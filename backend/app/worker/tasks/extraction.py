"""
app/worker/tasks/extraction.py
-----------------------------
Document text extraction logic for worker execution.
Downloads from MinIO and invokes the parser service.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import FileParsingException, StorageException
from app.models.document import Document, DocumentStatus
from app.services.parser_service import extract_text_streaming
from app.services.storage_service import get_file

logger = structlog.get_logger()


async def extract_document_text(
    db: AsyncSession,
    document: Document,
    correlation_id: str | None = None,
) -> list[dict[str, int | str]]:
    """
    Download file from MinIO and extract its text page-by-page.
    Updates Document status to PROCESSING during extraction.
    On failure, updates Document status to FAILED.
    """
    log = logger.bind(document_id=str(document.id), correlation_id=correlation_id)
    log.info("extraction_started", filename=document.filename, storage_key=document.storage_key)

    try:
        # Update status to PROCESSING
        document.status = DocumentStatus.PROCESSING
        await db.commit()

        # Download from MinIO
        file_bytes = await get_file(document.storage_key)

        # Extract text page-by-page
        pages = []
        mime_type = document.mime_type or "application/pdf"

        for page_data in extract_text_streaming(file_bytes, mime_type):
            pages.append(page_data)

        log.info("extraction_completed", pages_count=len(pages))
        return pages

    except (StorageException, FileParsingException) as exc:
        log.error("extraction_failed_known", error=exc.message)
        document.status = DocumentStatus.FAILED
        document.error_message = exc.message
        await db.commit()
        raise exc
    except Exception as exc:
        error_msg = f"Unexpected error during extraction: {str(exc)}"
        log.error("extraction_failed_unexpected", error=str(exc), exc_info=True)
        document.status = DocumentStatus.FAILED
        document.error_message = error_msg
        await db.commit()
        raise FileParsingException(error_msg)
