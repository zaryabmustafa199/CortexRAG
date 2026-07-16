# CortexRAG — AI Document Intelligence Platform
## Production-Level SaaS Blueprint · Version 2.0 FINAL

> **Status**: Approved — Ready for Implementation  
> **Stack**: Python 3.11 · FastAPI · PostgreSQL + pgvector · Redis · Celery · MinIO · Ollama · Next.js  
> **Deployment**: Docker Compose (local-first, cloud-portable)  
> **Cost**: 100% Free / Open Source Stack (no commercial API required)

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Data Model](#2-data-model)
3. [Core Workflows](#3-core-workflows)
4. [Security & Validation Rules](#4-security--validation-rules)
5. [Engineering Standards (Global Rules)](#5-engineering-standards-global-rules)
6. [Resolved Architecture Issues](#6-resolved-architecture-issues)
7. [Implementation Phases — 30 Steps](#7-implementation-phases--30-steps)
8. [Lesson File Structure](#8-lesson-file-structure)

---

## 1. System Architecture

### 1.1 Layer Stack

```
┌──────────────────────────────────────────────────────────────┐
│  CLIENT LAYER                                                 │
│  Next.js (React) SPA — streaming chat UI, document manager   │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTPS / WSS (TLS 1.3)
┌────────────────────────────▼─────────────────────────────────┐
│  GATEWAY LAYER                                                │
│  Caddy reverse proxy — SSL termination, rate limiting        │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  APPLICATION LAYER — FastAPI (Python 3.11, async)            │
│                                                               │
│  Routers:  /auth  /documents  /query  /workspace  /usage     │
│                                                               │
│  Middleware stack (applied in order):                         │
│    1. CorrelationIDMiddleware  → inject X-Correlation-ID     │
│    2. CORSMiddleware           → strict origin allowlist     │
│    3. JWTAuthMiddleware        → validate Bearer token       │
│    4. RBACMiddleware           → check role permissions      │
│    5. RLSContextMiddleware     → set DB session workspace_id │
└───────────┬─────────────────────────┬────────────────────────┘
            │ sync DB calls           │ enqueue tasks
┌───────────▼──────────┐   ┌──────────▼──────────────────────┐
│  DATA LAYER           │   │  QUEUE LAYER                     │
│                       │   │  Celery workers + Redis broker   │
│  PostgreSQL + pgvector│   │  (isolated Docker network —      │
│  (RLS enabled)        │   │   no outbound internet access)   │
│                       │   │                                  │
│  Redis                │   │  Workers:                        │
│  (cache + pub/sub)    │   │    ingestion_worker              │
│                       │   │    embedding_worker              │
│  MinIO                │   │    notification_worker           │
│  (private S3 buckets) │   │    cleanup_worker                │
│                       │   │                                  │
│  Elasticsearch        │   │  Config:                         │
│  (BM25 full-text)     │   │    max_tasks_per_child = 50      │
└───────────────────────┘   │    acks_late = True              │
                             │    retry: exponential backoff   │
                             └──────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  AI INFERENCE LAYER                                           │
│  Ollama (local)  →  LLM: llama3 / qwen2.5                    │
│                  →  Embeddings: nomic-embed-text (dim=768)    │
│                                                               │
│  [Optional cloud fallback via env var LLM_PROVIDER=openai]   │
│  OpenAI          →  LLM: gpt-4o                              │
│                  →  Embeddings: text-embedding-3-small (1536) │
└──────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  OBSERVABILITY LAYER                                          │
│  structlog (JSON logs) · Sentry (errors) · OpenTelemetry     │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Key Technology Decisions

| Concern | Choice | Reason |
|---|---|---|
| API framework | FastAPI + Python 3.11 | Native async, auto OpenAPI docs, Pydantic v2 |
| Vector store | pgvector (inside PostgreSQL) | No extra infra, HNSW indexing, SQL joins on metadata |
| Embeddings | Ollama `nomic-embed-text` (local) | Free, 768-dim, good quality. OpenAI as optional upgrade |
| LLM | Ollama `llama3` (local) | Free, runs on CPU. Swap via env var |
| Object storage | MinIO | S3-compatible, runs locally in Docker, private buckets |
| Task queue | Celery + Redis | Battle-tested, supports retries, ETA, priorities |
| BM25 search | Elasticsearch | Production-grade, complements vector search |
| Auth tokens | `secrets.token_urlsafe(32)` | Cryptographically secure, not `random` |
| Async waits | `asyncio.sleep` | Never `time.sleep` in async context |
| External calls | `asyncio.wait_for` | Prevents infinite hangs on network drops |
| Parallel tasks | `asyncio.gather(*tasks, return_exceptions=True)` or Python 3.11 `TaskGroup` + `except*` | Structured concurrency, no cascading failures |
| DB queries | SQLAlchemy `.first()` + manual `None` check | Avoids `NoResultFound` crashes; raises typed domain exceptions |
| Multi-tenancy | PostgreSQL Row-Level Security (RLS) | DB-enforced isolation, no application-layer filtering gaps |

---

## 2. Data Model

```
┌─────────────────────────────────────────────────────────────┐
│  User                                                        │
│  id · email · hashed_password · is_active · created_at      │
│  └──► Profile                                                │
│        tier: "free" | "pro"  (mock switch, no Stripe)       │
│        doc_limit · query_limit · storage_limit_mb           │
│  └──► APIKey                                                 │
│        key_hash · name · last_used · is_active              │
│  └──► UsageRecord  (token_count · cost_usd · month)         │
└───────────────────────┬─────────────────────────────────────┘
                        │ owns
┌───────────────────────▼─────────────────────────────────────┐
│  Workspace                                                   │
│  id · name · owner_id · created_at                          │
│  └──► WorkspaceMember  (user_id · role: viewer/editor/admin)│
│  └──► Document                                               │
│        id · workspace_id · filename · storage_key           │
│        status: PENDING|PROCESSING|READY|FAILED              │
│        file_size · mime_type · page_count · created_at      │
│        └──► UploadJob                                        │
│              id · document_id · celery_task_id              │
│              status · error_message · correlation_id        │
│        └──► ParentChunk                                      │
│              id · document_id · content · section_title     │
│              page_start · page_end · token_count            │
│              └──► LeafChunk                                  │
│                    id · parent_id · content · chunk_index   │
│                    token_count · years_detected             │
│                    └──► ChunkEmbedding                       │
│                          id · chunk_id · model_name         │
│                          vector (dynamic dim) · created_at  │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│  QuerySession                                                │
│  id · workspace_id · user_id · title · created_at           │
│  └──► Message                                                │
│        id · session_id · role: user|assistant               │
│        content · tokens_used · created_at                   │
│        └──► Citation                                         │
│              id · message_id · chunk_id · page_number       │
│              section_title · confidence_score               │
│  └──► FeedbackRecord  (rating · comment · created_at)       │
└─────────────────────────────────────────────────────────────┘
```

> **RLS Rule**: Every table with `workspace_id` has a Postgres RLS policy. The API sets `SET LOCAL app.workspace_id = '{id}'` on each DB connection before executing queries. Postgres blocks any row not matching this value automatically.

---

## 3. Core Workflows

### 3.1 User Registration & Onboarding
```
POST /auth/register  {email, password}
    │
    ▼ Validate: RFC5322 email · password strength (8+ chars, upper, digit, symbol)
    │           Use .first() → if user exists → raise ConflictException
    ▼
Hash password (PBKDF2-SHA256)
    ▼
INSERT User + Profile (tier=free, limits applied)
    ▼
Auto-create personal Workspace
    ▼
Return JWT access token (15min) + refresh token (7 days, stored in HttpOnly cookie)
    ▼
Client lands on Dashboard — ready to upload
```

### 3.2 Secure Document Ingestion Pipeline
```
POST /documents/upload  (multipart file)
    │
    ▼ [Sync validation — fail fast, before any I/O]
    │   1. Auth check (JWT valid, user active)
    │   2. Quota check: doc_count < profile.doc_limit
    │   3. File size ≤ profile.storage_limit_mb
    │   4. Extension check: only .pdf / .docx / .txt / .md
    │   5. Regex: reject double-extension filenames (e.g. file.sh.pdf)
    │   6. Magic byte check (python-magic) — read first 2048 bytes
    │      → detected MIME must match declared extension
    │      → mismatch → raise InvalidFileException(400)
    │   7. Sanitize filename → UUID-based storage key
    │
    ▼ [Store]
Store file in MinIO (private bucket, path: {workspace_id}/{uuid}.{ext})
    │
    ▼ [Record & Dispatch]
INSERT Document (status=PENDING) + UploadJob (correlation_id from request)
Enqueue Celery task: ingest_document.delay(job_id, correlation_id)
Return 202 Accepted + job_id (client polls or waits for WebSocket push)
    │
    ▼ [Celery Worker — isolated network]
1. Update status → PROCESSING
2. Download file from MinIO → stream page-by-page (never load full file into RAM)
3. Extract text with PyMuPDF (XXE disabled, no JS evaluation)
   → On failure: set status=FAILED, publish error to Redis pub/sub, exit
4. Clean & normalize text: strip null bytes, decode utf-8 errors="replace"
5. Build ParentChunks: split by section headers / every 5 pages (~3000 tokens each)
6. Build LeafChunks: recursive token-aware split of each parent (~400 tokens, 50 overlap)
   → Inject metadata: page_number, section_title, years_detected (regex)
7. Generate section summaries for each ParentChunk via Ollama
   → asyncio.wait_for(ollama_call, timeout=60.0) → on TimeoutError: retry up to 3x
8. Generate embeddings for all LeafChunks in batches of 32
   → asyncio.gather(*batch_tasks, return_exceptions=True)
   → log individual failures, retry transient errors
9. INSERT ParentChunks + LeafChunks + ChunkEmbeddings into PostgreSQL/pgvector
10. Update Document status → READY
11. Publish completion event to Redis pub/sub: cortex:notify:{workspace_id}
```

### 3.3 RAG Query Pipeline
```
POST /query/ask  {session_id, question}
    │
    ▼ Auth + RBAC + rate limit check
    │
    ▼ Query Rewriting (conversational context fix)
    │  Fetch last 5 messages from QuerySession
    │  If follow-up detected → LLM call to rewrite into standalone question
    │  e.g. "summarize it" → "summarize the health trends from 2010-2020"
    │  asyncio.wait_for(rewrite_call, timeout=10.0)
    │
    ▼ Embed rewritten query → nomic-embed-text via Ollama
    │  asyncio.wait_for(embed_call, timeout=15.0)
    │
    ▼ Hybrid Retrieval (parallel)
    │  async with asyncio.TaskGroup() as tg:
    │    t1 = tg.create_task(vector_search(query_vec, top_k=20))     # pgvector
    │    t2 = tg.create_task(bm25_search(rewritten_query, top_k=20)) # Elasticsearch
    │    t3 = tg.create_task(summary_search(query_vec, top_k=5))     # Parent summaries
    │  except* (DBConnectionError, ESConnectionError) as eg:
    │    log errors, fallback to whichever succeeded
    │
    ▼ Merge + Deduplicate results (by chunk_id)
    │
    ▼ Cross-encoder Re-ranking (top 25 → top 5)
    │  asyncio.wait_for(rerank_call, timeout=10.0)
    │  On failure → fallback to raw similarity scores (log warning)
    │
    ▼ Build structured LLM prompt:
    │  [SYSTEM] You are a precise document assistant.
    │           Answer ONLY from the provided context.
    │           Cite sources as [Source: doc_id · chunk_id · page N].
    │  [CONTEXT] {top 5 chunks with section metadata prepended}
    │  [QUESTION] {rewritten question}
    │
    ▼ Stream LLM response via SSE (Server-Sent Events)
    │  asyncio.wait_for(stream_generator, timeout=120.0)
    │  On disconnect mid-stream → log, close generator cleanly
    │
    ▼ Post-process streamed response:
    │  Parse [Source: ...] citations
    │  Validate each citation exists in retrieved chunk set
    │  Hallucinated citations (not in context) → strip + log
    │  Compute confidence: cite_ratio · reranker_score
    │
    ▼ INSERT Message (role=assistant) + Citations into DB
    ▼ UPDATE UsageRecord (tokens used this session)
    ▼ Return: streamed answer + validated citations + confidence badge
```

### 3.4 WebSocket — Real-Time Job Notifications
```
WS /ws/{workspace_id}  (authenticated via query param token)
    │
    ▼ Accept + validate JWT token from query string
    │
    ▼ Register connection in ConnectionManager (in-memory dict)
    │
    ▼ Start Redis pub/sub subscriber for cortex:notify:{workspace_id}
    │
    ▼ while True:
    │    try:
    │      data = await websocket.receive_text()  ← client ping or message
    │    except WebSocketDisconnect:
    │      log info, break
    │    except Exception as exc:
    │      log error, break
    │    finally:
    │      await manager.disconnect(websocket)
    │      cancel pub/sub subscriber task
    │
    ▼ On Redis pub/sub event received:
       push JSON payload to client: {type, document_id, status, message}
```

---

## 4. Security & Validation Rules

### 4.1 File Upload Security
| Check | Method | On Failure |
|---|---|---|
| File size | Compare bytes length to `profile.storage_limit_mb` | `InvalidFileException(400)` |
| Extension whitelist | `pathlib.Path(filename).suffix.lower() in {'.pdf','.docx','.txt','.md'}` | `InvalidFileException(400)` |
| Double extension | `re.search(r'\.(exe\|sh\|py\|js\|php\|bat)\.[a-z]+$', filename, re.I)` | `InvalidFileException(400)` |
| Unicode overrides | Check for Right-To-Left Override char (U+202E) in filename | `InvalidFileException(400)` |
| MIME magic bytes | `python-magic` reads first 2048 bytes → verified MIME must match extension | `InvalidFileException(400)` |
| ZIP/PDF bomb | Parser memory limit enforced in worker config; page-by-page streaming | Worker SIGTERM → status=FAILED |
| Path traversal | Filename replaced with `{uuid}.{ext}` before MinIO write | N/A (sanitized before use) |
| XXE in parsers | `PyMuPDF` has no XML eval; parsers run in isolated Docker network | N/A |

### 4.2 Authentication Security
| Check | Method |
|---|---|
| Password hashing | PBKDF2-SHA256 |
| JWT signing | RS256 (asymmetric) or HS256 with `secrets.token_urlsafe(64)` secret |
| Access token TTL | 15 minutes |
| Refresh token | 7-day TTL, stored in `HttpOnly; Secure; SameSite=Strict` cookie |
| Refresh rotation | Each refresh invalidates old refresh token (stored hash in DB) |
| API key generation | `secrets.token_urlsafe(32)` — only hash stored in DB, shown once to user |
| Brute force | Account lock after 5 failed logins (15-min Redis TTL counter) |
| Token theft | Short-lived access token; refresh token rotation; revocation list in Redis |

### 4.3 Multi-Tenancy (RLS)
```sql
-- Applied to: documents, parent_chunks, leaf_chunks, chunk_embeddings, query_sessions
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON documents
  USING (workspace_id = current_setting('app.workspace_id')::uuid);
```
Every API DB session must run: `SET LOCAL app.workspace_id = '{id}'` before any query.  
A missing filter no longer leaks data — Postgres enforces it at the storage level.

### 4.4 Input Validation (Pydantic v2 Strict Mode)
| Field | Rule |
|---|---|
| Email | `EmailStr` from pydantic-email-validator |
| Password | `min_length=8`, regex `[A-Z]`, `[0-9]`, `[!@#$%]` |
| Query text | `min_length=1`, `max_length=2000` |
| Workspace name | `min_length=2`, `max_length=50`, `pattern=r'^[\w\s\-]+$'` |
| API key name | `max_length=50` |
| File content | Validated at binary level (magic bytes), not Pydantic |

### 4.5 MinIO — Private Bucket + Presigned URLs
- All buckets created with `ACL=private`. No public access.
- Files served only via **presigned URLs** generated server-side:
  - `expires=600` (10 minutes)
  - URL generated on each authenticated file-view request
  - Never stored in DB or exposed in listings

---

## 5. Engineering Standards (Global Rules)

These rules apply to **every file** in the codebase. They are non-negotiable.

### 5.1 Exception Hierarchy
```python
# app/core/exceptions.py — single source of all domain exceptions

class CortexException(Exception):
    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "An unexpected error occurred."
    def __init__(self, message: str = None, details: dict = None):
        if message: self.message = message
        self.details = details or {}
        super().__init__(self.message)

# Auth
class AuthenticationException(CortexException):
    code="AUTH_FAILED"; status_code=401; message="Invalid or expired credentials."
class ForbiddenException(CortexException):
    code="FORBIDDEN"; status_code=403; message="You do not have permission."
class UserNotFoundException(CortexException):
    code="USER_NOT_FOUND"; status_code=404; message="User not found."

# Workspace / Business Logic
class WorkspaceNotFoundException(CortexException):
    code="WORKSPACE_NOT_FOUND"; status_code=404; message="Workspace not found."
class QuotaExceededException(CortexException):
    code="QUOTA_EXCEEDED"; status_code=403; message="Plan limit reached."
class ConflictException(CortexException):
    code="CONFLICT"; status_code=409; message="Resource already exists."

# File & Parsing
class InvalidFileException(CortexException):
    code="INVALID_FILE"; status_code=400; message="File rejected — invalid or suspicious format."
class FileParsingException(CortexException):
    code="PARSE_FAILED"; status_code=422; message="Could not extract text from document."
class DocumentNotFoundException(CortexException):
    code="DOCUMENT_NOT_FOUND"; status_code=404; message="Document not found."

# External Services
class LLMProviderException(CortexException):
    code="LLM_UNAVAILABLE"; status_code=503; message="AI service unavailable or timed out."
class EmbeddingException(CortexException):
    code="EMBEDDING_FAILED"; status_code=503; message="Embedding generation failed."
class StorageException(CortexException):
    code="STORAGE_ERROR"; status_code=503; message="File storage operation failed."
```

### 5.2 Global Exception Handler (registered in main.py)
```python
@app.exception_handler(CortexException)
async def cortex_handler(request: Request, exc: CortexException):
    cid = getattr(request.state, "correlation_id", "unknown")
    logger.error("cortex_exception", code=exc.code, message=exc.message,
                 details=exc.details, correlation_id=cid, status=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={
        "error": {"code": exc.code, "message": exc.message,
                  "details": exc.details, "correlation_id": cid}
    })

@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    cid = getattr(request.state, "correlation_id", "unknown")
    logger.critical("unhandled_exception", error=str(exc), correlation_id=cid,
                    exc_info=True)
    return JSONResponse(status_code=500, content={
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.",
                  "correlation_id": cid}
    })
```

### 5.3 Structured JSON Logging (structlog)
Every log line must be JSON with these fields:
```json
{
  "timestamp": "2026-06-06T02:00:00Z",
  "level": "ERROR",
  "event": "file_upload_blocked",
  "correlation_id": "req-9b1d-...",
  "user_id": "usr_abc",
  "workspace_id": "ws_xyz",
  "details": { "filename": "evil.sh.pdf", "detected_mime": "application/x-sh" }
}
```

### 5.4 Async Rules (enforced via linting / code review)
| Rule | Wrong | Correct |
|---|---|---|
| Non-blocking sleep | `time.sleep(1)` | `await asyncio.sleep(1)` |
| Secure tokens | `random.hex(16)` | `secrets.token_urlsafe(32)` |
| External API calls | `await client.post(url)` (unbounded) | `await asyncio.wait_for(client.post(url), timeout=30.0)` |
| Parallel tasks | `asyncio.gather(*tasks)` (fail-all) | `asyncio.gather(*tasks, return_exceptions=True)` |
| Structured concurrency | bare gather | `async with asyncio.TaskGroup()` + `except*` |
| DB single-row fetch | `.one()` (throws on None) | `.first()` + `if result is None: raise XxxException()` |

### 5.5 Redis Configuration
```python
redis_client = Redis(
    host=settings.REDIS_HOST, port=6379, db=0,
    retry=Retry(ExponentialBackoff(cap=10, initial=0.5), retries=5),
    retry_on_timeout=True,
    socket_connect_timeout=5.0,
    socket_timeout=5.0,
    max_connections=50,
    decode_responses=True
)
```

### 5.6 PostgreSQL Pool (SQLAlchemy async)
```python
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20, max_overflow=10, pool_recycle=1800,
    pool_pre_ping=True,  # detect stale connections
    connect_args={"connect_timeout": 10,
                  "options": "-c statement_timeout=30000"}
)
```

### 5.7 CORS Middleware (no wildcards in prod)
```python
app.add_middleware(CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # from env: ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
    allow_headers=["Authorization","Content-Type","X-Correlation-ID"],
)
```

### 5.8 Ollama / LLM HTTP Client
```python
llm_client = httpx.AsyncClient(
    base_url=settings.OLLAMA_BASE_URL,  # http://ollama:11434
    timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=10.0),
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=30),
)
```

---

## 6. Resolved Architecture Issues

Issues found during engineering review — all resolved and integrated into steps below:

| ID | Problem | Resolution | Step |
|---|---|---|---|
| AI-01 | Hardcoded vector dim (1536) breaks on model switch | `ChunkEmbedding.model_name` column + dynamic dim per model in registry | Step 9 |
| AI-02 | Follow-up queries ("summarize it") retrieve wrong context | Query rewriting middleware using chat history before embedding | Step 14 |
| AI-03 | Character chunker slices tokens mid-word | Token-aware splitter using `tiktoken` / model vocab tokenizer | Step 8 |
| QA-01 | Deleted doc stays in Redis cache → stale answers | Cascade delete: doc deletion → Redis namespace flush + pgvector wipe | Step 15 |
| QA-02 | 500-page PDF blows worker RAM → silent crash | Page-by-page streaming generator; `worker_max_tasks_per_child=50` | Step 10 |
| QA-03 | Prompt changes silently degrade answer quality | RAG eval suite (context precision + groundedness) in Phase 6 | Step 28 |
| SEC-01 | Missing `.filter(workspace_id=...)` leaks cross-tenant data | PostgreSQL RLS policies on all tenant tables | Step 2 |
| SEC-02 | Public MinIO URLs expose private documents | Private buckets + presigned URL generation (10min TTL) | Step 6 |
| SEC-03 | PDF parsers vulnerable to XXE / SSRF | Disabled XML entity resolution; workers on isolated Docker network | Steps 1, 7 |
| NET-01 | `time.sleep` in async functions freezes event loop | `await asyncio.sleep` enforced everywhere | All steps |
| NET-02 | `random` module used for tokens/keys | `secrets.token_urlsafe(32)` enforced | Steps 3, 16 |
| NET-03 | External API calls hang indefinitely on network drop | `asyncio.wait_for(coro, timeout=N)` wrapper on all external calls | Steps 9, 12-14 |
| NET-04 | Parallel task failures cascade to abort entire gather | `gather(*tasks, return_exceptions=True)` + TaskGroup + `except*` | Steps 12-14 |
| NET-05 | `.one()` throws `NoResultFound` bypassing exception pipeline | `.first()` + `if result is None: raise DomainException()` everywhere | All DB steps |

---

## 7. Implementation Phases — 30 Steps

> Each step is self-contained. A developer or model executing any step should read **only that step** plus **Section 5 (Engineering Standards)**. No other context needed.

---

### PHASE 1: FOUNDATION (Steps 1–5)

---

#### Step 1: Project Setup & Infrastructure

**Goal**: A running Docker environment with all services healthy, and the FastAPI application skeleton with core middleware wired up.

**Folder Structure to Create**:
```
cortexrag/
├── docker-compose.yml
├── .env.example
├── caddy/
│   └── Caddyfile
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml       (Poetry)
│   ├── app/
│   │   ├── main.py          (FastAPI app factory)
│   │   ├── core/
│   │   │   ├── config.py    (Settings via pydantic-settings)
│   │   │   ├── exceptions.py (Full exception hierarchy — see §5.1)
│   │   │   ├── logging.py   (structlog JSON config)
│   │   │   └── middleware.py (CorrelationID, RLS context setters)
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── router.py (aggregates all sub-routers)
│   │   └── db/
│   │       ├── session.py   (async engine + session factory)
│   │       └── base.py      (SQLAlchemy DeclarativeBase)
└── frontend/                (scaffolded in Step 21)
```

**Services in docker-compose.yml**:
- `postgres`: image `pgvector/pgvector:pg16` · port 5432 · volume `pg_data`
- `redis`: image `redis:7-alpine` · port 6379 · max-memory policy `allkeys-lru`
- `minio`: image `minio/minio` · ports 9000/9001 · private bucket init script
- `elasticsearch`: image `elasticsearch:8.13.0` · port 9200 · single-node, security disabled for local dev
- `ollama`: image `ollama/ollama` · port 11434 · volume `ollama_models` · pull `nomic-embed-text` + `llama3` on startup
- `backend`: custom Dockerfile · depends on all above · `app` network
- `worker`: same image as backend · command `celery -A app.worker worker` · `worker` network (isolated — no internet)
- `caddy`: image `caddy:2` · ports 80/443 · reverse proxy to backend:8000

**Docker Network Config**:
```yaml
networks:
  app:       # backend, minio, redis, elasticsearch, postgres, caddy, ollama
  worker:    # worker only — NO internet gateway (for XXE/SSRF protection)
    internal: true
```

**Middleware to wire in main.py** (in this order):
1. `CorrelationIDMiddleware`: reads `X-Correlation-ID` header or generates `secrets.token_urlsafe(16)`. Stores on `request.state.correlation_id`.
2. `CORSMiddleware`: origins from `settings.CORS_ORIGINS` (env var).
3. `TrustedHostMiddleware`: only allow configured hostnames.
4. Exception handlers: `cortex_handler` + `unhandled_handler` (see §5.2).

**Core Config (pydantic-settings)**:
```python
class Settings(BaseSettings):
    DATABASE_URL: str        # postgresql+asyncpg://...
    REDIS_URL: str           # redis://redis:6379/0
    MINIO_ENDPOINT: str      # minio:9000
    OLLAMA_BASE_URL: str     # http://ollama:11434
    CORS_ORIGINS: list[str]  # ["http://localhost:3000"]
    JWT_SECRET: str          # secrets.token_urlsafe(64) — set in .env
    LLM_PROVIDER: str = "ollama"   # or "openai"
    LLM_MODEL: str = "llama3"
    EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIM: int = 768
    model_config = SettingsConfigDict(env_file=".env")
```

**Test**: `docker compose up --build` → all containers healthy. `GET /health` returns `{"status": "ok"}`.  
**Lesson file**: `lessons/step-01-project-setup.md`

---

#### Step 2: Database Schema & Migrations

**Goal**: All database tables created via Alembic migrations with RLS policies, correct indexes, and connection pooling configured.

**Tables to create** (SQLAlchemy async models):
- `users`: id (UUID PK), email (unique), hashed_password, is_active, created_at
- `profiles`: id, user_id (FK), tier, doc_limit, query_limit_monthly, storage_limit_mb
- `api_keys`: id, user_id (FK), key_hash (unique), name, last_used_at, is_active
- `usage_records`: id, user_id (FK), month (Date), token_count, cost_usd
- `workspaces`: id, name, owner_id (FK → users)
- `workspace_members`: workspace_id, user_id, role (enum: viewer/editor/admin)
- `documents`: id, workspace_id (FK), filename, storage_key, status (enum), mime_type, file_size, page_count, error_message, created_at
- `upload_jobs`: id, document_id (FK), celery_task_id, status, error_message, correlation_id
- `parent_chunks`: id, document_id (FK), content, section_title, page_start, page_end, token_count, summary
- `leaf_chunks`: id, parent_id (FK), content, chunk_index, token_count, years_detected (JSONB)
- `chunk_embeddings`: id, chunk_id (FK → leaf_chunks), model_name, vector (vector type — dim from model registry)
- `query_sessions`: id, workspace_id (FK), user_id (FK), title, created_at
- `messages`: id, session_id (FK), role (enum), content, tokens_used, created_at
- `citations`: id, message_id (FK), chunk_id (FK), page_number, section_title, confidence_score
- `feedback_records`: id, session_id (FK), rating (1-5), comment, created_at

**pgvector**: Run `CREATE EXTENSION IF NOT EXISTS vector;` in migration env.

**RLS Policies** (add to migration script for each tenant table):
```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY ws_isolation ON documents
  FOR ALL USING (workspace_id::text = current_setting('app.workspace_id', true));
-- Repeat for: parent_chunks, leaf_chunks, chunk_embeddings, query_sessions, messages
```

**Indexes to create**:
- `idx_documents_workspace_id`
- `idx_leaf_chunks_parent_id`
- `CREATE INDEX ON chunk_embeddings USING hnsw (vector vector_cosine_ops) WITH (m=16, ef_construction=64);`
- `idx_messages_session_id`

**SQLAlchemy Pool config**: Apply §5.6 to `session.py`.

**Test**: `alembic upgrade head` succeeds. `\d+ documents` in psql shows RLS enabled. HNSW index visible in `\d+ chunk_embeddings`.  
**Lesson file**: `lessons/step-02-database-schema.md`

---

#### Step 3: Authentication System

**Goal**: Working JWT authentication — register, login, token refresh, logout. All passwords hashed with PBKDF2-SHA256. All tokens generated with `secrets.token_urlsafe`.

**Files**:
- `app/api/v1/auth.py` — router with endpoints
- `app/services/auth_service.py` — business logic
- `app/schemas/auth.py` — Pydantic v2 request/response schemas
- `app/core/security.py` — password hashing, JWT encode/decode

**Endpoints**:
- `POST /auth/register` → validate → `.first()` check for existing email → if None only → hash pw → create User + Profile(free) + Workspace → return tokens
- `POST /auth/login` → `.first()` → `if user is None: raise AuthenticationException` → verify PBKDF2 → issue JWT (15min) + refresh token (7 days, HttpOnly cookie)
- `POST /auth/refresh` → read refresh token from cookie → validate hash in DB → rotate: issue new pair, invalidate old refresh token hash in Redis
- `POST /auth/logout` → blacklist access token in Redis (TTL = remaining JWT lifetime)

**JWT Dependency** (`app/core/deps.py`):
```python
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            raise AuthenticationException()
    except JWTError:
        raise AuthenticationException()
    
    # Check token not blacklisted
    if await redis_client.get(f"blacklist:{token}"):
        raise AuthenticationException("Token has been revoked.")
    
    user = await db.execute(select(User).where(User.id == user_id))
    user = user.scalar_one_or_none()  # equivalent to .first() for scalars
    if user is None:
        raise UserNotFoundException()
    return user
```

**Brute force protection**: Redis counter `login_fail:{email}` with 15-min TTL. After 5 failures → raise `ForbiddenException("Account temporarily locked.")`.

**Test**: Register → login → access protected endpoint → refresh → logout → verify blacklisted token rejected.  
**Lesson file**: `lessons/step-03-authentication.md`

---

#### Step 4: User Profile & Workspace Management

**Goal**: APIs to manage user profile (tier toggle for demo), update password, delete account (GDPR). Workspace CRUD with member invite/role management.

**Endpoints**:
- `GET /users/me` → return User + Profile
- `PUT /users/me` → update display name
- `PUT /users/me/password` → verify old password → bcrypt new
- `DELETE /users/me` → soft-delete user, queue data purge job (documents, embeddings, sessions)
- `PUT /users/me/tier` → toggle `profile.tier` between `free`/`pro` (mock demo only)
- `POST /workspaces` → create workspace (enforce workspace limit by tier)
- `GET /workspaces/{id}` → return workspace + member list
- `POST /workspaces/{id}/members` → send invite (stored in DB with `secrets.token_urlsafe(16)` invite token)
- `DELETE /workspaces/{id}/members/{user_id}` → remove member (admin only)

**Tier Limits** (enforced by `QuotaService`):
```python
TIER_LIMITS = {
    "free":  {"doc_limit": 5,   "storage_mb": 10,  "query_monthly": 100},
    "pro":   {"doc_limit": 100, "storage_mb": 500,  "query_monthly": 5000},
}
```

**Test**: Toggle tier → upload more than 5 docs as free → 403 QuotaExceeded. Invite flow end-to-end.  
**Lesson file**: `lessons/step-04-user-workspace.md`

---

#### Step 5: API Key Management & Rate Limiting

**Goal**: Users can generate API keys for programmatic access. Per-user and per-key rate limiting via Redis counters.

**Files**:
- `app/api/v1/keys.py`
- `app/services/key_service.py`
- `app/core/rate_limiter.py`

**API Key flow**:
- `POST /keys` → generate: `raw = secrets.token_urlsafe(32)`, store `sha256(raw)` in DB. Return raw key **once** to user.
- `GET /keys` → list keys (name, last_used, is_active — never return raw key)
- `DELETE /keys/{id}` → set `is_active=False`
- Auth via API key: middleware checks `Authorization: ApiKey {raw}` → hash it → `.first()` on `api_keys` → `if key is None or not key.is_active: raise AuthenticationException()`

**Rate Limiter** (Redis sliding window):
```python
async def check_rate_limit(user_id: str, limit: int = 60, window: int = 60):
    key = f"ratelimit:{user_id}:{int(time.time() // window)}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window)
    if count > limit:
        raise ForbiddenException("Rate limit exceeded. Try again shortly.")
```

**Test**: Generate key → call API with key → rate limit test (61st request → 403).  
**Lesson file**: `lessons/step-05-api-keys-rate-limiting.md`

---

### PHASE 2: DOCUMENT PIPELINE (Steps 6–10)

---

#### Step 6: Secure File Upload & MinIO Storage

**Goal**: Endpoint to upload files with full security validation pipeline. Files stored in private MinIO bucket. Presigned URL generation for retrieval.

**Files**:
- `app/api/v1/documents.py`
- `app/services/upload_service.py`
- `app/services/storage_service.py`

**Validation order** (fail fast, reject before any I/O):
```python
async def validate_upload(file: UploadFile, profile: Profile):
    # 1. Size check
    content = await file.read()
    if len(content) > profile.storage_limit_mb * 1024 * 1024:
        raise InvalidFileException("File exceeds plan size limit.")
    
    # 2. Extension whitelist
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise InvalidFileException("File type not supported.")
    
    # 3. Double extension
    if re.search(r'\.(exe|sh|py|js|php|bat|cmd)\.[a-z]+$', file.filename, re.I):
        raise InvalidFileException("Suspicious filename rejected.")
    
    # 4. Unicode override character
    if '\u202e' in file.filename:
        raise InvalidFileException("Filename contains forbidden characters.")
    
    # 5. Magic bytes check
    detected_mime = magic.from_buffer(content[:2048], mime=True)
    allowed = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats...", ...}
    if detected_mime != allowed.get(suffix):
        raise InvalidFileException(f"File content does not match extension. Detected: {detected_mime}")
    
    return content  # validated bytes
```

**MinIO operations**:
```python
async def store_file(workspace_id: str, content: bytes, suffix: str) -> str:
    storage_key = f"{workspace_id}/{uuid4()}{suffix}"
    try:
        await asyncio.wait_for(
            minio_client.put_object(bucket, storage_key, content),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        raise StorageException("File upload timed out.")
    except Exception as exc:
        logger.error("minio_put_failed", error=str(exc))
        raise StorageException()
    return storage_key

async def get_presigned_url(storage_key: str) -> str:
    return minio_client.presigned_get_object(bucket, storage_key, expires=timedelta(minutes=10))
```

**Test**: Upload valid PDF → 202 + job_id. Upload `.sh.pdf` → 400. Upload valid `.pdf` with ELF magic bytes → 400. Presigned URL expires after 10 min.  
**Lesson file**: `lessons/step-06-file-upload-storage.md`

---

#### Step 7: Text Extraction

**Goal**: Celery worker function that downloads a file from MinIO and extracts clean text, page-by-page, without loading the entire file into RAM.

**Files**:
- `app/worker/tasks/extraction.py`
- `app/services/parser_service.py`

**Extraction strategy**:
```python
def extract_text_streaming(file_bytes: bytes, mime_type: str) -> Generator[dict, None, None]:
    """Yields {page_num, text} dicts one page at a time."""
    if mime_type == "application/pdf":
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page_num, page in enumerate(doc, start=1):
                raw = page.get_text()
                # UTF-8 safe decode for any binary bleed
                clean = raw.encode("utf-8", errors="replace").decode("utf-8")
                yield {"page": page_num, "text": clean.strip()}
    elif mime_type == "text/plain":
        text = file_bytes.decode("utf-8", errors="replace")
        yield {"page": 1, "text": text}
    # .docx: use python-docx, yield paragraph blocks
```

- PyMuPDF (`fitz`) — no XML external entity loading; runs entirely in-process (no subprocess risk)
- File bytes are passed in-memory from MinIO download; not written to disk
- On any exception during extraction: set `Document.status = FAILED`, log full traceback with correlation_id, publish failure event to Redis pub/sub

**Test**: Extract 100-page PDF → verify page-by-page yields without memory spike. Corrupt PDF → status=FAILED log entry.  
**Lesson file**: `lessons/step-07-text-extraction.md`

---

#### Step 8: Hierarchical Chunking (Parent-Child)

**Goal**: Convert extracted page text into ParentChunks (section-level) and LeafChunks (paragraph-level) with structural metadata injected. Use token-aware splitting.

**Files**:
- `app/services/chunking_service.py`
- `app/worker/tasks/chunking.py`

**Chunking approach**:
```python
# Token-aware splitter using tiktoken (cl100k_base for llama3 compatibility)
enc = tiktoken.get_encoding("cl100k_base")

def token_len(text: str) -> int:
    return len(enc.encode(text))

def build_parent_chunks(pages: list[dict]) -> list[ParentChunkData]:
    """Group pages into ~5-page sections (~3000 tokens each)"""
    # Detect section headers via regex; otherwise group by page window
    # Each parent: {section_title, page_start, page_end, content, token_count}

def build_leaf_chunks(parent: ParentChunkData) -> list[LeafChunkData]:
    """Recursively split parent into ~400-token leaf chunks with 50-token overlap"""
    # Split at sentence boundaries first, then at token boundary
    # Inject metadata prefix: "[Page {n} | Section: {title}]"
    # Extract years_detected via regex: r'\b(19|20)\d{2}\b'
    # Each leaf: {parent_id, content, chunk_index, token_count, years_detected}
```

- Parent summaries generated in Step 9 (after embedding model is ready)
- `await asyncio.sleep(0)` after each parent chunk to yield control back to event loop in async generator contexts

**Test**: 100-page PDF → expected ~20 parents, ~200 leaves. Each leaf ≤ 450 tokens. Verify metadata injection.  
**Lesson file**: `lessons/step-08-chunking.md`

---

#### Step 9: Embedding Generation & Dynamic Vector Schema

**Goal**: Generate embeddings for all LeafChunks and ParentChunk summaries. Support model-switching via env var. Store vectors with model name tracked.

**Files**:
- `app/services/embedding_service.py`
- `app/worker/tasks/embedding.py`

**Provider abstraction**:
```python
class EmbeddingService:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if settings.LLM_PROVIDER == "ollama":
            return await self._ollama_embed(texts)
        elif settings.LLM_PROVIDER == "openai":
            return await self._openai_embed(texts)

    async def _ollama_embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        # Batch in groups of 32
        for batch in chunks(texts, 32):
            tasks = [self._single_embed(t) for t in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in batch_results:
                if isinstance(res, Exception):
                    logger.error("embedding_batch_failure", error=str(res))
                    raise EmbeddingException()
                results.append(res)
        return results

    async def _single_embed(self, text: str) -> list[float]:
        try:
            response = await asyncio.wait_for(
                llm_client.post("/api/embeddings",
                    json={"model": settings.EMBED_MODEL, "prompt": text}),
                timeout=30.0
            )
            return response.json()["embedding"]
        except asyncio.TimeoutError:
            raise EmbeddingException("Embedding timeout.")
```

**Dynamic vector storage**: `chunk_embeddings.vector` column type is `Vector(dim)` where `dim` comes from `settings.EMBED_DIM`. On model switch, run migration to add new column `vector_{model_name}` or use `model_name` to route to correct index. No hardcoded 1536.

**Test**: Embed 10 texts → verify dim=768 (Ollama). Switch to openai in env → verify dim=1536. Batch failure on one → EmbeddingException raised, not silent corruption.  
**Lesson file**: `lessons/step-09-embeddings.md`

---

#### Step 10: Celery Task Queue & Worker Health

**Goal**: Full async ingestion pipeline wired as Celery tasks. Worker retry config, OOM protection, correlation ID propagation, Redis pub/sub notifications.

**Files**:
- `app/worker/celery_app.py`
- `app/worker/tasks/ingestion.py` (orchestrates steps 7-9)
- `app/worker/tasks/cleanup.py`

**Celery config**:
```python
celery_app = Celery("cortexrag", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,           # only ack after success, redeliver on crash
    worker_max_tasks_per_child=50, # recycle worker process after 50 tasks (OOM protection)
    task_reject_on_worker_lost=True,
    task_default_retry_delay=5,
    task_max_retries=3,
)
```

**Master ingestion task**:
```python
@celery_app.task(bind=True, max_retries=3)
def ingest_document(self, job_id: str, correlation_id: str):
    logger = get_logger().bind(job_id=job_id, correlation_id=correlation_id)
    try:
        # Step 1: Download from MinIO
        # Step 2: Extract text (streaming generator)
        # Step 3: Build parent + leaf chunks
        # Step 4: Generate parent summaries (LLM)
        # Step 5: Generate leaf embeddings (batch)
        # Step 6: INSERT all to DB
        # Step 7: Update Document.status = READY
        # Step 8: Publish to Redis pub/sub
        redis_client.publish(f"cortex:notify:{workspace_id}", json.dumps({
            "type": "DOCUMENT_READY", "document_id": doc_id, "status": "READY"
        }))
    except (StorageException, FileParsingException, EmbeddingException) as exc:
        # Known domain exception — fail without retry
        update_document_status(job_id, "FAILED", str(exc))
        redis_client.publish(f"cortex:notify:{workspace_id}", json.dumps({
            "type": "DOCUMENT_FAILED", "document_id": doc_id, "error": exc.message
        }))
    except Exception as exc:
        # Unknown transient — retry with exponential backoff
        logger.warning("ingestion_retrying", attempt=self.request.retries, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries + 2)
```

**Test**: Upload PDF → check job progress in DB (`PROCESSING` → `READY`). WebSocket receives `DOCUMENT_READY`. Kill worker mid-task → verify `acks_late` causes re-delivery. 500-page PDF → memory stays flat (streaming).  
**Lesson file**: `lessons/step-10-celery-workers.md`

---

### PHASE 3: RAG ENGINE (Steps 11–15)

---

#### Step 11: Vector Search (pgvector)

**Goal**: Semantic similarity search over LeafChunk embeddings using pgvector HNSW index. Configurable top-k retrieval with workspace isolation (RLS enforced).

**Files**:
- `app/services/vector_search_service.py`

**Search query**:
```python
async def vector_search(query_vec: list[float], workspace_id: str,
                        top_k: int = 20) -> list[LeafChunkResult]:
    async with get_db_session() as db:
        await db.execute(text(f"SET LOCAL app.workspace_id = '{workspace_id}'"))
        try:
            result = await asyncio.wait_for(
                db.execute(
                    select(LeafChunk, ChunkEmbedding,
                           (ChunkEmbedding.vector.cosine_distance(query_vec)).label("distance"))
                    .join(ChunkEmbedding, LeafChunk.id == ChunkEmbedding.chunk_id)
                    .order_by("distance")
                    .limit(top_k)
                ),
                timeout=10.0
            )
            return result.all()
        except asyncio.TimeoutError:
            raise CortexException("Vector search timed out.", status_code=503)
```

**Test**: Insert 100 chunks → query → verify top result is semantically closest. Verify RLS: user A cannot see user B's chunks even with correct vector.  
**Lesson file**: `lessons/step-11-vector-search.md`

---

#### Step 12: Hybrid Search & Result Merging

**Goal**: Combine pgvector semantic search with Elasticsearch BM25 keyword search. Run both in parallel. Merge and deduplicate results using Reciprocal Rank Fusion (RRF).

**Files**:
- `app/services/bm25_service.py`
- `app/services/retrieval_service.py` (orchestrator)

**Elasticsearch indexing**: On LeafChunk creation → index `{chunk_id, content, workspace_id, section_title}` into ES.

**Parallel hybrid search**:
```python
async def hybrid_search(query_text: str, query_vec: list[float],
                        workspace_id: str) -> list[RankedChunk]:
    try:
        async with asyncio.TaskGroup() as tg:
            t_vec = tg.create_task(vector_search(query_vec, workspace_id, top_k=20))
            t_bm25 = tg.create_task(bm25_search(query_text, workspace_id, top_k=20))
            t_summary = tg.create_task(summary_search(query_vec, workspace_id, top_k=5))
    except* Exception as eg:
        logger.error("hybrid_search_partial_failure", errors=[str(e) for e in eg.exceptions])
        # Use whichever task succeeded (access via task result, not eg)

    # Reciprocal Rank Fusion
    scores = {}
    for rank, chunk in enumerate(vector_results, 1):
        scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (60 + rank)
    for rank, chunk in enumerate(bm25_results, 1):
        scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (60 + rank)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_map[cid] for cid, _ in merged[:25]]
```

**Test**: Query that matches both semantically and by keyword → verify merged rank is higher than either alone. BM25 service down → vector results still returned (partial failure handled).  
**Lesson file**: `lessons/step-12-hybrid-search.md`

---

#### Step 13: Cross-Encoder Re-ranking & Context Assembly

**Goal**: Re-rank top 25 merged chunks to top 5 using a cross-encoder model. Assemble structured context with section metadata prepended. Provide fallback if re-ranker unavailable.

**Files**:
- `app/services/reranker_service.py`
- `app/services/context_builder.py`

**Re-ranking**: Use `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence-transformers` (runs locally, ~80MB).
```python
async def rerank(query: str, chunks: list[RankedChunk]) -> list[RankedChunk]:
    try:
        pairs = [(query, c.content) for c in chunks]
        scores = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None,
                lambda: cross_encoder.predict(pairs)),
            timeout=15.0
        )
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ranked[:5]]
    except asyncio.TimeoutError:
        logger.warning("reranker_timeout_fallback")
        return chunks[:5]  # graceful fallback — raw RRF order
    except Exception as exc:
        logger.warning("reranker_failed_fallback", error=str(exc))
        return chunks[:5]
```

**Context assembly**:
```python
def build_context(chunks: list[RankedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[Source {i} | Doc: {chunk.doc_id} | Page: {chunk.page_num} | Section: {chunk.section_title}]"
        parts.append(f"{header}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)
```

**Test**: Re-rank 25 chunks → verify top 5 are semantically closest to query. Kill sentence-transformers → fallback to RRF order without error.  
**Lesson file**: `lessons/step-13-reranking.md`

---

#### Step 14: LLM Integration — Query Rewriting & Streaming Response

**Goal**: Query rewriting for conversational context. Streaming LLM response via SSE. Graceful mid-stream disconnect handling.

**Files**:
- `app/services/llm_service.py`
- `app/services/query_rewriter.py`
- `app/api/v1/query.py`

**Query rewriter**:
```python
async def rewrite_query(history: list[Message], current: str) -> str:
    if len(history) == 0:
        return current  # no history → no rewrite needed
    
    history_str = "\n".join([f"{m.role}: {m.content}" for m in history[-5:]])
    prompt = (f"Given this conversation:\n{history_str}\n\n"
              f"Rewrite this question as a complete standalone search query: {current}\n"
              f"Output ONLY the rewritten question.")
    
    response = await asyncio.wait_for(
        llm_client.post("/api/generate",
            json={"model": settings.LLM_MODEL, "prompt": prompt, "stream": False}),
        timeout=15.0
    )
    return response.json().get("response", current).strip()
```

**LLM Prompt structure**:
```
[SYSTEM]
You are a precise document intelligence assistant.
Answer ONLY using the provided context. Do not invent facts.
Cite every claim using the format: [Source N] where N is the source number.
If the context does not contain the answer, say: "I cannot find this in the provided documents."

[CONTEXT]
{assembled context from Step 13}

[QUESTION]
{rewritten query}
```

**Streaming via SSE**:
```python
async def stream_llm(prompt: str):
    try:
        async with asyncio.timeout(120):  # Python 3.11 syntax
            async with llm_client.stream("POST", "/api/generate",
                json={"model": settings.LLM_MODEL, "prompt": prompt, "stream": True}) as response:
                async for line in response.aiter_lines():
                    data = json.loads(line)
                    yield f"data: {json.dumps({'token': data['response']})}\n\n"
                    if data.get("done"):
                        break
    except* asyncio.TimeoutError:
        yield f"data: {json.dumps({'error': 'LLM response timeout'})}\n\n"
    except* Exception as exc:
        logger.error("llm_stream_error", error=str(exc))
        yield f"data: {json.dumps({'error': 'AI service error'})}\n\n"
```

**Test**: Multi-turn chat — "What are the trends?" then "Summarize them" → verify second query gets rewritten correctly. Kill Ollama mid-stream → client receives error SSE event, not connection hang.  
**Lesson file**: `lessons/step-14-llm-streaming.md`

---

#### Step 15: Citation Engine & Cache Invalidation

**Goal**: Parse, validate, and persist citations from LLM response. Cascade delete behavior: document deletion wipes chunks, embeddings, Redis cache keys, and Elasticsearch index entries atomically.

**Files**:
- `app/services/citation_service.py`
- `app/services/document_lifecycle.py`

**Citation parsing**:
```python
def extract_citations(response_text: str, retrieved_chunks: list[RankedChunk]) -> list[CitationData]:
    cited_ids = re.findall(r'\[Source (\d+)\]', response_text)
    valid_citations = []
    for idx_str in cited_ids:
        idx = int(idx_str) - 1
        if 0 <= idx < len(retrieved_chunks):
            valid_citations.append(CitationData(chunk=retrieved_chunks[idx]))
        else:
            logger.warning("hallucinated_citation", cited_source=idx_str)
            # Strip from response text
    return valid_citations
```

**Document cascade delete**:
```python
async def delete_document(document_id: str, workspace_id: str):
    async with db.begin():  # atomic transaction
        # 1. Delete chunk embeddings from pgvector
        await db.execute(delete(ChunkEmbedding).where(...))
        # 2. Delete leaf chunks + parent chunks
        await db.execute(delete(LeafChunk).where(...))
        await db.execute(delete(ParentChunk).where(...))
        # 3. Delete document record
        await db.execute(delete(Document).where(Document.id == document_id))
        # 4. Delete from Elasticsearch
        await es_client.delete_by_query(index="chunks",
            body={"query": {"term": {"document_id": document_id}}})
        # 5. Flush MinIO file
        await asyncio.wait_for(minio_client.remove_object(bucket, doc.storage_key), timeout=10.0)
        # 6. Invalidate Redis cache namespace
        async for key in redis_client.scan_iter(f"cache:{workspace_id}:*"):
            await redis_client.delete(key)
    logger.info("document_deleted", document_id=document_id, workspace_id=workspace_id)
```

**Test**: Ask a question referencing doc → delete doc → re-ask → confirm Redis cache flushed → LLM says "cannot find". Verify no dangling pgvector entries.  
**Lesson file**: `lessons/step-15-citations-lifecycle.md`

---

### PHASE 4: SAAS LAYER (Steps 16–20)

---

#### Step 16: Usage Tracking & Quota Enforcement

**Goal**: Track token usage per user per month. Enforce monthly query quotas by tier. Display usage in dashboard.

- Count tokens in every LLM response (`len(enc.encode(response_text))`)
- `UPDATE usage_records SET token_count += N WHERE user_id=? AND month=?` (upsert)
- Before each query: check `usage_records.query_count` vs `profile.query_limit_monthly` → raise `QuotaExceededException` if exceeded
- `GET /usage/me` → return current month usage + limits

**Lesson file**: `lessons/step-16-usage-tracking.md`

---

#### Step 17: Conversation History & Session Management

**Goal**: Persistent conversation sessions. Users can list, resume, delete sessions. Session messages form the context window for query rewriting.

- `POST /query/sessions` → create new QuerySession
- `GET /query/sessions` → list sessions for workspace
- `GET /query/sessions/{id}/messages` → paginated message history
- `DELETE /query/sessions/{id}` → cascade delete messages + citations + feedback
- Session memory: last 5 messages fetched and passed to query rewriter (Step 14)

**Lesson file**: `lessons/step-17-conversation-history.md`

---

#### Step 18: Document Management API (Full CRUD)

**Goal**: Complete document lifecycle API — list, status, delete. Bulk operations. Status polling endpoint.

- `GET /documents` → list workspace documents with status, page_count, created_at (paginated)
- `GET /documents/{id}` → single document + presigned download URL
- `GET /documents/{id}/status` → job status polling endpoint
- `DELETE /documents/{id}` → triggers cascade delete from Step 15
- `GET /documents/{id}/chunks` → list chunks for debugging/transparency

**Lesson file**: `lessons/step-18-document-management.md`

---

#### Step 19: Real-Time Notifications (WebSocket + Redis Pub/Sub)

**Goal**: Full WebSocket infrastructure with connection management, Redis pub/sub listener, keep-alive ping, and graceful disconnect.

- `ConnectionManager` class: `connect(ws)`, `disconnect(ws)`, `send_to_workspace(ws_id, msg)`
- Each WS connection spawns a background Redis pub/sub subscriber coroutine
- `WS /ws/{workspace_id}?token={jwt}` → validate token from query param
- WebSocket receives and logs client pings; Starlette handles ping/pong internally
- On `WebSocketDisconnect` or any exception → `finally: await manager.disconnect(ws); cancel_subscriber()`
- Pub/Sub events shape: `{type: "DOCUMENT_READY"|"DOCUMENT_FAILED", document_id, status, message}`

**Lesson file**: `lessons/step-19-websocket-notifications.md`

---

#### Step 20: Observability — Logging, Tracing & Error Monitoring

**Goal**: Production-grade observability. Every request traceable end-to-end across API + Celery workers via correlation ID.

- `structlog` JSON logging configured globally with `correlation_id`, `user_id`, `workspace_id` context vars
- Sentry SDK integrated: `sentry_sdk.init(dsn=settings.SENTRY_DSN)` — captures unhandled exceptions
- OpenTelemetry traces: FastAPI auto-instrumentation + Celery instrumentation
- Grafana dashboard (optional for local): connect to Prometheus scraping FastAPI `/metrics` endpoint
- Health check endpoint: `GET /health` → checks DB connection, Redis ping, MinIO bucket access, Ollama availability

**Lesson file**: `lessons/step-20-observability.md`

---

### PHASE 5: FRONTEND (Steps 21–25)

---

#### Step 21: Next.js Setup & Design System

**Goal**: Next.js 14 (App Router) with Tailwind CSS. Global design tokens. Reusable component library. Dark mode default.

- `npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir`
- Color palette: dark background (#0A0A0F), accent violet (#7C3AED), surface (#1A1A2E)
- Google Fonts: Inter (body), JetBrains Mono (code/citations)
- Components: `Button`, `Card`, `Badge`, `Spinner`, `Avatar`, `Tooltip`, `Modal`
- Global: `axios` client with `Authorization` header injection + `X-Correlation-ID` header

**Lesson file**: `lessons/step-21-frontend-setup.md`

---

#### Step 22: Auth UI

**Goal**: Login, Register, and token refresh flow. JWT stored in memory (not localStorage). Refresh token in HttpOnly cookie.

- `/login` page: email + password form, OAuth buttons (placeholder for v2)
- `/register` page: email + password + confirm
- Auth context: `useAuth()` hook → stores access token in memory, auto-refreshes on expiry
- Protected route wrapper: redirects to `/login` if no valid token
- Form validation: client-side Zod schemas matching backend Pydantic rules

**Lesson file**: `lessons/step-22-auth-ui.md`

---

#### Step 23: Document Management UI

**Goal**: Upload interface with drag-and-drop, real-time status badges driven by WebSocket events, document list, delete confirmation.

- Drag-and-drop upload zone with file validation preview (size, type)
- Status badges: `PENDING` (grey) → `PROCESSING` (blue pulse) → `READY` (green) → `FAILED` (red)
- WebSocket hook: `useDocumentStatus(workspaceId)` → updates badge in real-time
- Document card: filename, page count, upload date, status, actions (view, delete)
- Delete confirmation modal with `"This will permanently remove all AI-indexed data"` warning

**Lesson file**: `lessons/step-23-document-ui.md`

---

#### Step 24: Chat Interface

**Goal**: Streaming chat UI. Citations rendered as inline clickable sources. Confidence badge. Session list sidebar.

- Chat input: multi-line, `Ctrl+Enter` to submit, character counter (max 2000)
- Message streaming: consume SSE stream token by token, render markdown progressively
- Citations: inline `[Source 1]` links → open document viewer modal at cited page
- Confidence badge: `High / Medium / Low` based on score from backend
- Session sidebar: list past sessions, create new, delete
- Empty state: "Upload a document to start asking questions"

**Lesson file**: `lessons/step-24-chat-ui.md`

---

#### Step 25: Dashboard & Settings

**Goal**: Usage dashboard showing token count, query count vs limits, tier toggle (demo), workspace settings.

- Usage card: progress bars for docs used / queries used / storage used
- Tier toggle: `Free ⇄ Pro (Demo Mode)` switch → `PUT /users/me/tier`
- Workspace settings: rename, member list with roles, invite new member
- API Keys section: list keys, generate new, revoke (key shown once via modal)
- Account: change password, delete account (with "type DELETE to confirm" gate)

**Lesson file**: `lessons/step-25-dashboard-settings.md`

---

### PHASE 6: HARDENING (Steps 26–30)

---

#### Step 26: Security Hardening

**Goal**: Harden all HTTP headers, validate all config at startup, ensure no secrets in code.

- `SecurityHeadersMiddleware`: add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy`, `Strict-Transport-Security`
- Startup validation: assert all required env vars present; if `JWT_SECRET` is default placeholder → refuse to start
- Input sanitization: strip HTML from all user-provided strings before storage (use `bleach`)
- API endpoint for health audit: `GET /admin/security-check` (internal only, not exposed via Caddy)

**Lesson file**: `lessons/step-26-security-hardening.md`

---

#### Step 27: Performance Optimization

**Goal**: Redis response caching for repeated identical queries. Connection pre-warming. Query result pagination.

- Cache key: `sha256(f"{workspace_id}:{rewritten_query}")` → TTL 300s
- On query: check Redis first → hit → stream from cache; miss → run full RAG → cache result
- Cache invalidation: on document delete (Step 15 already handles this)
- All list endpoints: cursor-based pagination (`?cursor=&limit=20`)
- Ollama model pre-warming: on app startup, send a dummy embed request so model is loaded

**Lesson file**: `lessons/step-27-performance.md`

---

#### Step 28: Test Suite

**Goal**: Unit tests, integration tests, and RAG quality evaluation.

- `pytest` + `pytest-asyncio` + `httpx.AsyncClient` for API tests
- Unit tests: all service functions with mocked DB and Redis
- Integration tests: full upload → ingest → query flow using test Docker compose
- Auth tests: JWT expiry, refresh rotation, brute force lockout
- Security tests: upload `.sh.pdf` → verify 400; test RLS cross-workspace isolation
- RAG eval: synthetic QA pairs generated from test documents → measure context precision and answer groundedness (`LLM-as-judge` prompts)

**Lesson file**: `lessons/step-28-testing.md`

---

#### Step 29: Docker & Deployment Pipeline

**Goal**: Production-ready Docker images. CI pipeline. Zero-downtime deployment config.

- Multi-stage Dockerfile: `builder` (install deps) → `production` (non-root user, minimal image)
- `.dockerignore`: exclude `.env`, `__pycache__`, test files
- `docker-compose.prod.yml`: override for production (no dev ports exposed, Caddy with real TLS)
- GitHub Actions CI: on push → lint (ruff) → type-check (mypy) → tests → build image
- Health checks in compose: all services have `healthcheck` blocks
- Graceful shutdown: FastAPI handles `SIGTERM` → finishes in-flight requests → exits

**Lesson file**: `lessons/step-29-deployment.md`

---

#### Step 30: Documentation & Lessons Index

**Goal**: Complete OpenAPI docs, developer README, and lessons index as a learning reference.

- FastAPI auto-generates OpenAPI at `/docs` and `/redoc`
- `README.md`: project overview, architecture diagram, quick-start (`docker compose up`)
- `CONTRIBUTING.md`: code standards (exceptions, async rules, query patterns)
- `lessons/index.md`: table of all 30 lessons with links and concept index
- Architecture diagram: update with final state using ASCII or Mermaid

**Lesson file**: `lessons/step-30-documentation.md`

---

## 8. Lesson File Structure

Every step produces one file under `lessons/`. Template:

```markdown
# Step XX — [Step Name]

## What You're Building
One paragraph. What this step delivers and why it matters in the system.

## Concepts Covered
| Concept | Definition | Why It Matters Here |
|---|---|---|
| e.g. HNSW Index | Graph-based ANN index | Enables sub-millisecond vector search at scale |

## Files Created / Modified
| File | Role |
|---|---|
| app/services/xxx.py | Handles ... |

## Engineering Standards Applied (from §5)
List which global rules from Section 5 appear in this step's code.
e.g. - `.first()` + None check for all DB queries
    - `asyncio.wait_for` on all Ollama calls

## Code Walkthrough
Key functions explained line by line.

## How to Test This Step
```bash
# Commands to run
docker compose up -d
pytest tests/test_step_XX.py -v
```
Expected output.

## Common Errors & Fixes
| Error Message | Root Cause | Fix |
|---|---|---|

## What's Next
One sentence bridging to the next step.
```

---

> **Plan Version**: 2.0 FINAL  
> **Approval Status**: Awaiting sign-off to begin Step 1  
> **Scope**: Steps 1–15 are the core RAG product. Steps 16–20 are SaaS layer. Steps 21–25 are frontend. Steps 26–30 are hardening.
