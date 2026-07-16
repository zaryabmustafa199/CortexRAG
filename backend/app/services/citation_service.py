"""
app/services/citation_service.py
-------------------------------
Citation extraction and validation service.
Parses, validates, and persists citations from the LLM response text.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query import Citation

logger = structlog.get_logger()


class CitationService:
    @staticmethod
    def extract_citations(
        response_text: str,
        retrieved_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Parse and validate citations in format [Source N] from response text.
        Returns a list of unique validated citation attributes.
        """
        cited_indices = re.findall(r'\[Source (\d+)\]', response_text)
        valid_citations = []
        seen_chunk_ids = set()

        for idx_str in cited_indices:
            idx = int(idx_str) - 1
            if 0 <= idx < len(retrieved_results):
                chunk = retrieved_results[idx]["chunk"]
                if chunk.id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk.id)

                # Fetch rerank score as confidence
                rerank_score = retrieved_results[idx].get("rerank_score", 1.0)
                # Convert logit to basic confidence range [0, 1] if needed, or store as raw logit
                confidence = float(rerank_score)

                valid_citations.append({
                    "chunk_id": chunk.id,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "confidence_score": confidence,
                })

        return valid_citations

    async def save_citations(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        citations_data: list[dict[str, Any]],
    ) -> list[Citation]:
        """Persist citations associated with a message in the database."""
        citations = []
        for data in citations_data:
            citation = Citation(
                message_id=message_id,
                chunk_id=data["chunk_id"],
                page_number=data["page_number"],
                section_title=data["section_title"],
                confidence_score=data["confidence_score"],
            )
            db.add(citation)
            citations.append(citation)

        if citations:
            await db.flush()  # flush to DB to get IDs
            logger.info("citations_persisted", message_id=str(message_id), count=len(citations))
        return citations
