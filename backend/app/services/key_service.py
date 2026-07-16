"""
app/services/key_service.py
----------------------------
Business logic for API key generation, validation, and deactivation.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
import structlog
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationException, ForbiddenException, CortexException
from app.models.user import APIKey, User

logger = structlog.get_logger()


class KeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_key(self, user_id: uuid.UUID, name: str) -> tuple[APIKey, str]:
        """
        Generate a cryptographically secure API key.
        Stores only the SHA-256 hash in the database.
        Returns the database record and the raw key (shown only once).
        """
        # Prefix the key for easy identification (e.g., cr_...)
        raw_key = f"cr_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            is_active=True,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        logger.info("api_key_created", user_id=str(user_id), key_id=str(api_key.id), name=name)
        return api_key, raw_key

    async def list_keys(self, user_id: uuid.UUID) -> list[APIKey]:
        """List all API keys belonging to the user, ordered by creation date."""
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_key(self, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
        """Deactivate an API key. Reversible or soft delete."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            # ForbiddenException is the closest semantic match for a missing resource
            # that belongs to the authenticated user (avoids exposing whether IDs exist).
            raise ForbiddenException("API key not found or you do not have permission to deactivate it.")

        api_key.is_active = False
        await self.db.commit()
        logger.info("api_key_deactivated", user_id=str(user_id), key_id=str(key_id))

    async def authenticate_key(self, raw_key: str) -> User:
        """
        Authenticate a raw API key.
        Updates last_used_at on success.
        Raises AuthenticationException if invalid or inactive.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        result = await self.db.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None or not api_key.is_active:
            raise AuthenticationException("Invalid or inactive API key.")

        # Update last used timestamp
        api_key.last_used_at = func.now()
        await self.db.commit()

        # Fetch associated user
        user_result = await self.db.execute(
            select(User).where(User.id == api_key.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthenticationException("Associated user account is inactive or not found.")

        logger.info("api_key_auth_success", user_id=str(user.id), key_id=str(api_key.id))
        return user
