# Step 27 — Performance Optimization

## What You're Building
System performance improvements targeting latency and throughput. This step implements Redis RAG query response caching (caching complete generation text and citation metadata in a `cache:{workspace_id}:{hash}` namespace), simulated SSE streaming for cached responses, non-blocking connection pre-warming for Ollama embedding models during system startup, and cursor-based pagination parameters for document lists and message histories.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Redis RAG Caching** | Storing final text and source citations in Redis with a 5-minute TTL | Bypasses slow hybrid searches and LLM generation on repeated identical workspace queries |
| **Simulated SSE Typing** | Emitting tokens from memory over SSE with a artificial 10ms asyncio delay | Preserves the typing user experience for cached response hits |
| **Model Pre-warming** | Triggering dummy embedding generations in a background startup task | Forces Ollama to load weights from disk to RAM early, avoiding 5-10s cold-start delays on the first query |
| **Cursor Pagination** | Paginating using sort-field conditions (e.g. `created_at > timestamp`) | Avoids performance degradation of high-offset SQL queries on large lists |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `backend/app/api/v1/documents.py` | Updates document listing to use timestamp-based cursor query filters | Modified |
| `backend/app/api/v1/query.py` | Implements query cache lookup/writes and cursor message query filters | Modified |
| `backend/app/main.py` | Configures background Ollama model pre-warming task on startup | Modified |

---

## Engineering Standards Applied (§5)

- **Non-blocking Event Loop Execution** — Sync Redis cache actions (`redis_client.get` and `redis_client.setex`) are executed in threads using `loop.run_in_executor`.
- **Asynchronous Pre-warming** — Model loading is wrapped inside a non-blocking background `asyncio.create_task` to prevent delaying route initialization or healthchecks.
- **Cache Namespace Safety** — Cache keys are prefixed with `cache:{workspace_id}:*` to align with the cascade delete namespace purge scanner.

---

## How to Test This Step

```bash
# Verify backend compiles cleanly
python -m py_compile backend/app/main.py backend/app/api/v1/query.py backend/app/api/v1/documents.py

# Run local development servers
npm run dev # inside frontend
uvicorn app.main:app --reload # inside backend

# 1. Ask a question through Chat UI. Observe response streaming (miss).
# 2. Ask the exact same question again in the same workspace.
# 3. Observe instant response speed (cache hit) with identical streaming UI.
# 4. Check backend logs for "query_cache_hit".
# 5. Delete a document from Document UI and verify cache namespace invalidation scans.
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `TypeError: Object of type UUID is not JSON serializable` | Attempted to serialize UUID objects directly to Redis JSON strings | Convert UUID keys (like `chunk_id`) to standard string representation (`str(uuid_val)`) before storing them in Redis |
| Lazy-loading error on cache hit database persist | Citations or chunk relations were accessed out of transaction boundaries | Ensure DB session uses `AsyncSessionLocal()` and applies eager joins when resolving relational fields |
