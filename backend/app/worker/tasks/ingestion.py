"""
app/worker/tasks/ingestion.py
-----------------------------
Master Celery ingestion task.
Coordinates download, extraction, chunking, LLM summarization, and embedding generation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.exceptions import EmbeddingException, FileParsingException, StorageException
from app.core.redis_client import redis_client
from app.db.session import AsyncSessionLocal, engine
from app.models.document import Document, DocumentStatus, UploadJob
from app.worker.celery_app import celery_app
from app.worker.tasks.chunking import chunk_and_save_document
from app.worker.tasks.embedding import embed_and_save_leaf_chunks
from app.worker.tasks.extraction import extract_document_text

logger = structlog.get_logger()


async def mark_job_as_failed(job_id: str, error_message: str) -> None:
    """Helper to mark a job and document as FAILED in the database and publish notification."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(UploadJob).where(UploadJob.id == uuid.UUID(job_id)))
        job = job_result.scalar_one_or_none()
        if job:
            job.status = "FAILED"
            job.error_message = error_message

            doc_result = await db.execute(select(Document).where(Document.id == job.document_id))
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = error_message

                # Publish failure event
                redis_client.publish(
                    f"cortex:notify:{doc.workspace_id}",
                    json.dumps(
                        {
                            "type": "DOCUMENT_FAILED",
                            "document_id": str(doc.id),
                            "error": error_message,
                        }
                    ),
                )
            await db.commit()


async def run_ingest_pipeline(job_id: str, correlation_id: str | None = None) -> None:
    """Core async orchestration for document ingestion."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        # 1. Fetch Job and Document records
        job_result = await db.execute(select(UploadJob).where(UploadJob.id == uuid.UUID(job_id)))
        job = job_result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Ingestion failed: Job {job_id} not found.")

        doc_result = await db.execute(select(Document).where(Document.id == job.document_id))
        doc = doc_result.scalar_one_or_none()
        if doc is None:
            raise ValueError(f"Ingestion failed: Document associated with Job {job_id} not found.")

        try:
            # 2. Extract Text (Downloads from MinIO and updates status to PROCESSING)
            pages = await extract_document_text(db, doc, correlation_id)

            # 3. Chunk and Save (Builds Parent/Leaf chunks and generates LLM summaries)
            parents, leaves = await chunk_and_save_document(db, doc, pages, correlation_id)

            # 4. Generate & Save Embeddings
            await embed_and_save_leaf_chunks(db, leaves, correlation_id)

            # 5. Mark as ready
            doc.status = DocumentStatus.READY
            job.status = "SUCCESS"
            await db.commit()

            # 6. Publish success notification to Redis Pub/Sub
            redis_client.publish(
                f"cortex:notify:{doc.workspace_id}",
                json.dumps(
                    {
                        "type": "DOCUMENT_READY",
                        "document_id": str(doc.id),
                        "status": "READY",
                    }
                ),
            )
            logger.info("ingestion_pipeline_success", job_id=job_id, doc_id=str(doc.id))

        except (StorageException, FileParsingException, EmbeddingException) as exc:
            # Known domain exception — fail immediately without Celery retries
            logger.error("ingestion_pipeline_domain_error", job_id=job_id, error=exc.message)
            doc.status = DocumentStatus.FAILED
            doc.error_message = exc.message
            job.status = "FAILED"
            job.error_message = exc.message
            await db.commit()

            redis_client.publish(
                f"cortex:notify:{doc.workspace_id}",
                json.dumps(
                    {
                        "type": "DOCUMENT_FAILED",
                        "document_id": str(doc.id),
                        "error": exc.message,
                    }
                ),
            )
        except Exception as exc:
            # Transient/unexpected exception — will bubble up to be retried by Celery
            logger.error("ingestion_pipeline_unexpected_error", job_id=job_id, error=str(exc))
            raise exc


@celery_app.task(bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def ingest_document(self: Any, job_id: str, correlation_id: str) -> None:
    """
    Celery task wrapper for document ingestion pipeline.
    Runs the async pipeline inside the synchronous worker process.
    Handles exponential backoff retries for unexpected errors.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id, job_id=job_id)

    logger.info("ingestion_task_received", job_id=job_id)

    try:
        asyncio.run(run_ingest_pipeline(job_id, correlation_id))
    except Exception as exc:
        # If all retries are exhausted, fail the job and document permanently
        if self.request.retries >= self.max_retries:
            logger.critical("ingestion_task_failed_permanently", job_id=job_id, error=str(exc))
            asyncio.run(
                mark_job_as_failed(job_id, f"Processing failed after 3 attempts: {str(exc)}")
            )
            return

        # Retry task with exponential backoff (e.g. 2, 4, 8 seconds + 2 seconds buffer)
        countdown = (2**self.request.retries) + 2
        logger.warning(
            "ingestion_task_retrying",
            job_id=job_id,
            attempt=self.request.retries + 1,
            delay=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
