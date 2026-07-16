"""
app/services/summary_service.py
-------------------------------
Service for generating section summaries for ParentChunks using Ollama or OpenAI.
Enforces a 3-retry configuration on timeout errors.
"""
from __future__ import annotations

import asyncio
import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import LLMProviderException

logger = structlog.get_logger()


class SummaryService:
    async def summarize_text(self, text: str) -> str:
        """
        Generate a concise summary of the text using the configured LLM.
        """
        if not text.strip():
            return ""

        if settings.LLM_PROVIDER == "openai":
            return await self._openai_summary(text)
        return await self._ollama_summary(text)

    async def _ollama_summary(self, text: str) -> str:
        prompt = (
            "Summarize the following document section in 2-3 concise sentences. "
            "Focus only on key facts, numbers, and dates. Do not include introductory text.\n\n"
            f"Content:\n{text}"
        )
        
        async with httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=15.0, pool=10.0)
        ) as client:
            for attempt in range(1, 4):  # Retry up to 3 times
                try:
                    response = await asyncio.wait_for(
                         client.post(
                             "/api/generate",
                             json={"model": settings.LLM_MODEL, "prompt": prompt, "stream": False}
                         ),
                         timeout=300.0
                    )
                    if response.status_code != 200:
                        raise LLMProviderException(f"Ollama returned status {response.status_code}")
                    return str(response.json().get("response", "")).strip()
                except asyncio.TimeoutError:
                    logger.warning("ollama_summary_timeout", attempt=attempt)
                    if attempt == 3:
                        raise LLMProviderException("Ollama summarization timed out after 3 attempts.")
                except Exception as exc:
                    logger.warning("ollama_summary_failed", attempt=attempt, error=str(exc))
                    if attempt == 3:
                        raise LLMProviderException(f"Ollama summarization failed: {str(exc)}")
        return ""

    async def _openai_summary(self, text: str) -> str:
        prompt = (
            "Summarize the following document section in 2-3 concise sentences. "
            "Focus only on key facts, numbers, and dates. Do not include introductory text."
        )
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=15.0, pool=10.0)
        ) as client:
            for attempt in range(1, 4):
                try:
                    response = await asyncio.wait_for(
                        client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                            json={
                                "model": settings.OPENAI_LLM_MODEL,
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": text}
                                ],
                                "temperature": 0.3,
                            }
                        ),
                        timeout=60.0
                    )
                    if response.status_code != 200:
                        raise LLMProviderException(f"OpenAI returned status {response.status_code}")
                    return str(response.json()["choices"][0]["message"]["content"]).strip()
                except asyncio.TimeoutError:
                    logger.warning("openai_summary_timeout", attempt=attempt)
                    if attempt == 3:
                        raise LLMProviderException("OpenAI summarization timed out after 3 attempts.")
                except Exception as exc:
                    logger.warning("openai_summary_failed", attempt=attempt, error=str(exc))
                    if attempt == 3:
                        raise LLMProviderException(f"OpenAI summarization failed: {str(exc)}")
        return ""
