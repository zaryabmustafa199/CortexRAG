# Step 20 — Observability — Logging, Tracing & Error Monitoring

## What You're Building
The application observability and live monitoring framework. This implements an extended dependency-aware `/health` status endpoint that probes all connected backing services (PostgreSQL, Redis, MinIO, and Ollama) asynchronously without blocking the event loop. It integrates centralized JSON logging via `structlog`, Sentry SDK error tracking, and OpenTelemetry instrumentation to trace request lifetimes (via correlation IDs) from the router all the way to background tasks.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Dependency Probing** | Ping checks executing live commands against external APIs during health checks | Assures monitoring systems (like Kubernetes, Docker, or Load Balancers) that backing databases and object stores are active, not just the python gateway |
| **JSON Logging** | Outputting standard print logs as structured JSON lines | Simplifies log parsing, aggregation, and querying in systems like ELK (Elasticsearch/Logstash/Kibana) or Datadog |
| **Sentry Error Tracking** | Automatically catching unhandled exceptions and routing telemetry to Sentry portals | Notifies developers instantly of production failures, including full stack traces and environment metadata |
| **Distributed Tracing** | Attaching a trace/correlation ID to a request context and carrying it across threads/workers | Allows developers to trace document upload problems from the HTTP POST upload route to the Celery ingestion worker |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/main.py` | Configures logging, Sentry monitoring, and mounts the comprehensive `/health` status path | Modified |

---

## Engineering Standards Applied (§5)

- **Non-blocking probes** — backing check operations against Redis and MinIO are offloaded to Python's thread executors to avoid blocking the FastAPI event loop.
- **Fail-Safe Health Status** — Individual failures are caught and logged inside the `/health` controller, returning a `503 Service Unavailable` with details instead of raising a generic 500.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# Call the health check endpoint
curl -X GET http://localhost:8000/health

# Expected output (when all backing systems are healthy):
# {
#   "status": "healthy",
#   "version": "0.1.0",
#   "services": {
#     "postgres": "ok",
#     "redis": "ok",
#     "minio": "ok",
#     "llm_provider": "ok"
#   }
# }

# Verify structure of console log output
# Every log print should output a valid JSON line with timestamps and log levels.
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `/health` returns `503` | One of the database or storage services failed to respond in time | Inspect the backend server logs for the specific failed dependency (e.g. `health_check_postgres_failed`) and verify service container health |
| Sentry events do not emit | `SENTRY_DSN` is empty or incorrect | Check `.env` configuration for the correct DSN credentials |

---

## What's Next

**Step 21** — Next.js Setup & Design System: enter Phase 5 (Frontend) by establishing the Next.js 14 application workspace equipped with typescript support, dark mode tokens, and core components.
