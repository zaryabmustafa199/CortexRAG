"""
app/services/auth_service.py
-----------------------------
Business logic for user registration, login, token refresh, and logout.

Engineering rules applied:
  - .first() / scalar_one_or_none() + manual None check — never .one()
  - secrets.token_urlsafe() for all token/key generation
  - Brute-force protection via Redis counter (5 attempts → 15-min lock)
  - Refresh token rotation: each use invalidates the old token
  - Access token blacklist on logout (TTL = remaining JWT lifetime)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccountLockedException,
    AuthenticationException,
    ConflictException,
    TokenRevokedException,
)
from app.core.redis_client import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import Profile, User
from app.models.workspace import Workspace, WorkspaceMember

logger = structlog.get_logger()

# Brute-force protection constants
MAX_LOGIN_ATTEMPTS = 5
LOCK_DURATION_SECONDS = 900  # 15 minutes

# Refresh token Redis key namespace
REFRESH_TOKEN_KEY = "refresh:{user_id}:{token_hash}"


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, email: str, password: str) -> tuple[User, str, str]:
        """
        Register a new user.

        Steps:
          1. Check for duplicate email — raise ConflictException if found
          2. Hash password with PBKDF2-SHA256
          3. Create User + Profile (free tier) + default Workspace
          4. Auto-add user as ADMIN member of their own workspace
          5. Generate access + refresh tokens

        Returns:
            (user, access_token, raw_refresh_token)
        """
        # 1. Duplicate email check
        existing = await self.db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        existing_user = existing.scalar_one_or_none()
        if existing_user is not None:
            raise ConflictException("An account with this email already exists.")

        # 2. Hash password
        hashed = hash_password(password)

        # 3. Create User
        user = User(
            email=email.lower().strip(),
            hashed_password=hashed,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()  # get user.id without committing

        # 4. Create Profile (free tier defaults)
        profile = Profile(
            user_id=user.id,
            tier="free",
            doc_limit=settings.MAX_DOCS_FREE,
            query_limit_monthly=settings.MAX_QUERIES_MONTHLY_FREE,
            storage_limit_mb=settings.MAX_UPLOAD_SIZE_MB_FREE,
        )
        self.db.add(profile)

        # 5. Create default personal workspace
        workspace = Workspace(
            name="My Workspace",
            owner_id=user.id,
        )
        self.db.add(workspace)
        await self.db.flush()  # get workspace.id

        # 6. Add user as admin of their own workspace
        from app.models.workspace import MemberRole
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MemberRole.ADMIN,
        )
        self.db.add(member)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info(
            "user_registered",
            user_id=str(user.id),
            workspace_id=str(workspace.id),
        )

        # 7. Generate tokens
        access_token = create_access_token(str(user.id))
        raw_refresh, refresh_hash = create_refresh_token()
        await self._store_refresh_token(str(user.id), refresh_hash)

        return user, access_token, raw_refresh

    async def login(self, email: str, password: str) -> tuple[User, str, str]:
        """
        Authenticate a user.

        Steps:
          1. Check brute-force lock → raise AccountLockedException if locked
          2. Fetch user by email (.first() → raise UserNotFoundException if None)
          3. Verify PBKDF2-SHA256 password → increment fail counter on mismatch
          4. Reset fail counter on success
          5. Generate and store tokens

        Returns:
            (user, access_token, raw_refresh_token)
        """
        email_clean = email.lower().strip()
        lock_key = f"login_fail:{email_clean}"

        # 1. Brute-force check
        # redis_client.get() returns str|None with decode_responses=True;
        # cast resolves mypy's Awaitable[Any]|Any union from untyped redis stubs.
        fail_count: str | None = str(redis_client.get(lock_key) or "") or None
        if fail_count and int(fail_count) >= MAX_LOGIN_ATTEMPTS:
            raise AccountLockedException(
                "Account temporarily locked due to repeated failed login attempts. "
                "Please wait 15 minutes."
            )

        # 2. Fetch user
        result = await self.db.execute(
            select(User).where(User.email == email_clean)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Increment fail counter even for non-existent emails (prevent enumeration)
            self._increment_fail_counter(lock_key)
            raise AuthenticationException("Invalid email or password.")

        # 3. Verify password
        if not verify_password(password, user.hashed_password):
            self._increment_fail_counter(lock_key)
            logger.warning("login_failed", email=email_clean, attempt=fail_count)
            raise AuthenticationException("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationException("Account has been deactivated.")

        # 4. Reset fail counter
        redis_client.delete(lock_key)
        logger.info("login_success", user_id=str(user.id))

        # 5. Generate tokens
        access_token = create_access_token(str(user.id))
        raw_refresh, refresh_hash = create_refresh_token()
        await self._store_refresh_token(str(user.id), refresh_hash)

        return user, access_token, raw_refresh

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str]:
        """
        Rotate refresh token — invalidate old token, issue new pair.

        Steps:
          1. Look up which user owns this refresh token via Redis scan
             (tokens stored as: refresh:{user_id}:{hash} = "valid")
          2. Delete old token from Redis
          3. Issue new access + refresh token pair

        Returns:
            (new_access_token, new_raw_refresh_token)

        Raises:
            TokenRevokedException — if token not found in Redis (already used or expired)
        """
        import hashlib
        token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()

        # Scan Redis for this token hash across all users
        for key in redis_client.scan_iter(f"refresh:*:{token_hash}"):
            # Valid token found
            redis_client.delete(key)
            user_id = key.split(":")[1]

            # Verify user still exists
            result = await self.db.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise TokenRevokedException()

            new_access = create_access_token(str(user.id))
            new_raw_refresh, new_refresh_hash = create_refresh_token()
            await self._store_refresh_token(user_id, new_refresh_hash)

            logger.info("token_refreshed", user_id=user_id)
            return new_access, new_raw_refresh

        # Token not found → already used or expired
        raise TokenRevokedException(
            "Refresh token is invalid or expired. Please log in again."
        )

    async def logout(self, access_token: str, user_id: str) -> None:
        """
        Revoke the access token by adding it to the Redis blacklist.
        TTL is set to the token's remaining lifetime.
        Refresh tokens are left to expire naturally (they are short-lived and single-use).
        """
        from jose import jwt as jose_jwt
        try:
            payload = jose_jwt.decode(
                access_token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            exp = payload.get("exp", 0)
            remaining = max(0, int(exp - datetime.now(UTC).timestamp()))
            if remaining > 0:
                redis_client.setex(f"blacklist:{access_token}", remaining, "1")
        except Exception:
            pass  # Token already invalid — no-op

        logger.info("user_logged_out", user_id=user_id)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _store_refresh_token(self, user_id: str, token_hash: str) -> None:
        """Store refresh token hash in Redis with TTL = refresh token lifetime."""
        key = f"refresh:{user_id}:{token_hash}"
        ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400  # days → seconds
        redis_client.setex(key, ttl, "valid")

    def _increment_fail_counter(self, lock_key: str) -> None:
        """Increment login failure counter; set TTL on first failure."""
        count = redis_client.incr(lock_key)
        if count == 1:
            redis_client.expire(lock_key, LOCK_DURATION_SECONDS)
