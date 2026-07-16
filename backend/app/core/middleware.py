"""
app/core/middleware.py
----------------------
Custom ASGI middleware stack applied in main.py.

Order matters — applied bottom-up by Starlette (last added = first executed).
Raw ASGI middleware is used instead of BaseHTTPMiddleware because BaseHTTPMiddleware
breaks WebSocket connections by failing to handle ASGI WebSocket protocols properly.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, MutableMapping

import structlog
from starlette.types import ASGIApp, Scope, Receive, Send

logger = structlog.get_logger()


class CorrelationIDMiddleware:
    """
    Reads X-Correlation-ID from incoming request headers.
    If absent, generates a cryptographically secure one.
    Attaches it to scope['state']['correlation_id'] and echoes it back in response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Direct bypass for WebSockets and other connection types
            await self.app(scope, receive, send)
            return

        correlation_id = secrets.token_urlsafe(16)
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-correlation-id":
                correlation_id = value.decode(errors="ignore")
                break

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["correlation_id"] = correlation_id

        # Bind to structlog context vars
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        start = time.perf_counter()
        status_code = [200]  # mutable container to store status_code

        async def send_wrapper(event: MutableMapping[str, Any]) -> None:
            if event["type"] == "http.response.start":
                status_code[0] = event.get("status", 200)
                headers = event.get("headers", [])
                if not any(h[0].lower() == b"x-correlation-id" for h in headers):
                    headers.append((b"X-Correlation-ID", correlation_id.encode()))
                event["headers"] = headers
            await send(event)

        await self.app(scope, receive, send_wrapper)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        path = scope.get("path", "")
        if path != "/health":
            logger.info(
                "http_request",
                method=scope.get("method", ""),
                path=path,
                status=status_code[0],
                duration_ms=duration_ms,
            )


class RLSContextMiddleware:
    """
    Ensures workspace_id is initialized in the request state.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["workspace_id"] = scope["state"].get("workspace_id", "")
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """
    Applies security headers to HTTP responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(event: MutableMapping[str, Any]) -> None:
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                headers.append((b"X-Content-Type-Options", b"nosniff"))
                headers.append((b"X-Frame-Options", b"DENY"))
                headers.append((b"X-XSS-Protection", b"0"))
                headers.append((b"Content-Security-Policy", b"default-src 'none'; frame-ancestors 'none'; sandbox"))
                headers.append((b"Strict-Transport-Security", b"max-age=31536000; includeSubDomains"))
                event["headers"] = headers
            await send(event)

        await self.app(scope, receive, send_wrapper)

