"""
app/schemas/query.py
--------------------
Pydantic schemas for query session and RAG query ask endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.sanitizer import SanitizedStr, SanitizedStrOptional


class QueryRequest(BaseModel):
    session_id: uuid.UUID | None = Field(None, description="UUID of existing session, or null to auto-create.")
    workspace_id: uuid.UUID = Field(..., description="Target workspace.")
    question: SanitizedStr = Field(..., min_length=1, max_length=2000)


class CitationResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    page_number: int | None = None
    section_title: str | None = None
    confidence_score: float | None = None
    chunk_content: str | None = None
    document_name: str | None = None
    document_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def load_citation_metadata(cls, data: Any) -> Any:
        if hasattr(data, "chunk") and data.chunk is not None:
            data.chunk_content = data.chunk.content
            if hasattr(data.chunk, "parent") and data.chunk.parent is not None:
                if hasattr(data.chunk.parent, "document") and data.chunk.parent.document is not None:
                    data.document_name = data.chunk.parent.document.filename
                    data.document_id = data.chunk.parent.document.id
        return data


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime
    citations: list[CitationResponse] = []

    model_config = {"from_attributes": True}


class QuerySessionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None = None
    created_at: datetime
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}


class CreateSessionRequest(BaseModel):
    title: SanitizedStrOptional = Field(None, max_length=500, description="Optional custom title for the session.")

