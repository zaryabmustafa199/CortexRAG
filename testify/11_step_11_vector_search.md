# Step 11 — Vector Search (pgvector)

## What You're Building
A semantic similarity search service utilizing the `pgvector` extension inside PostgreSQL. It runs cosine distance calculations ($<=>$ operator) over LeafChunk vector embeddings, limits outputs to a configurable top-k value, and operates under strict multi-tenant workspace Row-Level Security (RLS) policies.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **pgvector** | A PostgreSQL extension allowing storage and similarity indexing of high-dimensional vector embeddings | Eliminates the complexity of running a standalone vector database (like Pinecone or Milvus), keeping the data stack local and unified |
| **Cosine Distance** | A metric measuring the angular direction similarity between two vectors (regardless of magnitude) | Standard similarity metric for text embeddings, where $1.0 - \text{distance}$ yields the similarity score |
| **HNSW Indexing** | Hierarchical Navigable Small World graphs constructed on vector columns | Speeds up similarity search from linear scans $O(N)$ to logarithmic approximate nearest neighbor lookups $O(\log N)$ |
| **RLS Isolation** | Enforcing PostgreSQL database security policies based on a local connection parameter | Restricts chunk vector reads strictly to the current workspace context, preventing cross-tenant leakage |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/vector_search_service.py` | pgvector query generator with RLS setup and distance-to-similarity conversion | Created |

---

## Engineering Standards Applied (§5)

- **Strict Database Timeouts** — Enforces a 10.0-second statement execution gate using `asyncio.wait_for` to terminate runaway vector matches.
- **Metric Conversion** — Properly converts pgvector's raw cosine distance float output into a client-friendly similarity score: $\text{similarity} = 1.0 - \text{distance}$.
- **Isolated Transactions** — Sets the RLS `app.workspace_id` local connection parameter prior to running queries, preventing workspace leakage.

---

## How to Test This Step

```python
# Create a test script in scratch/test_vector_search.py
import asyncio
import uuid
from app.db.session import AsyncSessionLocal
from app.services.vector_search_service import VectorSearchService

async def test():
    # Set target workspace
    workspace_id = uuid.uuid4()
    
    async with AsyncSessionLocal() as db:
        service = VectorSearchService(db)
        
        # Mock a 768-dimensional query vector (e.g. nomic model)
        query_vector = [0.01] * 768
        
        # Execute search
        results = await service.vector_search(query_vector, workspace_id, top_k=5)
        print("Search Results:", len(results))

asyncio.run(test())
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `Semantic vector search timed out` | Database connection pools were saturated or index was missing | Ensure database connections are recycled and the HNSW index migration has been fully executed |
| Results do not contain matches | Workspace ID does not own any chunks or database RLS blocked the query | Verify the target workspace contains active documents marked as `READY` in the DB |
| Mismatch in vector dimensions | Query vector size (e.g. 1536) does not match DB columns (e.g. 768) | Align the query model in environment settings with the model used during document ingestion |

---

## What's Next

**Step 12** — Hybrid Search & Result Merging: combine pgvector semantic searches with Elasticsearch keyword BM25 queries, executing matches in parallel and resolving ranks via Reciprocal Rank Fusion (RRF).
