"""
app/services/embedding_service.py
---------------------------------
Embedding generation service.
Supports Ollama (local) and OpenAI (cloud fallback) providers.
Batches text embedding requests and enforces strict timeouts.
"""
from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any, cast

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import EmbeddingException

logger = structlog.get_logger()


def chunks(lst: list[Any], n: int) -> Generator[list[Any], None, None]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class EmbeddingService:
    @property
    def active_model_name(self) -> str:
        """Return the name of the active embedding model."""
        if settings.LLM_PROVIDER == "openai":
            return settings.OPENAI_EMBED_MODEL
        return settings.EMBED_MODEL

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.
        Automatically routes to active provider (Ollama or OpenAI).
        """
        if not texts:
            return []

        if settings.LLM_PROVIDER == "openai":
            return await self._openai_embed(texts)
        return await self._ollama_embed(texts)

    async def _ollama_embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings using local Ollama service.
        Batches texts and calls the API concurrently using asyncio.gather.
        """
        results: list[list[float]] = []
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=30)

        async with httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=10.0),
            limits=limits,
        ) as client:
            # Batch prompts in groups of 32
            for batch in chunks(texts, 32):
                tasks = [self._single_ollama_embed(client, text) for text in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for res in batch_results:
                    if isinstance(res, Exception):
                        logger.error("ollama_embedding_batch_failure", error=str(res))
                        raise EmbeddingException(f"Ollama batch embedding failed: {str(res)}")
                    # cast() tells mypy res is list[float] after the Exception check above
                    results.append(cast(list[float], res))

        return results

    async def _single_ollama_embed(self, client: httpx.AsyncClient, text: str) -> list[float]:
        """Generate a single embedding via Ollama with timeout."""
        try:
            response = await asyncio.wait_for(
                client.post(
                    "/api/embeddings",
                    json={"model": settings.EMBED_MODEL, "prompt": text}
                ),
                timeout=300.0
            )
            if response.status_code != 200:
                raise EmbeddingException(f"Ollama returned status {response.status_code}: {response.text}")

            return cast(list[float], response.json()["embedding"])
        except TimeoutError:
            raise EmbeddingException("Ollama embedding request timed out.")
        except Exception as exc:
            if isinstance(exc, EmbeddingException):
                raise exc
            raise EmbeddingException(f"Ollama connection error: {str(exc)}")

    async def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings using OpenAI API.
        Sends batched inputs in single requests for performance and cost.
        """
        results = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=10.0)
        ) as client:
            # Batch inputs in groups of 32
            for batch in chunks(texts, 32):
                try:
                    response = await asyncio.wait_for(
                        client.post(
                          "https://api.openai.com/v1/embeddings",
                          headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                          json={"model": settings.OPENAI_EMBED_MODEL, "input": batch}
                        ),
                        timeout=30.0
                    )

                    if response.status_code != 200:
                        raise EmbeddingException(f"OpenAI returned status {response.status_code}: {response.text}")

                    data = response.json()["data"]
                    # Sort by index to preserve order
                    data_sorted = sorted(data, key=lambda x: x["index"])
                    results.extend([item["embedding"] for item in data_sorted])

                except TimeoutError:
                    raise EmbeddingException("OpenAI embedding request timed out.")
                except Exception as exc:
                    if isinstance(exc, EmbeddingException):
                        raise exc
                    raise EmbeddingException(f"OpenAI connection error: {str(exc)}")

        return results
