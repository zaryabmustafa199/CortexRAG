"""
app/services/storage_service.py
-------------------------------
S3-compatible file storage service using MinIO.
Runs synchronous MinIO operations in a thread pool to avoid blocking the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import timedelta

import structlog
from minio import Minio

from app.core.config import settings
from app.core.exceptions import StorageException

logger = structlog.get_logger()

# Instantiate MinIO client
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


def init_bucket() -> None:
    """Ensure the private document bucket exists in MinIO."""
    try:
        bucket = settings.MINIO_BUCKET
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info("minio_bucket_created", bucket=bucket)
        else:
            logger.info("minio_bucket_already_exists", bucket=bucket)
    except Exception as exc:
        logger.critical("minio_bucket_init_failed", error=str(exc))
        # Do not crash the process immediately, but log as critical


async def store_file(workspace_id: str, content: bytes, suffix: str) -> str:
    """
    Store file bytes in the private MinIO bucket under the path: {workspace_id}/{uuid}{suffix}.
    Runs in a thread pool and enforces a 30-second timeout.
    """
    storage_key = f"{workspace_id}/{uuid.uuid4()}{suffix}"
    bucket = settings.MINIO_BUCKET

    def _upload() -> None:
        data_stream = io.BytesIO(content)
        minio_client.put_object(
            bucket_name=bucket,
            object_name=storage_key,
            data=data_stream,
            length=len(content),
        )

    try:
        # Run synchronous MinIO call in thread executor
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _upload),
            timeout=30.0
        )
        logger.info("minio_file_stored", workspace_id=workspace_id, storage_key=storage_key, size_bytes=len(content))
        return storage_key
    except TimeoutError:
        logger.error("minio_upload_timeout", workspace_id=workspace_id, storage_key=storage_key)
        raise StorageException("File storage upload timed out.")
    except Exception as exc:
        logger.error("minio_upload_failed", workspace_id=workspace_id, storage_key=storage_key, error=str(exc))
        raise StorageException("Failed to store file in object storage.")


async def get_file(storage_key: str) -> bytes:
    """
    Retrieve file bytes from the MinIO bucket.
    Runs in a thread pool and enforces a 30-second timeout.
    """
    bucket = settings.MINIO_BUCKET

    def _download() -> bytes:
        response = minio_client.get_object(bucket, storage_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    try:
        content = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _download),
            timeout=30.0
        )
        return bytes(content)
    except TimeoutError:
        logger.error("minio_download_timeout", storage_key=storage_key)
        raise StorageException("File storage download timed out.")
    except Exception as exc:
        logger.error("minio_download_failed", storage_key=storage_key, error=str(exc))
        raise StorageException("Failed to retrieve file from object storage.")


async def get_presigned_url(storage_key: str) -> str:
    """
    Generate a presigned GET URL for retrieving a document.
    URL expires in 10 minutes (600 seconds).
    """
    bucket = settings.MINIO_BUCKET

    def _get_url() -> str:
        return str(minio_client.presigned_get_object(
            bucket_name=bucket,
            object_name=storage_key,
            expires=timedelta(minutes=10),
        ))

    try:
        url = await asyncio.get_event_loop().run_in_executor(None, _get_url)
        return str(url)
    except Exception as exc:
        logger.error("minio_presigned_url_failed", storage_key=storage_key, error=str(exc))
        raise StorageException("Failed to retrieve secure URL for document.")


async def delete_file(storage_key: str) -> None:
    """
    Delete a file from the MinIO bucket.
    """
    bucket = settings.MINIO_BUCKET

    def _delete() -> None:
        minio_client.remove_object(
            bucket_name=bucket,
            object_name=storage_key,
        )

    try:
        await asyncio.get_event_loop().run_in_executor(None, _delete)
        logger.info("minio_file_deleted", storage_key=storage_key)
    except Exception as exc:
        logger.error("minio_delete_failed", storage_key=storage_key, error=str(exc))
        raise StorageException("Failed to delete file from object storage.")
