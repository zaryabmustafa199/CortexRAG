"""
app/schemas/documents.py
------------------------
Pydantic schemas for document and upload job endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    storage_key: str
    status: str
    mime_type: str | None = None
    file_size: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadJobResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    celery_task_id: str | None = None
    status: str
    error_message: str | None = None
    correlation_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentPresignedUrlResponse(BaseModel):
    url: str
    expires_in_seconds: int = 600


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    download_url: str
    expires_in_seconds: int = 600


class LeafChunkSchema(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID
    content: str
    chunk_index: int
    token_count: int
    years_detected: list[int] | None = None

    model_config = {"from_attributes": True}


class ParentChunkSchema(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    token_count: int
    summary: str | None = None
    leaf_chunks: list[LeafChunkSchema] = []

    model_config = {"from_attributes": True}

