"""
app/core/security.py
--------------------
Password hashing and JWT token utilities.

Rules enforced:
  - PBKDF2-SHA256 password hashing (zero external compile/binary dependencies)
  - JWT signed with HS256 using settings.JWT_SECRET (64-byte urlsafe token)
  - Token generation uses python-jose
  - Refresh tokens are stored as sha256(raw) in DB — never the raw value
  - All random/token generation uses `secrets` module, never `random`
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationException

# ---------------------------------------------------------------------------
# Password context (PBKDF2-SHA256 has zero external binary dependencies)
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Return PBKDF2-SHA256 hash of the given plain-text password."""
    return str(pwd_context.hash(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored hash."""
    return bool(pwd_context.verify(plain_password, hashed_password))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        subject: The user UUID (stored as the 'sub' claim).
        extra_claims: Optional dict of additional claims to embed.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return str(jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))


def create_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically secure refresh token.

    Returns:
        (raw_token, hashed_token) — store only the hash; give raw to client.
        The raw token is set as an HttpOnly cookie.
    """
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Raises:
        AuthenticationException — if the token is malformed, expired, or wrong type.
    """
    try:
        from typing import cast as _cast
        payload: dict[str, Any] = _cast(dict[str, Any], jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        ))
        if payload.get("type") != "access":
            raise AuthenticationException("Invalid token type.")
        return payload
    except JWTError as exc:
        raise AuthenticationException(f"Token validation failed: {exc}") from exc


def hash_api_key(raw_key: str) -> str:
    """Return sha256 hex digest of a raw API key — only this is stored in DB."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        (raw_key, key_hash) — show raw_key once to user; store only key_hash.
    """
    raw = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw)
    return raw, key_hash
