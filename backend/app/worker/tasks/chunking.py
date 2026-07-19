"""
app/worker/tasks/chunking.py
---------------------------
Orchestration function for document chunking on worker processes.
Calls chunking service and saves ParentChunk and LeafChunk structures in the database.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, LeafChunk, ParentChunk
from app.services.chunking_service import build_leaf_chunks, build_parent_chunks

logger = structlog.get_logger()


async def chunk_and_save_document(
    db: AsyncSession,
    document: Document,
    pages: list[dict[str, int | str]],
    correlation_id: str | None = None,
) -> tuple[list[ParentChunk], list[LeafChunk]]:
    """
    Take a list of extracted pages, chunk them into hierarchical parents and child leaves,
    and save them to the database.
    """
    log = logger.bind(document_id=str(document.id), correlation_id=correlation_id)
    log.info("chunking_started", pages_count=len(pages))

    # 1. Build parent chunks from the page stream
    parent_data_list = await build_parent_chunks(pages)

    parent_models = []
    leaf_models = []

    from app.services.summary_service import SummaryService

    summary_service = SummaryService()

    for parent_data in parent_data_list:
        # Generate parent summary with LLM
        summary = None
        try:
            summary = await summary_service.summarize_text(parent_data["content"])
        except Exception as exc:
            log.warning("parent_chunk_summarization_failed", error=str(exc))

        # Create ParentChunk model
        parent = ParentChunk(
            document_id=document.id,
            workspace_id=document.workspace_id,
            content=parent_data["content"],
            summary=summary,
            section_title=parent_data["section_title"],
            page_start=parent_data["page_start"],
            page_end=parent_data["page_end"],
            token_count=parent_data["token_count"],
        )
        db.add(parent)
        parent_models.append(parent)

        # Flush parent to get generated UUID
        await db.flush()

        # Build child leaf chunks for this parent.
        # Assertions narrow page_start/page_end from Optional[int] → int;
        # they are always set from parent_data which always contains integer page values.
        assert parent.page_start is not None, "parent.page_start must not be None"
        assert parent.page_end is not None, "parent.page_end must not be None"
        leaf_data_list = build_leaf_chunks(
            parent_content=parent.content,
            page_start=parent.page_start,
            page_end=parent.page_end,
            section_title=parent.section_title,
        )

        for leaf_data in leaf_data_list:
            leaf = LeafChunk(
                parent_id=parent.id,
                workspace_id=document.workspace_id,
                content=leaf_data["content"],
                chunk_index=leaf_data["chunk_index"],
                token_count=leaf_data["token_count"],
                page_number=leaf_data["page_number"],
                section_title=leaf_data["section_title"],
                years_detected=leaf_data["years_detected"],
            )
            db.add(leaf)
            leaf_models.append(leaf)

    await db.commit()

    # 3. Index leaf chunks in Elasticsearch for BM25 search
    import asyncio

    from app.services.bm25_service import index_leaf_chunk

    es_tasks = [
        index_leaf_chunk(leaf.id, leaf.content, leaf.workspace_id, leaf.section_title)
        for leaf in leaf_models
    ]
    if es_tasks:
        await asyncio.gather(*es_tasks, return_exceptions=True)

    log.info("chunking_completed", parents_count=len(parent_models), leaves_count=len(leaf_models))
    return parent_models, leaf_models
