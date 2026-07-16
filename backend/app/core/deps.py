"""
app/core/deps.py
----------------
FastAPI dependency functions shared across routers.

Key dependencies:
  - get_current_user()   — validates JWT, checks blacklist, returns User
  - get_current_db()     — returns DB session with RLS activated for user's workspace
  - require_workspace()  — resolves + validates workspace and membership
  - require_pro()        — gates pro-only endpoints by profile tier
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationException,
    ForbiddenException,
    UserNotFoundException,
    WorkspaceNotFoundException,
)
from app.core.rate_limiter import check_rate_limit
from app.core.redis_client import redis_client
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.user import APIKey, Profile, User
from app.models.workspace import Workspace, WorkspaceMember

# ---------------------------------------------------------------------------
# HTTP Bearer scheme — reads the Authorization: Bearer <token> header
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Core: validate JWT or API Key and return authenticated User
# ---------------------------------------------------------------------------
async def get_current_user(
    request: Request,
) -> User:
    """
    Validate the authentication credentials (JWT Bearer token or ApiKey) and
    return the authenticated User. Also applies per-user/per-key rate limiting.

    Raises:
        AuthenticationException — missing, invalid, expired, or revoked token/key.
        UserNotFoundException   — user deleted from DB.
        RateLimitException      — rate limit exceeded.
    """
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("X-API-Key")

    token: str | None = None
    raw_api_key: str | None = None

    if auth_header:
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif auth_header.startswith("ApiKey "):
            raw_api_key = auth_header[7:]
        else:
            raise AuthenticationException("Invalid authentication scheme. Use Bearer or ApiKey.")
    elif api_key_header:
        raw_api_key = api_key_header

    if not token and not raw_api_key:
        raise AuthenticationException("Authorization header or X-API-Key missing.")

    if token:
        # ── JWT Authentication ────────────────────────────────────────────────
        # Decode and validate JWT structure + expiry
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise AuthenticationException("Token missing subject claim.")

        # Check if token has been explicitly revoked (logout)
        blacklist_key = f"blacklist:{token}"
        if redis_client.exists(blacklist_key):
            raise AuthenticationException("Token has been revoked. Please log in again.")

        # Fetch user from DB
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.id == uuid.UUID(user_id_str))
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise UserNotFoundException("Account not found.")
            if not user.is_active:
                raise AuthenticationException("Account has been deactivated.")

        # Enforce per-user rate limit (60 requests / minute)
        check_rate_limit(f"user:{user.id}", limit=60, window=60)
        return user

    else:
        # ── API Key Authentication ────────────────────────────────────────────
        # raw_api_key is guaranteed non-None here: the else branch is only reached
        # when the token branch above is not entered, and at least one of them must be
        # non-None due to the guard at line 74. Assert to narrow str|None -> str.
        assert raw_api_key is not None
        key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()

        async with AsyncSessionLocal() as db:
            # Fetch API Key
            key_result = await db.execute(
                select(APIKey).where(APIKey.key_hash == key_hash)
            )
            api_key = key_result.scalar_one_or_none()
            if api_key is None or not api_key.is_active:
                raise AuthenticationException("Invalid or inactive API key.")

            # Update last_used_at
            api_key.last_used_at = func.now()
            await db.commit()

            # Fetch user
            user_result = await db.execute(
                select(User).where(User.id == api_key.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                raise UserNotFoundException("Associated account not found.")
            if not user.is_active:
                raise AuthenticationException("Associated account has been deactivated.")

        # Enforce per-key rate limit (60 requests / minute)
        check_rate_limit(f"key:{api_key.id}", limit=60, window=60)
        return user



# ---------------------------------------------------------------------------
# DB session with RLS activated for a specific workspace
# ---------------------------------------------------------------------------
async def get_db_for_workspace(workspace_id: str = "") -> AsyncGenerator[AsyncSession, None]:
    """
    Returns an async DB session with RLS activated.
    Called internally by require_workspace() — not used directly in routes.
    """
    async with AsyncSessionLocal() as session:
        if workspace_id:
            from sqlalchemy import text
            await session.execute(
                text(f"SET LOCAL app.workspace_id = '{workspace_id}'")
            )
        yield session


# ---------------------------------------------------------------------------
# Resolve and validate workspace membership
# ---------------------------------------------------------------------------
async def require_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> tuple[Workspace, WorkspaceMember]:
    """
    Validate that the current user is a member of the requested workspace.

    Returns:
        (Workspace, WorkspaceMember) tuple — membership includes the user's role.

    Raises:
        WorkspaceNotFoundException — workspace doesn't exist.
        ForbiddenException         — user is not a member of this workspace.
    """
    async with AsyncSessionLocal() as db:
        # Fetch workspace
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = ws_result.scalar_one_or_none()
        if workspace is None:
            raise WorkspaceNotFoundException()

        # Fetch membership
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        membership = member_result.scalar_one_or_none()
        if membership is None:
            raise ForbiddenException("You are not a member of this workspace.")

        return workspace, membership


# ---------------------------------------------------------------------------
# Pro tier gate
# ---------------------------------------------------------------------------
async def require_pro(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency for pro-only endpoints.
    Raises ForbiddenException if user's profile tier is 'free'.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Profile).where(Profile.user_id == current_user.id)
        )
        profile = result.scalar_one_or_none()
        if profile is None or profile.tier != "pro":
            raise ForbiddenException(
                "This feature requires a Pro plan.",
                details={"required_tier": "pro", "current_tier": getattr(profile, "tier", "free")},
            )
        return current_user


# ---------------------------------------------------------------------------
# DB Session with Workspace RLS Enforced
# ---------------------------------------------------------------------------
async def get_rls_db(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that validates the user's membership in the workspace
    and returns a database session with Row-Level Security (RLS) activated.
    """
    # 1. Validate membership first using a temporary session
    async with AsyncSessionLocal() as db:
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if member_result.scalar_one_or_none() is None:
            raise ForbiddenException("You do not have access to this workspace.")

    # 2. Yield session with RLS activated
    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import text
            await session.execute(
                text(f"SET LOCAL app.workspace_id = '{workspace_id}'")
            )
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

