"""
app/services/upload_service.py
------------------------------
Handles document upload validation (size, extension, double extension, magic bytes)
and orchestrates the database record creation and Celery ingestion dispatch.
"""
from __future__ import annotations

import re
import uuid
import structlog
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidFileException, QuotaExceededException
from app.models.document import Document, DocumentStatus, UploadJob
from app.models.user import Profile
from app.services.storage_service import store_file
from app.worker.tasks.ingestion import ingest_document

logger = structlog.get_logger()

# Allowed extensions and their corresponding MIME types
ALLOWED_MIMES = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",  # docx files are zip archives
    },
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown", "application/octet-stream"},
}


class UploadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def handle_upload(
        self,
        workspace_id: uuid.UUID,
        profile: Profile,
        file: UploadFile,
        correlation_id: str | None = None,
    ) -> UploadJob:
        """
        Validate file, store in MinIO, create DB records, and trigger Celery task.
        """
        filename = file.filename or "unnamed_file"
        
        # 1. Read file bytes
        content = await file.read()
        file_size = len(content)

        # 2. Quota Check: total document count in this workspace
        doc_count_result = await self.db.execute(
            select(func.count()).select_from(Document).where(Document.workspace_id == workspace_id)
        )
        doc_count = doc_count_result.scalar() or 0
        if doc_count >= profile.doc_limit:
            raise QuotaExceededException(
                f"Document limit reached. Your tier allows up to {profile.doc_limit} documents per workspace."
            )

        # 3. File size check
        limit_bytes = profile.storage_limit_mb * 1024 * 1024
        if file_size > limit_bytes:
            raise InvalidFileException(
                f"File size ({file_size / (1024 * 1024):.2f}MB) exceeds limit of {profile.storage_limit_mb}MB."
            )

        # 4. Extension whitelist check
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_MIMES:
            raise InvalidFileException(
                f"File extension '{suffix}' is not supported. Allowed: .pdf, .docx, .txt, .md"
            )

        # 5. Double extension validation (prevent malicious script uploads like script.sh.pdf)
        if re.search(r"\.(exe|sh|py|js|php|bat|cmd|bin)\.[a-z]+$", filename, re.I):
            raise InvalidFileException("Double-extension filename structure is not allowed.")

        # 6. Unicode RTL override character check
        if "\u202e" in filename:
            raise InvalidFileException("Filename contains forbidden characters.")

        # 7. Magic bytes check (python-magic)
        detected_mime = None
        try:
            import magic
            detected_mime = magic.from_buffer(content[:2048], mime=True)
        except Exception as exc:
            # Fallback gracefully if libmagic is not installed on system (e.g., local Windows)
            logger.warning("magic_bytes_detection_failed", error=str(exc))
            detected_mime = file.content_type or "application/octet-stream"

        allowed = ALLOWED_MIMES.get(suffix, set())
        if detected_mime not in allowed:
            # Also check if file.content_type is allowed as a secondary check
            if file.content_type not in allowed:
                raise InvalidFileException(
                    f"File MIME type mismatch. Extension '{suffix}' does not match content type '{detected_mime}'."
                )

        # 8. Store file in MinIO (private bucket)
        storage_key = await store_file(str(workspace_id), content, suffix)

        # 9. Create Document record in DB
        doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            storage_key=storage_key,
            status=DocumentStatus.PENDING,
            mime_type=detected_mime,
            file_size=file_size,
        )
        self.db.add(doc)
        await self.db.flush()

        # 10. Create UploadJob record
        job = UploadJob(
            document_id=doc.id,
            status="QUEUED",
            correlation_id=correlation_id,
        )
        self.db.add(job)
        await self.db.commit()

        await self.db.refresh(doc)
        await self.db.refresh(job)

        # 11. Dispatch Celery ingestion worker task
        ingest_document.delay(str(job.id), correlation_id)

        logger.info(
            "document_upload_success",
            workspace_id=str(workspace_id),
            document_id=str(doc.id),
            job_id=str(job.id),
            filename=filename,
        )

        return job
