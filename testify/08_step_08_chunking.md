# Step 08 — Hierarchical Chunking (Parent-Child)

## What You're Building
A hierarchical chunking module that processes document page streams into ParentChunks (section-level, ~3000 tokens) and child LeafChunks (paragraph-level, ~400 tokens with 50 token overlap). The splitter is token-aware (using `tiktoken` with the `cl100k_base` encoding) and sentence-boundary-aligned. It automatically detects section headers via regex, extracts numerical years from content for downstream temporal search, prepends structural page/section metadata, and persists the parent-child relational hierarchy in the database.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Hierarchical Chunking** | Splitting text into large parent blocks (for summaries/context) and smaller overlapping leaf chunks (for embedding searches) | Improves context quality: small vector matches fetch large surrounding sections, resolving "lost-in-the-middle" LLM attention issues |
| **Token-Aware Splitting** | Counting boundaries by model tokens (using tiktoken) rather than character or word counts | Prevents chunks from being truncated mid-word or overflowing LLM/embedding window context lengths |
| **Sentence-Aligned Boundaries** | Splitting chunks exclusively at sentence endings (`.`, `!`, `?`) | Preserves paragraph context, ensuring the LLM doesn't receive fragmented phrases that degrade search accuracy |
| **Dynamic Overlap** | Keeping a sliding window of sentences from the end of the previous chunk in the next | Maintains semantic continuity across chunk boundaries (no lost facts at the margins) |
| **Metadata Injection** | Prepended tags like `[Page X | Section: Y]` added to each leaf chunk text | Injects hard page/title metadata directly into the vector space, enhancing search results |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/chunking_service.py` | Core chunker logic: token counting, section detection, parent/leaf splitters | Created |
| `app/worker/tasks/chunking.py` | Worker task helper that processes the stream and inserts chunks into the DB | Created |

---

## Engineering Standards Applied (§5)

- **Non-blocking Event Loop** — Calls `await asyncio.sleep(0)` after generating each parent chunk to keep the Celery/API async loop active.
- **Relational Integrity** — Executes child inserts only after parent `flush()` operations yield relational UUID foreign keys.
- **Robust Tokenizer Fallback** — Implements a safe character-length division fallback if offline execution prevents `tiktoken` vocabulary initialization.
- **RLS Denormalization** — Propagates `workspace_id` directly onto parent and child tables, allowing Postgres RLS to filter chunks without complex multi-table JOINs.

---

## How to Test This Step

```python
# Create a test script in scratch/test_chunker.py
import asyncio
from app.services.chunking_service import build_parent_chunks, build_leaf_chunks

async def test():
    # 1. Create mock pages
    pages = [
        {"page": 1, "text": "SECTION 1. INTRODUCTION\nThis is a long introductory sentence. Here is another sentence containing the year 2026."},
        {"page": 2, "text": "This is page 2 text. We are discussing the RAG framework architecture."}
    ]
    
    # 2. Build parents
    parents = await build_parent_chunks(pages)
    print("Parents:", parents)
    
    # 3. Build leaves
    leaves = build_leaf_chunks(parents[0]["content"], 1, 2, parents[0]["section_title"])
    print("Leaves count:", len(leaves))
    print("First leaf:", leaves[0])

asyncio.run(test())
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| Chunks are missing parent relationships | DB session was committed before mapping child IDs | Ensure parent is added and `await db.flush()` is called prior to building leaf chunks |
| `tiktoken` slows down or fails | No internet connection to download the `cl100k_base` cache | The chunking service catches the initialization error and falls back to character estimation automatically |
| Chunks are split in the middle of words | Sentence boundary regex matched standard periods in decimal numbers (e.g. `1.5`) | The regex matches `(?<=[.!?])\s+` which checks that a period is followed by spaces, preventing splits on simple floats |

---

## What's Next

**Step 9** — Embedding Generation: construct a multi-provider service (Ollama / OpenAI) that generates embeddings for leaf chunks in parallel batches of 32 using structured task gathers.
