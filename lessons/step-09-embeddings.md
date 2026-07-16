# Step 09 — Embedding Generation & Dynamic Vector Schema

## What You're Building
A robust, multi-provider embedding generation service that handles vector creation for LeafChunks. It supports local Ollama execution (`nomic-embed-text`, 768-dim) and OpenAI cloud execution (`text-embedding-3-small`, 1536-dim), automatically selecting the configuration from the active environment settings. It manages batching in groups of 32 prompts, uses structured concurrency (`asyncio.gather`), sets strict connection timeouts, and persists vectors in the database tracking the associated model name.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Multi-Provider Router** | Abstracting embedding logic behind a unified interface supporting multiple APIs | Prevents vendor lock-in and allows seamless switching between zero-cost local nominate models and OpenAI |
| **Concurrent Batching** | Splitting large prompt groups into chunks of 32 and gathering results concurrently | Maximizes API throughput: OpenAI handles all 32 items in a single HTTP request; Ollama runs 32 threads concurrently |
| **Dynamic Vector Schema** | Mapping columns in pgvector to `active_embed_dim` | Ensures model migrations are handled programmatically without hardcoding coordinate lengths |
| **Structured Concurrency** | Gathering tasks via `asyncio.gather(*tasks, return_exceptions=True)` | Catches connection issues or network exceptions safely, preventing partial batch corruption |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/embedding_service.py` | Embedding generation client routing Ollama/OpenAI APIs with batching | Created |
| `app/worker/tasks/embedding.py` | Task orchestrator that gathers chunk text, generates vectors, and saves them | Created |

---

## Engineering Standards Applied (§5)

- **Batched Network Gather** — Prompts are grouped in blocks of 32; failures in a single gather abort the transaction with an `EmbeddingException` to prevent half-finished document states.
- **Fail-Safe Connection Timeouts** — HTTP requests enforce connection timeouts (5.0s connect, 30.0s read) using `asyncio.wait_for`.
- **Dynamic Model Tracking** — Persists `model_name` directly in the `chunk_embeddings` records, tracking which model coordinates belong to for index isolation.
- **Transactional Consistency** — Embeddings are added and committed in single SQL transactions to prevent orphans.

---

## How to Test This Step

```python
# Create a test script in scratch/test_embeddings.py
import asyncio
from app.services.embedding_service import EmbeddingService

async def test():
    service = EmbeddingService()
    print("Active Model:", service.active_model_name)
    
    texts = ["CortexRAG is local-first.", "Embeddings are 768-dimensional."]
    vectors = await service.embed_texts(texts)
    
    print("Vectors generated:", len(vectors))
    print("First vector dimension:", len(vectors[0]))

asyncio.run(test())
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `ollama_embedding_batch_failure` | Local Ollama container is down or has not loaded the model | Run `ollama pull nomic-embed-text` and check container status |
| `openai_key_required_if_provider_openai` | Config set to OpenAI but `OPENAI_API_KEY` is blank | Set the API key in your `.env` configuration file |
| Vector dimension mismatch in DB | DB was migrated with a different embedding size | Run Alembic reset migrations or ensure `EMBED_DIM` matches database column dimensions |

---

## What's Next

**Step 10** — Celery Task Queue & Worker Health: orchestrate download, parse, chunk, embed, and database persistence in the main `ingest_document` task with worker recycles, custom retries, and Redis pub/sub completion events.
