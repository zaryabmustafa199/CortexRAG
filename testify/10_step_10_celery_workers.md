# Step 10 — Celery Task Queue & Worker Health

## What You're Building
A fully asynchronous background task runner powered by Celery and Redis. It handles long-running, CPU-intensive document processing pipelines (download, extraction, hierarchical chunking, section summarization, and embedding generation) and user deletion/GDPR data purges without impacting the response latency of API routers. It propagates correlation identifiers across all workers, publishes job updates to Redis Pub/Sub, and handles final failure state transitions and exponential retries.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Task Queue (Celery)** | Offloads intensive work (I/O, network calls, LLM inference) to concurrent worker processes | Prevents web server requests from hanging while processing heavy tasks like document ingestion |
| **Worker Process Recycle** | Automatically recycling individual Celery worker child processes after completing 50 tasks (`worker_max_tasks_per_child=50`) | Mitigates Python memory fragmentation and prevents silent OOM (Out Of Memory) container crashes |
| **Exponential Backoff Retries** | Retrying failed tasks with progressively longer wait periods (e.g. $2^{retry} + 2$ seconds) | Handles transient system outages (e.g. database locks or network timeouts) gracefully without overwhelming dependencies |
| **Cascade File Deletion** | Purging physical files (MinIO binaries) prior to committing DB drops | Prevents object storage leakages and ensures GDPR data hygiene compliance |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/summary_service.py` | LLM Section summarizer routing to Ollama/OpenAI with a 3-retry timeout gate | Created |
| `app/worker/celery_app.py` | Celery application setup with process recycles and late ACKs | Modified (completed) |
| `app/worker/tasks/ingestion.py` | Master `ingest_document` task orchestrating the extraction/chunking/embedding pipeline | Modified (completed) |
| `app/worker/tasks/cleanup.py` | Background cleanup task (`cleanup_user_data`) executing user-owned asset purges | Created |
| `app/services/user_service.py` | Dispatches the user data cleanup task on account deactivation | Modified |
| `app/worker/tasks/__init__.py` | Exports Celery tasks | Modified |

---

## Engineering Standards Applied (§5)

- **Late Acknowledgements** — Task ACKs occur only after successful pipeline resolution (`task_acks_late=True`), ensuring tasks are redelivered rather than lost if a container crashes mid-execution.
- **Fail-Open LLM Failures** — Wraps parent chunk section summarization in a try-except block; summary generation failures do not abort the entire document pipeline.
- **Permanent Failure Transition** — Detects final retry exhaustion (`self.request.retries >= self.max_retries`) and transitions the document/job states to `FAILED` in the database, preventing indefinite processing lock states.
- **Redis Pub/Sub Completion Alerts** — Publishes structured JSON completion/failure payloads to `cortex:notify:{workspace_id}` channels to push instant notifications to the client.

---

## How to Test This Step

```bash
# Start background worker and broker containers
docker compose up -d redis minio postgres worker

# Trigger a document ingestion by calling the upload API:
curl -X POST "http://localhost:8000/api/v1/documents/upload?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@sample.pdf"

# View Celery worker logs to trace the orchestration steps:
docker compose logs -f worker

# Expected:
# [info] ingestion_task_received job_id=...
# [info] extraction_started document_id=...
# [info] parent_chunk_summarization_success parent_id=...
# [info] embedding_completed embeddings_count=...
# [info] ingestion_pipeline_success job_id=...
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `ingestion_task_retrying` | Redis connection timed out or database lock occurred | Enforced exponential backoff retries task parameters; wait for the task to succeed on the next attempt |
| Worker process dies silently | Processing massive documents (500+ pages) exceeded RAM boundaries | Ensure memory limits are not hit by using page-by-page streaming generators rather than full-file reads |
| `DOCUMENT_FAILED` in database | One of the core parsing or embedding steps threw a domain exception | View `error_message` in the `documents` table to see the exact exception detail |

---

## What's Next

**Phase 3: RAG Engine** — Step 11: Vector Search: build pgvector-optimized cosine distance queries to retrieve top leaf chunk vectors inside isolated workspace boundaries.
