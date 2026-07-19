"""
app/services/query_rewriter.py
-------------------------------
Conversational query rewriter.
Rewrites follow-up questions into standalone queries based on message history.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import LLMProviderException
from app.models.query import Message

logger = structlog.get_logger()


class QueryRewriter:
    async def rewrite(self, history: list[Message], current_query: str) -> str:
        """
        Rewrite query to resolve pronouns and context based on last 5 messages.
        If no history exists, returns the current query unmodified.
        """
        if not history:
            return current_query

        # Build history string from last 5 messages
        history_sents = []
        for msg in history[-5:]:
            role_label = "User" if msg.role == "user" else "Assistant"
            history_sents.append(f"{role_label}: {msg.content}")
        history_str = "\n".join(history_sents)

        system_instruction = (
            "Given the following conversation history, rewrite the user's latest follow-up question "
            "into a self-contained, standalone search query. Do NOT answer the question. "
            "Output ONLY the rewritten standalone question and nothing else."
        )
        prompt = (
            f"History:\n{history_str}\n\nLatest Question: {current_query}\n\nStandalone Question:"
        )

        try:
            if settings.LLM_PROVIDER == "openai":
                return await self._openai_rewrite(system_instruction, prompt, current_query)
            return await self._ollama_rewrite(system_instruction, prompt, current_query)
        except Exception as exc:
            logger.warning("query_rewrite_failed_fallback", error=str(exc))
            # Fallback open: return original user query if LLM rewriting fails
            return current_query

    async def _ollama_rewrite(self, system: str, prompt: str, fallback: str) -> str:
        async with httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=5.0, pool=5.0),
        ) as client:
            response = await asyncio.wait_for(
                client.post(
                    "/api/generate",
                    json={
                        "model": settings.LLM_MODEL,
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.0,
                            "num_predict": 40,
                            "num_ctx": 1024,
                        },
                    },
                ),
                timeout=120.0,
            )
            if response.status_code != 200:
                raise LLMProviderException(f"Ollama returned status {response.status_code}")
            return str(response.json().get("response", fallback)).strip()

    async def _openai_rewrite(self, system: str, prompt: str, fallback: str) -> str:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        ) as client:
            response = await asyncio.wait_for(
                client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": settings.OPENAI_LLM_MODEL,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.0,
                    },
                ),
                timeout=15.0,
            )
            if response.status_code != 200:
                raise LLMProviderException(f"OpenAI returned status {response.status_code}")
            return str(response.json()["choices"][0]["message"]["content"]).strip()
