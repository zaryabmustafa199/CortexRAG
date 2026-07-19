"""
app/services/bm25_service.py
----------------------------
Elasticsearch BM25 keyword search service.
Handles indexing, deletion, and keyword search operations.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch

from app.core.config import settings

logger = structlog.get_logger()

# Instantiate Async Elasticsearch Client
es_client = AsyncElasticsearch(settings.ELASTICSEARCH_URL)


async def init_es_index() -> None:
    """Initialize Elasticsearch index chunks mappings if not existing."""
    index = settings.ELASTICSEARCH_INDEX_CHUNKS
    try:
        if not await es_client.indices.exists(index=index):
            await es_client.indices.create(
                index=index,
                body={
                    "mappings": {
                        "properties": {
                            "chunk_id": {"type": "keyword"},
                            "content": {"type": "text"},
                            "workspace_id": {"type": "keyword"},
                            "section_title": {"type": "text"},
                        }
                    }
                },
            )
            logger.info("elasticsearch_index_created", index=index)
        else:
            logger.info("elasticsearch_index_exists", index=index)
    except Exception as exc:
        logger.error("elasticsearch_index_init_failed", index=index, error=str(exc))


async def index_leaf_chunk(
    chunk_id: uuid.UUID,
    content: str,
    workspace_id: uuid.UUID,
    section_title: str | None = None,
) -> None:
    """Index a LeafChunk inside Elasticsearch for BM25 retrieval."""
    try:
        await es_client.index(
            index=settings.ELASTICSEARCH_INDEX_CHUNKS,
            id=str(chunk_id),
            body={
                "chunk_id": str(chunk_id),
                "content": content,
                "workspace_id": str(workspace_id),
                "section_title": section_title or "",
            },
        )
    except Exception as exc:
        # Fail open: log error but do not raise, keeping chunking worker alive
        logger.error("elasticsearch_indexing_failed", chunk_id=str(chunk_id), error=str(exc))


async def delete_indexed_chunks(workspace_id: uuid.UUID) -> None:
    """Delete all indexed chunks associated with a workspace."""
    try:
        await es_client.delete_by_query(
            index=settings.ELASTICSEARCH_INDEX_CHUNKS,
            body={"query": {"term": {"workspace_id": str(workspace_id)}}},
        )
        logger.info("elasticsearch_chunks_deleted", workspace_id=str(workspace_id))
    except Exception as exc:
        logger.error("elasticsearch_delete_failed", workspace_id=str(workspace_id), error=str(exc))


async def bm25_search(
    query_text: str,
    workspace_id: uuid.UUID,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """
    Search chunks using BM25 query text.
    Returns list of dicts: [{"chunk_id": UUID, "score": float}, ...]
    """
    try:
        response = await es_client.search(
            index=settings.ELASTICSEARCH_INDEX_CHUNKS,
            body={
                "size": top_k,
                "query": {
                    "bool": {
                        "must": [{"match": {"content": query_text}}],
                        "filter": [{"term": {"workspace_id": str(workspace_id)}}],
                    }
                },
            },
        )

        hits = response["hits"]["hits"]
        results = []
        for hit in hits:
            source = hit["_source"]
            results.append(
                {
                    "chunk_id": uuid.UUID(source["chunk_id"]),
                    "score": hit["_score"],
                }
            )

        logger.info("elasticsearch_search_success", query=query_text, results_count=len(results))
        return results

    except Exception as exc:
        logger.error("elasticsearch_search_failed", query=query_text, error=str(exc))
        # Fail open: fallback to empty results if Elasticsearch is unreachable
        return []
