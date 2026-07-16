"""
app/schemas/workspace.py
------------------------
Pydantic schemas for workspace and member management endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from app.core.sanitizer import SanitizedStr


class WorkspaceCreateRequest(BaseModel):
    name: SanitizedStr = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def name_safe_chars(cls, v: str) -> str:
        import re
        if not re.match(r"^[\w\s\-\.]+$", v):
            raise ValueError("Workspace name may only contain letters, numbers, spaces, hyphens, and dots.")
        return v.strip()


class WorkspaceUpdateRequest(BaseModel):
    name: SanitizedStr = Field(min_length=2, max_length=100)


class WorkspaceMemberResponse(BaseModel):
    user_id: uuid.UUID
    role: str
    invited_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime
    members: list[WorkspaceMemberResponse] = []

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: str = Field(default="editor", pattern="^(viewer|editor|admin)$")


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern="^(viewer|editor|admin)$")
