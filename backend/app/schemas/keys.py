"""
app/schemas/keys.py
-------------------
Pydantic schemas for API key management endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.sanitizer import SanitizedStr


class CreateAPIKeyRequest(BaseModel):
    name: SanitizedStr = Field(min_length=1, max_length=50)


class APIKeyCreatedResponse(BaseModel):
    """Returned only once on key creation — raw_key shown once and never again."""

    id: uuid.UUID
    name: str
    raw_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyResponse(BaseModel):
    """Safe listing response — never includes raw_key."""

    id: uuid.UUID
    name: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
