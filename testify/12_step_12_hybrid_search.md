# Step 12 — Hybrid Search & Result Merging

## What You're Building
A hybrid search orchestrator that combines semantic similarity search (pgvector) with keyword keyword matches (Elasticsearch BM25). Both search engines execute in parallel, and their output rankings are merged and deduplicated using Reciprocal Rank Fusion (RRF). Any keyword matches returned by Elasticsearch that are missing from pgvector's DB cache are automatically resolved from the SQL database to construct fully loaded objects before returning the top 25 merged results.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Hybrid Search** | Running vector search (concept matching) and BM25 search (keyword matching) together | Achieves optimal search recall: handles conceptual queries ("health updates") and exact term queries ("Drug-X 20mg") equally well |
| **BM25 Algorithm** | Best Match 25 — a probabilistic relevance algorithm evaluating keyword frequency, document length, and inverse document frequency | Production-standard keyword query relevance algorithm (built-in to Elasticsearch) |
| **Reciprocal Rank Fusion (RRF)** | A rank-merging algorithm that sums the reciprocal ranks of a document across multiple search systems | Enables sorting merged results without normalizing raw, incomparable scoring metrics (cosine distance vs BM25 score) |
| **RRF Constant ($k=60$)** | A tuning parameter smoothing rank positions | Standard RRF parameter preventing top-1 rankings from overwhelmingly dominating intermediate search results |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/bm25_service.py` | Elasticsearch BM25 index creation, search queries, and delete handlers | Created |
| `app/services/retrieval_service.py` | Hybrid search orchestrator running parallel gathers and RRF rank sorting | Created |
| `app/worker/tasks/chunking.py` | Calls Elasticsearch indexing during LeafChunk commits | Modified |
| `app/main.py` | Calls Elasticsearch index initialization on application startup | Modified |

---

## Engineering Standards Applied (§5)

- **Fail-Open Concurrency** — Parallel gathers catch search server failures (e.g. Elasticsearch down); the orchestrator logs warning tracebacks and fails open, returning the remaining database results.
- **Auto DB Resolution** — Resolves missing database objects in a single batch query (`LeafChunk.id.in_(missing_ids)`), preventing expensive $N+1$ single-row SELECT loops.
- **Async Indexing** — Celery workers index leaf chunks concurrently using `asyncio.gather` after database commits.

---

## How to Test This Step

```python
# Create a test script in scratch/test_hybrid.py
import asyncio
import uuid
from app.db.session import AsyncSessionLocal
from app.services.retrieval_service import RetrievalService

async def test():
    workspace_id = uuid.uuid4()
    query_text = "system architecture"
    query_vector = [0.01] * 768  # mock vector
    
    async with AsyncSessionLocal() as db:
        service = RetrievalService(db)
        results = await service.hybrid_search(query_text, query_vector, workspace_id, top_k=10)
        print("Merged Hybrid Results:", len(results))

asyncio.run(test())
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `elasticsearch_search_failed` | Elasticsearch container is down or unreachable | Check status: `docker compose ps elasticsearch`. Ensure Elasticsearch is running and port 9200 is open |
| RRF scores are flat | Document has not been indexed in Elasticsearch | Make sure documents uploaded after Step 12 are processed so the Celery worker indexes them |
| Database resolution fails | A chunk ID in Elasticsearch refers to a deleted database row | Safe behavior; unresolved chunks are ignored by RRF |

---

## What's Next

**Step 13** — Cross-Encoder Re-ranking & Context Assembly: filter the top 25 merged results down to the most relevant 5 using a cross-encoder model and assemble the structured LLM context window.
