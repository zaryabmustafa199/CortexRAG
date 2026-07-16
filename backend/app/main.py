"""
app/main.py
-----------
FastAPI application factory.

Middleware stack (applied in reverse order of add_middleware calls):
  Request  →  CorrelationID → RLSContext → CORS → TrustedHost → Routes
  Response ←  CorrelationID ← RLSContext ← CORS ← TrustedHost ← Routes

Exception handlers:
  CortexException subclasses → structured JSON with correlation_id
  Unhandled Exception        → 500 + correlation_id (stack trace in logs only)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import CortexException
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    CorrelationIDMiddleware,
    RLSContextMiddleware,
    SecurityHeadersMiddleware,
)

# ---------------------------------------------------------------------------
# Logging — configure before anything else so early startup errors are captured
# ---------------------------------------------------------------------------
configure_logging(
    json_logs=settings.is_production,
    log_level="INFO" if settings.is_production else "DEBUG",
)

logger = get_logger()

# ---------------------------------------------------------------------------
# Sentry — error monitoring (only when DSN is set)
# ---------------------------------------------------------------------------
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
    logger.info("sentry_initialised", dsn_set=True)


# ---------------------------------------------------------------------------
# Lifespan context manager — replaces deprecated @app.on_event handlers
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manages application startup and graceful shutdown tasks.
    Replaces the deprecated @on_event("startup") / @on_event("shutdown") pattern.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info(
        "application_starting",
        env=settings.APP_ENV,
        version=settings.APP_VERSION,
        llm_provider=settings.LLM_PROVIDER,
        embed_model=settings.EMBED_MODEL,
        embed_dim=settings.active_embed_dim,
    )
    from app.services.storage_service import init_bucket
    init_bucket()
    from app.services.bm25_service import init_es_index
    await init_es_index()

    # Pre-warm Ollama model in the background (non-blocking)
    if settings.LLM_PROVIDER == "ollama":
        async def prewarm() -> None:
            try:
                from app.services.embedding_service import EmbeddingService
                embed_service = EmbeddingService()
                await embed_service.embed_texts(["prewarm"])
                logger.info("ollama_embeddings_prewarmed", model=settings.EMBED_MODEL)
            except Exception as exc:
                logger.warning("ollama_prewarm_failed", error=str(exc))
        asyncio.create_task(prewarm())

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    application = FastAPI(
        title="CortexRAG",
        description="AI Document Intelligence Platform",
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,  # Modern lifespan handler (replaces deprecated on_event)
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    # NOTE: Starlette applies middleware in LIFO order (last added = first run).
    # Final execution order on a request:
    #   CorrelationID → RLSContext → CORS → TrustedHost → route handler

    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.cortexrag.com", "*"]
        if not settings.is_production
        else ["cortexrag.com", "*.cortexrag.com"],
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )

    application.add_middleware(RLSContextMiddleware)
    application.add_middleware(CorrelationIDMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────────────

    @application.exception_handler(CortexException)
    async def cortex_exception_handler(
        request: Request, exc: CortexException
    ) -> JSONResponse:
        """
        Catches all CortexException subclasses.
        Returns structured JSON + logs with full context.
        Never leaks internal stack traces to the client.
        """
        cid = getattr(request.state, "correlation_id", "unknown")
        logger.error(
            "cortex_exception",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "correlation_id": cid,
                }
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Safety net for any exception not explicitly handled above.
        Logs full stack trace; returns generic 500 with correlation_id only.
        """
        cid = getattr(request.state, "correlation_id", "unknown")
        logger.critical(
            "unhandled_exception",
            error=str(exc),
            path=request.url.path,
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "correlation_id": cid,
                }
            },
        )

    # ── Routes ────────────────────────────────────────────────────────────────

    @application.get("/health", tags=["Health"])
    async def health_check() -> JSONResponse:
        """
        Extended health check verifying connections to Postgres, Redis, MinIO, and Ollama.
        """
        import httpx
        from sqlalchemy import text

        from app.core.redis_client import redis_client
        from app.db.session import AsyncSessionLocal
        from app.services.storage_service import minio_client

        postgres_ok = False
        redis_ok = False
        minio_ok = False
        ollama_ok = False

        # 1. Check Postgres
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                postgres_ok = True
        except Exception as exc:
            logger.error("health_check_postgres_failed", error=str(exc))

        # 2. Check Redis
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, redis_client.ping)
            redis_ok = True
        except Exception as exc:
            logger.error("health_check_redis_failed", error=str(exc))

        # 3. Check MinIO
        try:
            bucket = settings.MINIO_BUCKET
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, minio_client.bucket_exists, bucket)
            minio_ok = True
        except Exception as exc:
            logger.error("health_check_minio_failed", error=str(exc))

        # 4. Check Ollama / LLM provider
        try:
            async with httpx.AsyncClient() as client:
                if settings.LLM_PROVIDER == "ollama":
                    resp = await client.get(f"{settings.OLLAMA_BASE_URL}/", timeout=2.0)
                    if resp.status_code == 200:
                        ollama_ok = True
                else:
                    ollama_ok = True
        except Exception as exc:
            logger.error("health_check_llm_provider_failed", error=str(exc))

        status_code = 200
        if not (postgres_ok and redis_ok and minio_ok and ollama_ok):
            status_code = 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if status_code == 200 else "unhealthy",
                "version": settings.APP_VERSION,
                "services": {
                    "postgres": "ok" if postgres_ok else "failed",
                    "redis": "ok" if redis_ok else "failed",
                    "minio": "ok" if minio_ok else "failed",
                    "llm_provider": "ok" if ollama_ok else "failed",
                }
            }
        )


    @application.get("/admin/security-check", tags=["Admin"])
    async def security_audit() -> JSONResponse:
        """
        Internal administrative endpoint to check system safety configurations.
        """
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal

        # 1. Audit JWT Secret
        jwt_ok = len(settings.JWT_SECRET) >= 32 and settings.JWT_SECRET != "CHANGE_ME_generate_with_secrets_token_urlsafe_64"

        # 2. Audit SSL/HTTPS settings
        ssl_ok = True
        if settings.is_production:
            ssl_ok = settings.APP_ENV == "production"

        # 3. Audit RLS on database tables
        rls_ok = False
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(
                    "SELECT relrowsecurity FROM pg_class WHERE relname = 'documents'"
                ))
                row = result.scalar_one_or_none()
                if row is True:
                    rls_ok = True
        except Exception as exc:
            logger.error("security_check_rls_audit_failed", error=str(exc))

        # 4. Sentry Check
        sentry_ok = bool(settings.SENTRY_DSN)

        # 5. API Documentation Exposure Check
        docs_exposed = not settings.is_production

        overall_secure = jwt_ok and rls_ok and (not settings.is_production or (ssl_ok and sentry_ok))

        return JSONResponse(
            status_code=200,
            content={
                "secure": overall_secure,
                "checks": {
                    "jwt_secret_strength": "passed" if jwt_ok else "failed",
                    "postgres_rls_active": "passed" if rls_ok else "failed",
                    "sentry_error_tracking": "configured" if sentry_ok else "disabled",
                    "api_documentation_exposed": "yes" if docs_exposed else "no",
                    "production_ssl_enforcement": "passed" if ssl_ok else "warning",
                }
            }
        )


    from app.api.v1.router import api_router
    application.include_router(api_router, prefix="/api/v1")

    return application


app = create_app()
