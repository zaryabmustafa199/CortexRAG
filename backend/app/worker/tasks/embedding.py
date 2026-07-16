"""
app/worker/tasks/embedding.py
-----------------------------
Document embedding task logic for worker execution.
Calls embedding service and inserts ChunkEmbedding records into the database.
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmbeddingException
from app.models.document import ChunkEmbedding, LeafChunk
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()


async def embed_and_save_leaf_chunks(
    db: AsyncSession,
    leaves: list[LeafChunk],
    correlation_id: str | None = None,
) -> list[ChunkEmbedding]:
    """
    Take a list of LeafChunks, generate vector embeddings for their content,
    and save ChunkEmbedding records in the database.
    """
    if not leaves:
        return []

    log = logger.bind(document_id=str(leaves[0].workspace_id), correlation_id=correlation_id)
    log.info("embedding_started", chunks_count=len(leaves))

    # 1. Extract texts
    texts = [leaf.content for leaf in leaves]

    # 2. Call embedding service
    embed_service = EmbeddingService()
    try:
        vectors = await embed_service.embed_texts(texts)
    except Exception as exc:
        log.error("embedding_generation_failed", error=str(exc))
        if isinstance(exc, EmbeddingException):
            raise exc
        raise EmbeddingException(f"Failed to generate embeddings: {str(exc)}")

    # 3. Create ChunkEmbedding models
    embedding_models = []
    model_name = embed_service.active_model_name

    for leaf, vector in zip(leaves, vectors):
        embedding = ChunkEmbedding(
            chunk_id=leaf.id,
            workspace_id=leaf.workspace_id,
            model_name=model_name,
            vector=vector,
        )
        db.add(embedding)
        embedding_models.append(embedding)

    await db.commit()
    log.info("embedding_completed", embeddings_count=len(embedding_models), model_name=model_name)
    return embedding_models
