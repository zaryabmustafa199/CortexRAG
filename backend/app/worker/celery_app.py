"""
app/worker/celery_app.py
------------------------
Celery application instance.
"""
from __future__ import annotations

from celery import Celery
from app.core.config import settings

# Import all models to ensure SQLAlchemy registers them and avoids mapper failures
from app.models.user import User, Profile, APIKey, UsageRecord
from app.models.workspace import Workspace, WorkspaceMember
from app.models.document import Document, UploadJob, ParentChunk, LeafChunk, ChunkEmbedding
from app.models.query import QuerySession, Message, Citation, FeedbackRecord

celery_app = Celery(
    "cortexrag",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    include=[
        "app.worker.tasks.ingestion",
        "app.worker.tasks.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_max_tasks_per_child=50,
    task_routes={
        "app.worker.tasks.ingestion.ingest_document": {"queue": "ingestion"},
        "app.worker.tasks.cleanup.cleanup_user_data": {"queue": "cleanup"},
    },
)
