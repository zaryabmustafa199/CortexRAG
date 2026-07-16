# Step 18 — Document Management API (Full CRUD)

## What You're Building
The complete lifecycle management API for documents. This step exposes endpoints to retrieve a workspace's documents (paginated), retrieve metadata + presigned URLs for single files, check processing job status, cascade delete records from the workspace, and inspect hierarchical database chunks (both parent and leaf objects) directly for transparency and debugging.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Eager Loading** | Loading relationship data upfront using SQLAlchemy's `selectinload` | Avoids standard N+1 lazy loading issues on child leaf arrays in an async database context |
| **Presigned URL Expiry** | Generating time-restricted S3/MinIO URLs dynamically during document detail requests | Protects document access by keeping raw object storage endpoints private |
| **Hierarchical Inspection** | Exposing API paths that output structural Parent and Child chunks | Crucial for transparency, allowing engineers and advanced users to audit chunking quality |
| **Polling Mechanism** | Standardizing task job statuses so frontend clients can monitor ingestion status | Essential for providing updates during long-running async worker tasks (e.g. OCR, parsing) |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/schemas/documents.py` | Pydantic response models for single document details and chunk structures | Modified |
| `app/api/v1/documents.py` | Adds endpoints for document listing, detail, job status, and chunk inspection | Modified |

---

## Engineering Standards Applied (§5)

- **SQLAlchemy `selectinload`** — Used to eagerly load nested `leaf_chunks` collections from PostgreSQL in a single async query, avoiding event-loop blocking.
- **Fail-Safe Fallbacks** — The status endpoint yields status indicators from the Document table directly if the celery `UploadJob` record is absent.
- **Strict multi-tenancy** — All endpoints resolve database queries using the `get_rls_db` dependency to guarantee strict workspace boundaries.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# List documents in a workspace
curl -X GET "http://localhost:8000/api/v1/documents?workspace_id=<workspace_uuid>&limit=10" \
  -H "Authorization: Bearer <access_token>"

# Get details & presigned URL for a single document
curl -X GET "http://localhost:8000/api/v1/documents/<document_uuid>?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"

# Expected output:
# {
#   "document": { ... },
#   "download_url": "http://minio:9000/...",
#   "expires_in_seconds": 600
# }

# Poll upload status of document
curl -X GET "http://localhost:8000/api/v1/documents/<document_uuid>/status?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"

# Inspect parsed chunks hierarchy
curl -X GET "http://localhost:8000/api/v1/documents/<document_uuid>/chunks?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `AttributeError: 'ParentChunk' object has no attribute 'leaf_chunks'` | Accessing lazy-loaded attributes inside async context | Ensure the query uses `.options(selectinload(ParentChunk.leaf_chunks))` to eagerly load collections |
| `DocumentNotFoundException` | Document ID does not exist, or user lacks workspace member authorization | Verify the requested UUID is correct and that the workspace RLS session setting matches the document's workspace ID |

---

## What's Next

**Step 19** — Real-Time Notifications: establish Starlette WebSocket routing combined with Redis Pub/Sub channels to push real-time document parsing and completion events instantly to clients.
