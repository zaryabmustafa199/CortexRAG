"""
app/services/document_lifecycle.py
----------------------------------
Orchestrates secure document deactivation and cascade purging across storage layers:
  1. Downloads/removes file binaries from MinIO storage.
  2. Deletes associated LeafChunks in Elasticsearch index.
  3. Evicts cached queries from Redis.
  4. Cascade deletes SQL rows (chunks, embeddings, documents) under RLS.
"""
from __future__ import annotations

import uuid
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DocumentNotFoundException
from app.core.redis_client import redis_client
from app.models.document import Document, ParentChunk, LeafChunk
from app.services.storage_service import delete_file
from app.services.bm25_service import es_client

logger = structlog.get_logger()


class DocumentLifecycleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def purge_document(
        self,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        """
        Permanently purge a document and all related vectors, index entries,
        and objects. Enforces workspace RLS boundaries.
        """
        log = logger.bind(document_id=str(document_id), workspace_id=str(workspace_id))
        log.info("document_purge_started")

        # 1. Fetch the document (RLS enforces workspace isolation)
        doc_result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundException("Document not found or access denied.")

        # 2. Fetch all LeafChunk IDs associated with this document for Elasticsearch cleanup
        leaf_chunks_result = await self.db.execute(
            select(LeafChunk.id)
            .join(ParentChunk, LeafChunk.parent_id == ParentChunk.id)
            .where(ParentChunk.document_id == document_id)
        )
        chunk_ids = [str(cid) for cid in leaf_chunks_result.scalars().all()]

        # 3. Purge Elasticsearch index entries
        if chunk_ids:
            try:
                await es_client.delete_by_query(
                    index=settings.ELASTICSEARCH_INDEX_CHUNKS,
                    body={
                        "query": {
                            "ids": {"values": chunk_ids}
                        }
                    }
                )
                log.info("elasticsearch_chunks_purged", count=len(chunk_ids))
            except Exception as exc:
                # Log but continue to prevent blocking SQL cascade
                log.error("elasticsearch_purge_failed", error=str(exc))

        # 4. Purge MinIO binary object
        try:
            await delete_file(document.storage_key)
        except Exception as exc:
            log.error("minio_purge_failed", storage_key=document.storage_key, error=str(exc))

        # 5. Evict Redis RAG query caches for this workspace
        try:
            # Delete cache keys matching cache:workspace_id:* namespace
            cache_keys = []
            # Redis scan to locate matching keys
            for key in redis_client.scan_iter(f"cache:{workspace_id}:*"):
                cache_keys.append(key)
            
            if cache_keys:
                redis_client.delete(*cache_keys)
                log.info("redis_query_cache_invalidated", keys_count=len(cache_keys))
        except Exception as exc:
            log.error("redis_cache_invalidation_failed", error=str(exc))

        # 6. Delete document from database (cascades parent chunks, child leaves, and vector embeddings in DB)
        await self.db.delete(document)
        await self.db.commit()

        log.info("document_purge_completed")
