# CortexRAG Lessons Index

This index acts as a reference guide mapping every phase of construction to its corresponding lesson file, tech concepts covered, and verified directories.

---

## Phase 1: Foundation (Steps 1–5)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 01 | [step-01-project-setup.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-01-project-setup.md) | Project Setup & Infrastructure | FastAPI apps, Docker networks, Configuration, exception handling |
| 02 | [step-02-database-schema.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-02-database-schema.md) | Database Schema & Migrations | Alembic, pgvector, HNSW indexing, RLS policy generation |
| 03 | [step-03-authentication.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-03-authentication.md) | Authentication System | JWT signing, token rotation, brute force Redis counters |
| 04 | [step-04-user-workspace.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-04-user-workspace.md) | User & Workspace CRUD | Membership roles, SaaS tier caps, GDPR accounts erasure |
| 05 | [step-05-api-keys-rate-limiting.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-05-api-keys-rate-limiting.md) | API Keys & Rate Limiting | Sliding window rate limits, key hashes, raw tokens creation |

---

## Phase 2: Document Pipeline (Steps 6–10)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 06 | [step-06-file-upload-storage.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-06-file-upload-storage.md) | File Upload & MinIO Storage | Magic bytes, double extension blocks, presigned URLs |
| 07 | [step-07-text-extraction.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-07-text-extraction.md) | Text Extraction | PyMuPDF streams, text decoding, XXE & SSRF mitigation |
| 08 | [step-08-chunking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-08-chunking.md) | Hierarchical Chunking | Tiktoken-aware splitters, parent-child relations, overlapping |
| 09 | [step-09-embeddings.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-09-embeddings.md) | Embedding Generation | Ollama inference, batch processing, dynamic dimensions |
| 10 | [step-10-celery-workers.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-10-celery-workers.md) | Celery Queue & Worker Health | `acks_late` reliability, worker recycles, Redis notifications |

---

## Phase 3: RAG Engine (Steps 11–15)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 11 | [step-11-vector-search.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-11-vector-search.md) | Vector Search (pgvector) | Cosine distances, HNSW search, DB session RLS context |
| 12 | [step-12-hybrid-search.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-12-hybrid-search.md) | Hybrid Search & Merging | Elasticsearch BM25, Reciprocal Rank Fusion (RRF) |
| 13 | [step-13-reranking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-13-reranking.md) | Cross-Encoder Re-ranking | MS-MARCO re-ranking, structured context headers |
| 14 | [step-14-llm-streaming.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-14-llm-streaming.md) | LLM Streaming & SSE | SSE generators, query rewriting, mid-stream abort handles |
| 15 | [step-15-citations-lifecycle.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-15-citations-lifecycle.md) | Citations & Cache Purging | Source parsing, cascade deletion, Redis cache invalidation |

---

## Phase 4: SaaS Layer (Steps 16–20)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 16 | [step-16-usage-tracking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-16-usage-tracking.md) | Usage Tracking & Quota | Monthly counters, quota check middleware |
| 17 | [step-17-conversation-history.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-17-conversation-history.md) | Sessions Management | Conversational state memory, thread storage |
| 18 | [step-18-document-management.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-18-document-management.md) | Document Management API | Document CRUD, chunk listing, status polling |
| 19 | [step-19-websocket-notifications.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-19-websocket-notifications.md) | WebSockets & Pub/Sub | Connection managers, Redis pub/sub routing, WS pings |
| 20 | [step-20-observability.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-20-observability.md) | Observability & Tracing | Correlation ID middleware, Sentry errors, structlog |

---

## Phase 5: Frontend (Steps 21–25)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 21 | [step-21-frontend-setup.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-21-frontend-setup.md) | Next.js & Design System | Dark mode palette, Tailwind utilities, Zod schemas |
| 22 | [step-22-auth-ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-22-auth-ui.md) | Auth UI Forms | In-memory token storage, cookie refresh rotation hooks |
| 23 | [step-23-document-ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-23-document-ui.md) | Documents Upload UI | WS status badges, dropzones, cascade delete modals |
| 24 | [step-24-chat-ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-24-chat-ui.md) | Chat Streaming UI | Progress SSE stream, inline citations, confidence badges |
| 25 | [step-25-dashboard-settings.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-25-dashboard-settings.md) | Settings & Usage Dashboard | Quota usage bars, workspace renaming, api key CRUD |

---

## Phase 6: Hardening & Deployment (Steps 26–30)

| Step | Lesson File | Description | Core Concepts |
|:---:|---|---|---|
| 26 | [step-26-security-hardening.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-26-security-hardening.md) | HTTP & Data Security | Security middleware, HTML stripping, admin routes blocking |
| 27 | [step-27-performance.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-27-performance.md) | Performance Tuning | Redis RAG cache, model pre-warming, cursor pagination |
| 28 | [step-28-testing.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-28-testing.md) | Test Suite | SQLAlchemy TextClause tests, mocks isolation, RAG eval |
| 29 | [step-29-deployment.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-29-deployment.md) | Docker & Deployment Pipeline | Multi-stage Docker, compose overrides, GHA automation |
| 30 | [step-30-documentation.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/lessons/step-30-documentation.md) | Documentation & Index | Platform README, Contributing rules, lessons index |
