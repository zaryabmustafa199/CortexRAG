# Step 15 — Citation Engine & Cache Invalidation

## What You're Building
A robust, validated citation attribution system and a secure, multi-layer cascade purge mechanism for document deletion. The citation service parses LLM response text for `[Source N]` tags, validates them against the list of retrieved context chunks, and persists them to the database. The document purge service coordinates deletion across all layers of the stack: removing file binaries from MinIO, deleting chunk records from Elasticsearch by query, invalidating Redis query caches under the tenant workspace namespace, and cascading database deletions in pgvector/SQL (chunks, embeddings, and documents) under strict Row-Level Security (RLS).

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Citation Attribution** | Parsing tags like `[Source N]` from generated text and mapping them back to database LeafChunk records | Provides source transparency and verifiability for all AI answers, establishing trust |
| **Cascade Purging** | Coordinating deletion across SQL database, pgvector, object storage, BM25 indices, and key-value caches | Prevents orphaned binary files, dead vector embeddings, stale keyword index records, or dirty cache reads |
| **Cache Invalidation** | Automatically clearing the workspace-scoped query cache when workspace documents change | Prevents old data from being retrieved out of cache after a document has been deleted or updated |
| **RLS Boundaries** | Enforcing tenant isolation during document deletion | Ensures a tenant can only delete and cascade documents belonging to their own workspace |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/citation_service.py` | Parsers and validators mapping `[Source N]` to LeafChunks and database citations | Created |
| `app/services/document_lifecycle.py` | Orchestrator executing multi-layer cascading document purge | Created |
| `app/api/v1/query.py` | Integrates `CitationService` to extract and save citations on streaming query completion | Modified |
| `app/api/v1/documents.py` | Exposes `DELETE /documents/{document_id}` endpoint mapping to `DocumentLifecycleService` | Modified |

---

## Engineering Standards Applied (§5)

- **Atomic Transactions** — SQL cascade deletions are executed atomically within the SQLAlchemy session scope.
- **Graceful Failures** — Third-party service purge failures (e.g., Elasticsearch, MinIO, Redis) are logged as errors but do not block the database transaction from completing.
- **Executor Offloading** — Blocking operations like scanning Redis keys are executed asynchronously where possible to keep the event loop unblocked.
- **RLS isolation** — Connection session variables are populated with the workspace ID before deletions, ensuring RLS checks are run at the Postgres engine level.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# Submit a RAG query to generate a citation
curl -X POST http://localhost:8000/api/v1/query/ask \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id": "<workspace_uuid>", "question": "Compare the architectures of the documents"}'

# Verify in database that citations were saved:
# SELECT * FROM citations WHERE message_id = '<message_uuid>';

# Purge a document
curl -X DELETE "http://localhost:8000/api/v1/documents/<document_uuid>?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"

# Verify cascade:
# 1. Document record is deleted in database (cascades chunks/embeddings)
# 2. Redis cache for workspace is cleared: redis-cli KEYS "cache:<workspace_uuid>:*"
# 3. Elasticsearch index lacks chunk IDs: curl -X GET "http://localhost:9200/chunks/_search" -d '{"query":{"ids":{"values":["<chunk_id>"]}}}'
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `elasticsearch_purge_failed` | Elasticsearch service is down or index connection was lost | Ensure Elasticsearch container is running and healthy; the API logs the error and continues database cleanups |
| `minio_purge_failed` | MinIO bucket object not found or storage API timeout | Verify bucket policies and object keys; verify container network connectivity |
| `redis_cache_invalidation_failed` | Redis connection is down or scan iteration timed out | Check Redis container logs; the delete request will proceed but query caches may persist until TTL expiry |

---

## What's Next

**Step 16** — Usage Tracking & Quota Enforcement: track API query counts and token usage per workspace, enforcing limits based on user subscription tiers (Free vs. Pro).
