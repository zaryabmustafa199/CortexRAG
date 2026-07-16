# CortexRAG — Master Automated Testing & Verification Plan

This document defines the comprehensive testing plan for verifying the entire CortexRAG platform. It bridges the structural phases (Phase 1 to Phase 6) with automated verification scripts, describing how another AI model or quality assurance system can verify the codebase.

---

## 1. Automated Verification Topology

```
┌─────────────────────────────────────────────────────────────┐
│  TEST RUNNER (scripts/run_e2e_tests.py)                     │
│  Simulates client calls programmatically using Async HTTP   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    [API GATEWAY LAYER] [APPLICATION LAYER]  [DATA STORE LAYER]
    Caddy Proxy Ports   FastAPI Endpoints    PostgreSQL RLS settings
    Security Headers    JWT / Auth Rotation  Redis Cache namespace
    Admin URI Blockers  Celery queue status  MinIO object buckets
                        RAG RRF retrieves    Elasticsearch indices
```

---

## 2. Phase-by-Phase Verification Plan

### Phase 1: Environment & Services Health Probes
* **Objective**: Ensure backing services are healthy before executing application-level scripts.
* **Testify MD Reference**: [01_step_01_project_setup.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/01_step_01_project_setup.md), [02_step_02_database_schema.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/02_step_02_database_schema.md), [10_step_10_celery_workers.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/10_step_10_celery_workers.md)
* **Automated Checks**:
  1. Call `GET http://localhost:8000/health`. Assert status code `200` and response body `"status": "healthy"`.
  2. Parse the services health nested status block:
     ```json
     {
       "services": {
         "postgres": "ok",
         "redis": "ok",
         "minio": "ok",
         "llm_provider": "ok"
       }
     }
     ```
  3. Verify PostgreSQL connection pooling parameters: statement timeout = 30s, pre-ping enabled.

### Phase 2: Authentication & Multi-Tenancy (Steps 3–5, 22, 25)
* **Objective**: Verify that user accounts are isolated, passwords are complex, and API keys are rate-limited.
* **Testify MD Reference**: [03_step_03_authentication.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/03_step_03_authentication.md), [04_step_04_user_workspace.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/04_step_04_user_workspace.md), [05_step_05_api_keys_rate_limiting.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/05_step_05_api_keys_rate_limiting.md), [22_step_22_auth_ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/22_step_22_auth_ui.md)
* **Automated Checks**:
  1. **Password Complexity**: Submit `POST /auth/register` with a weak password (e.g. `1234`). Assert response code `422 Unprocessable Entity` and verify error details contain complexity warning messages.
  2. **JWT Lifecycle**: Register a valid user, login, and obtain the `access_token`. Request a secure endpoint without header (assert 401), with key (assert 200).
  3. **Refresh Cookie**: Call `POST /auth/refresh` and verify that the old refresh token hash in Redis is invalidated, while a new rotated JWT access token is issued.
  4. **Workspace Isolation**: Call `POST /workspaces` with a user's JWT. Create a second user, try to query workspace 1, and verify that the system returns `403 Forbidden` or `404 Not Found`.
  5. **API Key Rate Limit**: Execute 61 concurrent requests using a generated API Key. Verify that the 61st query returns `403 Forbidden` with `"Rate limit exceeded"`.

### Phase 3: Document Ingestion Pipeline (Steps 6–10, 18, 23)
* **Objective**: Verify file validation filters, object storage integrity, and celery chunking workers.
* **Testify MD Reference**: [06_step_06_file_upload_storage.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/06_step_06_file_upload_storage.md), [07_step_07_text_extraction.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/07_step_07_text_extraction.md), [08_step_08_chunking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/08_step_08_chunking.md), [09_step_09_embeddings.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/09_step_09_embeddings.md), [23_step_23_document_ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/23_step_23_document_ui.md)
* **Automated Checks**:
  1. **Binary Extension Validation**: Attempt to upload a python script named `payload.py.pdf` containing binary ELF headers. Assert response returns `400 Bad Request` with `"File rejected"`.
  2. **Valid Upload & Polling**: Upload a text document containing key terms. Extract the `id` from the `202 Accepted` response. Poll `GET /documents/{id}/status` until status equals `READY`.
  3. **Data Verification**: Query the database using a mock session:
     - Verify that chunks exist in the `parent_chunks` and `leaf_chunks` tables with matching `workspace_id`.
     - Verify that `chunk_embeddings` contains vectors with a dimension of `768` (for nomic-embed-text).

