# Step 01 — Project Setup & Infrastructure

## What You're Building
The complete Docker infrastructure and FastAPI application skeleton that all subsequent steps build on. After this step, every service (Postgres, Redis, MinIO, Elasticsearch, Ollama, Caddy) is running and healthy, and the FastAPI app boots with the full middleware stack, structured logging, and exception handling already wired up.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Multi-stage Dockerfile** | A Dockerfile with multiple `FROM` blocks — each stage builds on the previous and discards build artefacts | Keeps production image small and secure; development stage has hot-reload |
| **Docker Network Isolation** | Two separate Docker bridge networks: `app` (internet-capable) and `worker` (internal only) | Celery workers that parse untrusted PDFs cannot make outbound internet calls (prevents SSRF / XXE exfiltration) |
| **Correlation ID** | A unique identifier (`secrets.token_urlsafe(16)`) attached to every HTTP request | Enables end-to-end tracing across API logs, Celery worker logs, and error responses without a full APM setup |
| **structlog** | Structured logging library that outputs JSON log lines with consistent fields | Makes logs machine-parseable for Grafana Loki / Datadog without regex parsing |
| **pydantic-settings** | Reads env vars and `.env` files into a typed, validated Python class | App refuses to start if required config is missing or insecure (e.g. weak JWT secret) |
| **RLS (Row-Level Security)** | PostgreSQL feature: attaches a USING clause to every query so rows not matching `app.workspace_id` are invisible | Database-level tenant isolation — a missing `.filter()` in application code cannot leak cross-tenant data |
| **CORS Middleware** | Browser security policy enforcement — only allows requests from configured origins | Prevents malicious third-party sites from silently sending authenticated requests to your API |

---

## Files Created

| File | Role |
|---|---|
| `docker-compose.yml` | Defines all 8 services with health checks, networks, volumes |
| `.env.example` | Environment variable template — copy to `.env` before running |
| `.gitignore` | Prevents secrets and build artefacts from being committed |
| `caddy/Caddyfile` | Reverse proxy config — routes port 80 to FastAPI backend |
| `scripts/init_db.sql` | Postgres init — enables `pgvector` and `uuid-ossp` extensions |
| `scripts/ollama_pull.sh` | Pulls `nomic-embed-text` and `llama3` models on Ollama start |
| `backend/Dockerfile` | Multi-stage image: `development` (hot-reload) and `production` (non-root) |
| `backend/pyproject.toml` | Poetry dependency manifest with all libraries pinned |
| `backend/app/main.py` | FastAPI app factory — middleware stack + exception handlers + /health |
| `backend/app/core/config.py` | Settings class — validates all env vars at startup |
| `backend/app/core/exceptions.py` | Full typed exception hierarchy (all 20 exception classes) |
| `backend/app/core/logging.py` | structlog configuration — JSON in prod, pretty in dev |
| `backend/app/core/middleware.py` | `CorrelationIDMiddleware` + `RLSContextMiddleware` |
| `backend/app/db/session.py` | Async SQLAlchemy engine + RLS-aware session factory |
| `backend/app/db/base.py` | DeclarativeBase — Alembic discovers models from here |

---

## Engineering Standards Applied (§5)

- **`secrets.token_urlsafe(16)`** — correlation ID generation in `CorrelationIDMiddleware`
- **`secrets.token_urlsafe(64)`** — JWT secret (enforced by config validator)
- **Startup validation** — `config.py` calls `sys.exit(1)` on insecure/missing config
- **`asyncio.sleep`** — all middleware uses async-native patterns
- **CORS no wildcard** — `allow_origins=settings.CORS_ORIGINS` (from env), never `"*"`
- **Pool config** — `pool_size=20, max_overflow=10, pool_recycle=1800, pool_pre_ping=True`
- **RLS activation** — `SET LOCAL app.workspace_id = '...'` on every DB session

---

## How to Run This Step

### 1. Copy the environment file and generate a secure JWT secret
```bash
cp .env.example .env

# Generate a secure JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Paste the output as JWT_SECRET in .env
```

### 2. Build and start all services
```bash
docker compose up --build -d
```

### 3. Watch logs until all services are healthy
```bash
docker compose ps          # all should show "healthy"
docker compose logs backend --follow
```

### 4. Verify the API is running
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.1.0"}

curl http://localhost/health   # via Caddy reverse proxy
# Expected: {"status":"ok","version":"0.1.0"}
```

### 5. Verify structured logging
The backend logs should look like (in dev, pretty format):
```
[INFO ] application_starting env=development version=0.1.0 llm_provider=ollama
[INFO ] http_request method=GET path=/health status=200 duration_ms=1.2 correlation_id=abc123
```

### 6. Verify MinIO bucket was created
```
Open http://localhost:9001 in browser
Login: MINIO_ACCESS_KEY / MINIO_SECRET_KEY from .env
Navigate to Buckets → cortexrag-documents should exist and be private
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `[FATAL] JWT_SECRET is insecure` | `.env` still has placeholder value | Generate with `secrets.token_urlsafe(64)` and paste into `.env` |
| `backend` stays unhealthy | Postgres still starting up | Wait 30s — backend retries until postgres health check passes |
| `minio_init` exits with error | MinIO not healthy yet | Increase `start_period` in MinIO healthcheck or re-run `docker compose up` |
| `ollama` health check fails | Model download still in progress | `llama3` is ~4GB — wait 5–10 min on first pull. Check `docker compose logs ollama` |
| `connection refused` on port 8000 | Backend crashed on startup | Run `docker compose logs backend` — usually a missing env var |
| `ModuleNotFoundError` | Poetry lock file missing | Run `poetry lock` inside `backend/` then rebuild |

---

## What's Next

**Step 2** — Write all SQLAlchemy models (User, Workspace, Document, Chunk, etc.) and run Alembic migrations to create the tables with RLS policies and HNSW indexes in PostgreSQL.
