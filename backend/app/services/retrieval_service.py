"""
app/services/retrieval_service.py
---------------------------------
Orchestrates parallel hybrid retrieval (pgvector semantic + Elasticsearch BM25 keyword).
Merges and ranks results using Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

import uuid
import asyncio
from typing import Any, cast
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import LeafChunk
from app.services.vector_search_service import VectorSearchService
from app.services.bm25_service import bm25_search

logger = structlog.get_logger()


class RetrievalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.vector_search_service = VectorSearchService(db)

    async def hybrid_search(
        self,
        query_text: str,
        query_vec: list[float],
        workspace_id: uuid.UUID,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Execute parallel pgvector and Elasticsearch keyword search,
        combining rankings using Reciprocal Rank Fusion (RRF).

        Returns a list of dicts: {"chunk": LeafChunk, "rrf_score": float}
        """
        # Execute parallel searches with asyncio.gather (fail open, collect exceptions)
        tasks = [
            self.vector_search_service.vector_search(query_vec, workspace_id, top_k=top_k),
            bm25_search(query_text, workspace_id, top_k=top_k),
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 1. Parse vector results — narrow the BaseException union via isinstance guard
        if isinstance(raw_results[0], Exception):
            logger.error("hybrid_search_vector_failed", error=str(raw_results[0]))
            vector_results: list[dict[str, Any]] = []
        else:
            # cast() tells mypy the value is the expected list type after the Exception check
            vector_results = cast(list[dict[str, Any]], raw_results[0])

        # 2. Parse BM25 results — same pattern
        if isinstance(raw_results[1], Exception):
            logger.error("hybrid_search_bm25_failed", error=str(raw_results[1]))
            bm25_results: list[dict[str, Any]] = []
        else:
            bm25_results = cast(list[dict[str, Any]], raw_results[1])

        # 3. Resolve LeafChunk DB instances
        # Build map of chunk_id -> LeafChunk object from vector results
        chunk_map: dict[uuid.UUID, LeafChunk] = {
            item["chunk"].id: item["chunk"] for item in vector_results
        }

        # Identify chunk IDs present in BM25 results but missing from vector results
        bm25_chunk_ids: list[uuid.UUID] = [item["chunk_id"] for item in bm25_results]
        missing_ids = [cid for cid in bm25_chunk_ids if cid not in chunk_map]

        if missing_ids:
            try:
                # Fetch missing LeafChunk objects from DB, filtered to this workspace
                # Explicit workspace_id filter is required because the DB user (cortexrag)
                # is a superuser who bypasses PostgreSQL RLS policies.
                db_result = await self.db.execute(
                    select(LeafChunk)
                    .options(selectinload(LeafChunk.parent))
                    .where(
                        LeafChunk.id.in_(missing_ids),
                        LeafChunk.workspace_id == workspace_id,
                    )
                )
                for chunk in db_result.scalars().all():
                    chunk_map[chunk.id] = chunk
            except Exception as exc:
                logger.error("hybrid_search_db_resolution_failed", error=str(exc))

        # 4. Perform Reciprocal Rank Fusion (RRF)
        # RRF formula: Score(d) = sum( 1 / (60 + Rank(d, system)) )
        # k=60 is the standard RRF constant from the original 2009 paper.
        rrf_scores: dict[uuid.UUID, float] = {}

        for rank, item in enumerate(vector_results, start=1):
            chunk_id: uuid.UUID = item["chunk"].id
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (60.0 + rank)

        for rank, item in enumerate(bm25_results, start=1):
            chunk_id = item["chunk_id"]
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (60.0 + rank)

        # 5. Sort by RRF score descending and slice the top 25 candidates for the reranker
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        final_results: list[dict[str, Any]] = []
        for chunk_id, score in sorted_chunks[:25]:
            # chunk_map.get() can return None if the BM25 chunk was not loaded —
            # skip any chunk whose DB object failed to load
            chunk_obj: LeafChunk | None = chunk_map.get(chunk_id)
            if chunk_obj is not None:
                final_results.append({
                    "chunk": chunk_obj,
                    "rrf_score": score,
                })

        logger.info(
            "hybrid_search_success",
            workspace_id=str(workspace_id),
            vector_count=len(vector_results),
            bm25_count=len(bm25_results),
            merged_count=len(final_results),
        )
        return final_results
