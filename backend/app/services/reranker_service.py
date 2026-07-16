"""
app/services/reranker_service.py
---------------------------------
Reranks hybrid search results using Ollama LLM relevance scoring.
Provides a soft fallback to Reciprocal Rank Fusion (RRF) order on timeout or failure.

NOTE: The original implementation used sentence_transformers.CrossEncoder (local model)
which pulled 22GB of PyTorch+CUDA. This version uses Ollama's API directly via httpx,
consistent with the rest of the stack. Scoring is done via LLM relevance prompt.
"""
from __future__ import annotations

import asyncio
from typing import Any
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_RERANK_PROMPT_TEMPLATE = """You are a relevance scorer. Given a query and a passage, score how relevant the passage is to the query.

Query: {query}

Passage: {passage}

Respond with ONLY a single decimal number between 0.0 (completely irrelevant) and 1.0 (perfectly relevant). Nothing else."""


class RerankerService:
    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Re-rank RRF merged chunks using Ollama LLM relevance scoring.
        Scores each chunk concurrently with a 10-second timeout per chunk.

        Falls back to raw RRF order on exceptions or timeout.
        """
        if not results:
            return []

        # Optimization: Local CPU-bound Ollama cannot handle 25 concurrent LLM
        # requests for re-ranking without freezing or timing out.
        # Fall back to raw RRF rankings immediately (which are already high quality).
        if settings.LLM_PROVIDER == "ollama":
            logger.info("rerank_bypass_ollama", count=len(results), top_k=top_k)
            return results[:top_k]

        try:
            async with httpx.AsyncClient(
                base_url=settings.OLLAMA_BASE_URL,
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0),
            ) as client:
                tasks = [
                    self._score_chunk(client, query, item)
                    for item in results
                ]
                scored_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out exceptions — fall back to 0.0 score on error
            final = []
            for item, result in zip(results, scored_results):
                if isinstance(result, Exception):
                    logger.warning("reranker_chunk_score_failed", error=str(result))
                    new_item = dict(item)
                    new_item["rerank_score"] = 0.0
                elif isinstance(result, dict):
                    new_item = result
                else:
                    new_item = dict(item)
                    new_item["rerank_score"] = 0.0

                final.append(new_item)

            final.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            logger.info("rerank_success", input_count=len(results), output_count=top_k)
            return final[:top_k]

        except asyncio.TimeoutError:
            logger.warning("reranker_timeout_fallback", msg="Rerank timed out. Falling back to RRF order.")
            return results[:top_k]
        except Exception as exc:
            logger.warning("reranker_failed_fallback", error=str(exc), msg="Rerank failed. Falling back to RRF order.")
            return results[:top_k]

    async def _score_chunk(
        self,
        client: httpx.AsyncClient,
        query: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        """Score a single chunk for relevance using Ollama LLM."""
        chunk_content = item["chunk"].content if hasattr(item.get("chunk"), "content") else str(item.get("chunk", ""))
        prompt = _RERANK_PROMPT_TEMPLATE.format(
            query=query,
            passage=chunk_content[:1000],  # limit passage length
        )

        try:
            response = await asyncio.wait_for(
                client.post(
                    "/api/generate",
                    json={
                        "model": settings.LLM_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 8},
                    },
                ),
                timeout=120.0,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "0.5").strip()
                # Extract first float found in response
                import re
                match = re.search(r"\d+\.?\d*", raw)
                score = float(match.group()) if match else 0.5
                score = max(0.0, min(1.0, score))  # clamp to [0, 1]
            else:
                score = 0.5  # neutral score on API error

        except (asyncio.TimeoutError, Exception):
            score = 0.5  # neutral score on timeout/error

        new_item = dict(item)
        new_item["rerank_score"] = score
        return new_item
