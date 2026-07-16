# Step 13 — Cross-Encoder Re-ranking & Context Assembly

## What You're Building
A re-ranking and prompt context assembly service. It uses a local Cross-Encoder model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to re-score the top 25 hybrid search chunks down to the most relevant 5. It runs model inference in a background thread executor to prevent blocking the async loop, handles time-outs and connection fallbacks gracefully, and formats the output into a structured source context string containing page numbers, document UUIDs, and section titles for the LLM generator.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Cross-Encoder Re-ranking** | An inference model processing query and document text simultaneously to output a precise relevance score | Overcomes limitations of bi-encoders (which index vectors independently), maximizing retrieval precision |
| **Lazy Loading Singleton** | Initializing heavy model weight objects only on first demand | Prevents web server startup bottlenecks while preserving GPU/CPU memory |
| **Thread Executor Offloading** | Moving heavy CPU-bound model predictions out of the event loop | Prevents API endpoints from freezing and keeps FastAPI responsive |
| **Source Context Assembly** | Formatting raw textual chunks into structured blocks divided by markdown tags | Standardizes context formatting so LLMs can cite specific page numbers, section titles, and source document IDs accurately |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/reranker_service.py` | Lazy initializes the cross-encoder and executes re-ranking in executors | Created |
| `app/services/context_builder.py` | Assembles final chunk arrays into markdown templates | Created |

---

## Engineering Standards Applied (§5)

- **Execution Timeout** — Restricts model inference to 15.0 seconds using `asyncio.wait_for`, preventing resource exhaustion during heavy server load.
- **Fail-Open Fallback** — Catches all exceptions and falls back to raw RRF order without blocking search requests.
- **Lazy Singleton Init** — Minimizes model weight loading overhead by instantiating the cross-encoder only on first demand.

---

## How to Test This Step

```python
# Create a test script in scratch/test_reranker.py
import asyncio
from app.services.reranker_service import RerankerService
from app.services.context_builder import build_context
from app.models.document import LeafChunk

async def test():
    # 1. Setup mock chunks
    chunk_1 = LeafChunk(content="CortexRAG uses pgvector and Elasticsearch.")
    chunk_2 = LeafChunk(content="The capital of France is Paris.")
    results = [
        {"chunk": chunk_1, "rrf_score": 0.5},
        {"chunk": chunk_2, "rrf_score": 0.4}
    ]
    
    # 2. Rerank
    service = RerankerService()
    reranked = await service.rerank("What databases does CortexRAG use?", results)
    print("Top Reranked Chunk Content:", reranked[0]["chunk"].content)
    
    # 3. Build Context
    context = build_context(reranked)
    print("\nAssembled Context:\n", context)

asyncio.run(test())
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| Model fails to load | `sentence-transformers` is not installed or download is blocked | Verify packages are loaded in the virtual environment. Ensure the container has network access to download weights from Hugging Face on first run |
| Slow API response | Model runs directly inside the event loop | Ensure you invoke the model inside the thread executor: `asyncio.get_event_loop().run_in_executor` |
| `reranker_timeout_fallback` | CPU-bound model inference exceeded 15 seconds | Allocate more CPU cores to the environment or check background tasks |

---

## What's Next

**Step 14** — LLM Integration — Query Rewriting & Streaming Response: fetch conversational history, rewrite follow-up queries, format system templates, and stream prompt responses via Server-Sent Events (SSE).
