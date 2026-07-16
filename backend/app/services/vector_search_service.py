"""
app/services/vector_search_service.py
-------------------------------------
Vector similarity search service using pgvector.
Enforces Row-Level Security (RLS) by setting the workspace_id in the database transaction session.
"""
from __future__ import annotations

import uuid
import asyncio
from typing import Any
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SearchServiceException
from app.models.document import LeafChunk, ChunkEmbedding

logger = structlog.get_logger()


class VectorSearchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def vector_search(
        self,
        query_vec: list[float],
        workspace_id: uuid.UUID,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Perform a semantic similarity vector search over LeafChunks.
        Uses pgvector's cosine distance operator (<=>).
        
        RLS is activated by setting local session variables.
        Returns a list of dicts: {"chunk": LeafChunk, "similarity": float}
        """
        # Set workspace context locally for pgvector RLS checks
        await self.db.execute(
            text(f"SET LOCAL app.workspace_id = '{workspace_id}'")
        )

        from sqlalchemy.orm import selectinload
        try:
            # Query LeafChunks joined with embeddings, ordered by cosine distance
            query = (
                select(LeafChunk, (ChunkEmbedding.vector.cosine_distance(query_vec)).label("distance"))
                .options(selectinload(LeafChunk.parent))
                .join(ChunkEmbedding, LeafChunk.id == ChunkEmbedding.chunk_id)
                .where(LeafChunk.workspace_id == workspace_id)
                .order_by("distance")
                .limit(top_k)
            )

            # Enforce 10-second query statement timeout
            db_result = await asyncio.wait_for(
                self.db.execute(query),
                timeout=10.0
            )
            rows = db_result.all()

            results = []
            for leaf_chunk, distance in rows:
                # Cosine Similarity = 1 - Cosine Distance
                similarity = 1.0 - float(distance) if distance is not None else 0.0
                results.append({
                    "chunk": leaf_chunk,
                    "similarity": similarity,
                })

            logger.info(
                "vector_search_success",
                workspace_id=str(workspace_id),
                results_count=len(results),
            )
            return results

        except asyncio.TimeoutError:
            logger.error("vector_search_timeout", workspace_id=str(workspace_id))
            raise SearchServiceException("Semantic vector search timed out.")
        except Exception as exc:
            logger.error("vector_search_error", workspace_id=str(workspace_id), error=str(exc))
            raise SearchServiceException(f"Failed to execute vector search: {str(exc)}")
