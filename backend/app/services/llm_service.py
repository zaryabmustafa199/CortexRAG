"""
app/services/llm_service.py
---------------------------
LLM generation service.
Supports streaming responses from Ollama (local) and OpenAI.
Implements unified stream generators yielding tokens with strict timeouts.
"""
from __future__ import annotations

import json
import asyncio
import httpx
import structlog
from typing import AsyncGenerator

from app.core.config import settings
from app.core.exceptions import LLMProviderException

logger = structlog.get_logger()


class LLMService:
    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from the configured LLM provider (Ollama or OpenAI).
        Yields raw text tokens.
        """
        if settings.LLM_PROVIDER == "openai":
            async for token in self._stream_openai(prompt, system_prompt):
                yield token
        else:
            async for token in self._stream_ollama(prompt, system_prompt):
                yield token

    async def _stream_ollama(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response from Ollama generate API."""
        url = "/api/generate"
        payload = {
            "model": settings.LLM_MODEL,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096,
                "num_predict": 512,
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(connect=5.0, read=300.0, write=15.0, pool=10.0)

        try:
            async with httpx.AsyncClient(
                base_url=settings.OLLAMA_BASE_URL,
                limits=limits,
                timeout=timeout,
            ) as client:
                # Use stream context manager to stream response lines
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        raise LLMProviderException(f"Ollama returned status {response.status_code}: {err_body.decode()}")

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break
        except asyncio.TimeoutError as exc:
            logger.error("ollama_stream_timeout")
            raise LLMProviderException("Ollama response stream timed out.") from exc
        except Exception as exc:
            if isinstance(exc, LLMProviderException):
                raise exc
            logger.error("ollama_stream_failed", error=str(exc))
            raise LLMProviderException(f"Ollama stream connection failed: {str(exc)}")

    async def _stream_openai(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI Chat Completions API."""
        url = "https://api.openai.com/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.OPENAI_LLM_MODEL,
            "messages": messages,
            "stream": True,
            "temperature": 0.3,
        }

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=15.0, pool=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        raise LLMProviderException(f"OpenAI returned status {response.status_code}: {err_body.decode()}")

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        
                        # Strip "data: " prefix
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        
                        delta = choices[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
        except asyncio.TimeoutError as exc:
            logger.error("openai_stream_timeout")
            raise LLMProviderException("OpenAI response stream timed out.") from exc
        except Exception as exc:
            if isinstance(exc, LLMProviderException):
                raise exc
            logger.error("openai_stream_failed", error=str(exc))
            raise LLMProviderException(f"OpenAI stream connection failed: {str(exc)}")
