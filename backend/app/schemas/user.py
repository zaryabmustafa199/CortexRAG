"""
app/schemas/user.py
-------------------
Pydantic schemas for user and profile API endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from app.core.sanitizer import SanitizedStrOptional


class ProfileResponse(BaseModel):
    tier: str
    doc_limit: int
    query_limit_monthly: int
    storage_limit_mb: int

    model_config = {"from_attributes": True}


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
    profile: ProfileResponse | None = None

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    """Fields the user can self-update."""
    display_name: SanitizedStrOptional = Field(None, min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        errors = []
        if not any(c.isupper() for c in v):
            errors.append("at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(f"New password must contain: {', '.join(errors)}")
        return v


class TierToggleRequest(BaseModel):
    tier: str = Field(pattern="^(free|pro)$")


class DeleteAccountRequest(BaseModel):
    """User must type 'DELETE' to confirm account deletion."""
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def must_type_delete(cls, v: str) -> str:
        if v != "DELETE":
            raise ValueError("You must type 'DELETE' to confirm account deletion.")
        return v
