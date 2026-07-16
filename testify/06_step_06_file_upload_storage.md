# Step 06 — Secure File Upload & MinIO Storage

## What You're Building
A secure document upload pipeline that validates file sizes, extensions, double-extensions, and magic bytes, before storing files in a private, secure MinIO object bucket. It writes Document and UploadJob records to the database under strict workspace-level Row-Level Security (RLS), and dispatches a Celery task for asynchronous text extraction. It also provides a secure presigned URL generation endpoint for temporarily retrieving document contents.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Magic Bytes Verification** | Checking the initial bytes of a file to verify its true file signature | Prevents attackers from bypassing extensions by naming a shell script `script.sh.pdf` |
| **Double Extension Defense** | Restricting filenames that contain nested executable extensions | Mitigates visual tricks that trick users/parsers into executing malicious code |
| **Object Storage (MinIO)** | Local-first, private S3-compatible bucket storage | Securely stores document binaries out of the SQL database and direct public access |
| **Thread Executor Offloading** | Executing synchronous library calls inside `run_in_executor` | Prevents blocking synchronous I/O operations (like the `minio` library) from halting FastAPI's event loop |
| **Presigned URLs** | Short-lived, digitally signed access links to private objects | Exposes files safely without setting bucket access policies to public, preventing data leaks |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/storage_service.py` | MinIO connection initialization, file uploads, URL generation | Created |
| `app/services/upload_service.py` | Validations (size, double extensions, magic bytes) and DB records setup | Created |
| `app/schemas/documents.py` | Pydantic schemas for Document and UploadJob | Created |
| `app/api/v1/documents.py` | Endpoints: POST /documents/upload and GET /documents/{id}/url | Created |
| `app/worker/celery_app.py` | Celery application setup with task limits | Created |
| `app/worker/tasks/ingestion.py` | Celery document ingestion task stub | Created |
| `app/core/deps.py` | Added RLS database dependency `get_rls_db` | Modified |
| `app/main.py` | Added MinIO bucket check on startup | Modified |
| `app/api/v1/router.py` | Mounted the documents router | Modified |

---

## Engineering Standards Applied (§5)

- **Fail-Fast Validation** — Validates files in memory before doing any database or storage operations.
- **RLS database connection dependency** — `get_rls_db` enforces workspace membership verification and sets local PG context before yielding database connections.
- **Asynchronous Offloading** — Offloads synchronous MinIO calls via Python's default thread executor.
- **Private Presigned TTL** — Presigned URLs expire strictly after 10 minutes (`expires=600`).

---

## How to Test This Step

```bash
# Start the backend services
docker compose up -d

# 1. Upload a valid document (PDF)
curl -X POST "http://localhost:8000/api/v1/documents/upload?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@sample.pdf" | jq .

# Expected:
# {
#   "id": "job_uuid",
#   "document_id": "document_uuid",
#   "status": "QUEUED",
#   ...
# }

# 2. Upload an invalid double-extension file
curl -X POST "http://localhost:8000/api/v1/documents/upload?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@evil.sh.pdf" | jq .
# Expected: 400 InvalidFileException (Double-extension filename structure is not allowed.)

# 3. Retrieve temporary presigned URL for document
curl -X GET "http://localhost:8000/api/v1/documents/<document_uuid>/url?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>" | jq .
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `503 StorageException` | MinIO endpoint is unreachable | Check MinIO docker health: `docker compose ps minio` |
| `400 InvalidFileException` (MIME mismatch) | Genuine file headers do not match target extension | Ensure file contains valid magic header byte structures (e.g. `%PDF-` for PDFs) |
| `403 Forbidden` | User is not a member of the workspace | Check workspace membership or use the correct `workspace_id` parameter |

---

## What's Next

**Step 7** — Text Extraction: write a Celery task that streams text extraction page-by-page from MinIO without causing RAM exhaustion spikes.