### Phase 4: Hybrid Search & RAG Generation (Steps 11–15, 17, 24)
* **Objective**: Verify Reciprocal Rank Fusion math, Cross-Encoder scoring, LLM streaming context injection, and citation tracing.
* **Testify MD Reference**: [11_step_11_vector_search.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/11_step_11_vector_search.md), [12_step_12_hybrid_search.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/12_step_12_hybrid_search.md), [13_step_13_reranking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/13_step_13_reranking.md), [14_step_14_llm_streaming.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/14_step_14_llm_streaming.md), [15_step_15_citations_lifecycle.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/15_step_15_citations_lifecycle.md), [24_step_24_chat_ui.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/24_step_24_chat_ui.md)
* **Automated Checks**:
  1. **RRF & Re-ranking Validation**: Run pytest on `test_rag.py`. Assert that RRF ranking calculations prioritize chunks appearing in both vector and keyword matching pools, and cross-encoder re-ranking runs successfully.
  2. **SSE Streaming Ask**: Call `POST /query/ask` and parse the SSE generator token-by-token. Verify that the response contains the terms from the uploaded document, and that inline `[Source 1]` citations are returned matching actual leaf chunk IDs.
  3. **Row-Level Security**: Execute a similarity query with a local session containing a mismatched local workspace parameter (`SET LOCAL app.workspace_id`). Assert that the query returns `0` results (validating multi-tenant separation).

### Phase 5: SaaS Quotas, Cache Invalidation, and WebSocket Events (Steps 15, 16, 19, 27)
* **Objective**: Verify that usage is counted, cached responses return instantly, and updates push via WebSockets.
* **Testify MD Reference**: [15_step_15_citations_lifecycle.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/15_step_15_citations_lifecycle.md), [16_step_16_usage_tracking.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/16_step_16_usage_tracking.md), [19_step_19_websocket_notifications.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/19_step_19_websocket_notifications.md), [27_step_27_performance.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/27_step_27_performance.md)
* **Automated Checks**:
  1. **Redis Cache Speedup**: Submit the identical query from Phase 4. Verify that the response duration is < 100ms (Cache hit), and that it simulates natural token typing.
  2. **Free Tier Quotas**: Change the profile tier to `free` and upload more than 5 documents. Verify the server rejects the 6th upload with `403 QuotaExceededException`.
  3. **WS Event Push**: Connect to the WebSocket route `WS /ws/{workspace_id}`. Upload a new document and verify that the socket client receives a JSON message `"type": "DOCUMENT_READY"`.
  4. **Cache Invalidation**: Call `DELETE /documents/{id}`. Submit the query again and assert that it triggers a cache miss, bypasses deleted documents, and returns a graceful message.

### Phase 6: Hardening, Security Headers, and Compilation Checks (Steps 26, 28, 29)
* **Objective**: Verify HTTP hardening constraints, admin route restrictions, and compiler type-safety.
* **Testify MD Reference**: [26_step_26_security_hardening.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/26_step_26_security_hardening.md), [28_step_28_testing.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/28_step_28_testing.md), [29_step_29_deployment.md](file:///d:/Projects/PORTFOLIO/CORTEXRAG/testify/29_step_29_deployment.md)
* **Automated Checks**:
  1. **HTTP Headers Probes**: Request the landing page and probe headers. Verify the presence of:
     - `Content-Security-Policy`
     - `X-Frame-Options: DENY`
     - `X-Content-Type-Options: nosniff`
  2. **Admin Blocks**: Send a request to `GET /admin/security-check` on port 80. Verify that Caddy blocks the request and returns `403 Forbidden` or `Access Denied`.
  3. **Frontend Compilation**: Run TypeScript verification.
  4. **Backend Test Suite**: Run backend unit and integration test suite.

---

## 3. How to Execute the Master Testing Plan

Follow these steps to run the entire automated verification suite:

### Step 1: Spin Up Backing Infrastructure
Ensure all services are running and Ollama models are pre-warmed:
```bash
docker compose up -d --build
```

### Step 2: Run Backend Integration & Unit Tests
Run the unit test suite:
```bash
cd backend
poetry run pytest
```

### Step 3: Run TypeScript Type-Checks
Verify that frontend compiles without warnings:
```bash
cd frontend
npx.cmd tsc --noEmit
```

### Step 4: Run E2E Automated Verification Runner
Run the master E2E flow simulation script:
```bash
python scripts/run_e2e_tests.py
```
This script acts as the automated test suite verifying auth tokens, uploads, Celery statuses, SSE streams, RRF search fusion, and security headers.
