"""
app/worker/tasks/cleanup.py
---------------------------
Celery background cleanup tasks (GDPR account purges).
Deletes physical binaries from MinIO before purging user DB records.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models.document import Document
from app.models.user import User
from app.models.workspace import Workspace
from app.services.storage_service import delete_file
from app.worker.celery_app import celery_app

logger = structlog.get_logger()


async def run_user_data_purge(user_id: str) -> None:
    """Core async orchestration for GDPR user data purge."""
    user_uuid = uuid.UUID(user_id)
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        # Fetch workspaces owned by the user
        ws_result = await db.execute(
            select(Workspace).where(Workspace.owner_id == user_uuid)
        )
        workspaces = ws_result.scalars().all()
        workspace_ids = [ws.id for ws in workspaces]

        # If user owns workspaces, fetch all documents in them
        if workspace_ids:
            doc_result = await db.execute(
                select(Document).where(Document.workspace_id.in_(workspace_ids))
            )
            documents = doc_result.scalars().all()

            # Delete each document binary from MinIO
            for doc in documents:
                try:
                    await delete_file(doc.storage_key)
                except Exception as exc:
                    # Log but continue to ensure the DB purge executes
                    logger.error(
                        "cleanup_minio_file_failed",
                        doc_id=str(doc.id),
                        storage_key=doc.storage_key,
                        error=str(exc),
                    )

        # Fetch the user
        user_result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = user_result.scalar_one_or_none()
        if user:
            # Delete user (database cascade deletes workspaces, members, documents, chunks, and embeddings)
            await db.delete(user)
            await db.commit()
            logger.info("cleanup_user_data_success", user_id=user_id)
        else:
            logger.warning("cleanup_user_data_user_not_found", user_id=user_id)


@celery_app.task(bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def cleanup_user_data(self: Any, user_id: str) -> None:
    """
    Celery task to permanently purge all data associated with a soft-deleted user.
    Deletes MinIO files first and then cascade deletes DB entries.
    """
    logger.info("cleanup_user_data_task_received", user_id=user_id)
    try:
        asyncio.run(run_user_data_purge(user_id))
    except Exception as exc:
        logger.warning(
            "cleanup_user_data_task_retrying",
            user_id=user_id,
            attempt=self.request.retries + 1,
        )
        raise self.retry(exc=exc, countdown=10)
