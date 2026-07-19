"""
app/api/v1/documents.py
-----------------------
API endpoints for document uploads and secure presigned URL retrieval.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_rls_db
from app.core.exceptions import DocumentNotFoundException, UserNotFoundException
from app.models.document import Document, ParentChunk, UploadJob
from app.models.user import Profile, User
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentPresignedUrlResponse,
    DocumentResponse,
    ParentChunkSchema,
    UploadJobResponse,
)
from app.services.document_lifecycle import DocumentLifecycleService
from app.services.storage_service import get_presigned_url
from app.services.upload_service import UploadService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=UploadJobResponse, status_code=202)
async def upload_document(
    request: Request,
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> UploadJobResponse:
    """
    Upload a document (.pdf, .docx, .txt, .md) to a workspace.
    Runs validation, stores the file in secure storage, and schedules async ingestion.
    """
    # Fetch user profile for limit enforcement
    profile_result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise UserNotFoundException("User profile not found.")

    correlation_id = getattr(request.state, "correlation_id", None)

    upload_service = UploadService(db)
    job = await upload_service.handle_upload(
        workspace_id=workspace_id,
        profile=profile,
        file=file,
        correlation_id=correlation_id,
    )

    return UploadJobResponse.model_validate(job)


@router.get("/{document_id}/url", response_model=DocumentPresignedUrlResponse)
async def get_document_url(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> DocumentPresignedUrlResponse:
    """
    Get a secure, temporary presigned URL to download or view a document.
    The URL expires automatically after 10 minutes.
    """
    # Fetch document (RLS enforces workspace isolation automatically)
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundException("Document not found or access denied.")

    url = await get_presigned_url(doc.storage_key)
    return DocumentPresignedUrlResponse(url=url, expires_in_seconds=600)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> Response:
    """
    Permanently delete a document from the workspace.
    Triggers a cascading purge across all storage layers (pgvector, ES, MinIO, Redis cache).
    """
    lifecycle_service = DocumentLifecycleService(db)
    await lifecycle_service.purge_document(document_id=document_id, workspace_id=workspace_id)
    return Response(status_code=204)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: uuid.UUID,
    limit: int = 50,
    cursor: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> list[DocumentResponse]:
    """
    List all documents in a workspace (cursor-based pagination).
    """
    query = select(Document).where(Document.workspace_id == workspace_id)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(Document.created_at < cursor_dt)
        except ValueError:
            pass

    result = await db.execute(query.order_by(Document.created_at.desc()).limit(limit))
    return cast(list[DocumentResponse], list(result.scalars().all()))


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> DocumentDetailResponse:
    """
    Retrieve metadata and a temporary presigned download URL for a single document.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundException("Document not found or access denied.")

    url = await get_presigned_url(doc.storage_key)
    return DocumentDetailResponse(
        document=DocumentResponse.model_validate(doc),
        download_url=url,
        expires_in_seconds=600,
    )


@router.get("/{document_id}/status", response_model=UploadJobResponse)
async def get_document_status(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> UploadJobResponse:
    """
    Get the processing job status of an uploaded document.
    """
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundException("Document not found or access denied.")

    job_result = await db.execute(select(UploadJob).where(UploadJob.document_id == document_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        # Fallback if job record is missing
        return UploadJobResponse(
            id=uuid.uuid4(),
            document_id=document_id,
            status=doc.status.value,
            created_at=doc.created_at,
        )
    return UploadJobResponse.model_validate(job)


@router.get("/{document_id}/chunks", response_model=list[ParentChunkSchema])
async def get_document_chunks(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> list[ParentChunkSchema]:
    """
    Retrieve hierarchical chunks (parents and their leaf children) for a document.
    """
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundException("Document not found or access denied.")

    result = await db.execute(
        select(ParentChunk)
        .options(selectinload(ParentChunk.leaf_chunks))
        .where(ParentChunk.document_id == document_id)
        .order_by(ParentChunk.page_start.asc(), ParentChunk.id.asc())
    )
    return cast(list[ParentChunkSchema], list(result.scalars().all()))
