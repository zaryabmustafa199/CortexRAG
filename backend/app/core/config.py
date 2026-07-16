"""
app/core/config.py
------------------
Centralised settings loaded from environment variables via pydantic-settings.
All configuration is validated at startup — if a required value is missing or
invalid the application refuses to start.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "production"] = "development"
    APP_VERSION: str = "0.1.0"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:8080",
    ]

    # ── Security ─────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str          # postgresql+asyncpg://...
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str             # redis://redis:6379/0
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # ── MinIO ─────────────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "cortexrag-documents"
    MINIO_SECURE: bool = False

    # ── Elasticsearch ─────────────────────────────────────────────────────────
    ELASTICSEARCH_URL: str = "http://elasticsearch:9200"
    ELASTICSEARCH_INDEX_CHUNKS: str = "cortexrag_chunks"

    # ── AI Provider ───────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["ollama", "openai"] = "ollama"
    LLM_MODEL: str = "llama3"
    EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIM: int = 768

    OLLAMA_BASE_URL: str = "http://ollama:11434"

    # OpenAI (only required when LLM_PROVIDER=openai)
    OPENAI_API_KEY: str = ""
    OPENAI_LLM_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBED_DIM: int = 1536

    # ── File Upload Limits ─────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB_FREE: int = 10
    MAX_UPLOAD_SIZE_MB_PRO: int = 50
    MAX_DOCS_FREE: int = 5
    MAX_DOCS_PRO: int = 100
    MAX_QUERIES_MONTHLY_FREE: int = 100
    MAX_QUERIES_MONTHLY_PRO: int = 5000

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_not_be_placeholder(cls, v: str) -> str:
        """Refuse to start if JWT_SECRET was not changed from the example value."""
        if v == "CHANGE_ME_generate_with_secrets_token_urlsafe_64" or len(v) < 32:
            print(
                "\n[FATAL] JWT_SECRET is insecure or not set.\n"
                "Generate one with:  python -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
                "Then set it in your .env file.\n",
                file=sys.stderr,
            )
            sys.exit(1)
        return v

    @model_validator(mode="after")
    def openai_key_required_if_provider_openai(self) -> "Settings":
        """When LLM_PROVIDER=openai the API key must be present."""
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            print(
                "\n[FATAL] LLM_PROVIDER is 'openai' but OPENAI_API_KEY is empty.\n"
                "Either set OPENAI_API_KEY or switch LLM_PROVIDER=ollama.\n",
                file=sys.stderr,
            )
            sys.exit(1)
        return self

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def active_embed_dim(self) -> int:
        """Return the embedding dimension for the active provider."""
        if self.LLM_PROVIDER == "openai":
            return self.OPENAI_EMBED_DIM
        return self.EMBED_DIM


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    Call get_settings() anywhere in the app instead of instantiating directly.
    Use FastAPI's Depends(get_settings) in routes.
    """
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()
