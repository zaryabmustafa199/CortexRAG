# Step 24 — Chat Interface

## What You're Building
The RAG conversation engine chat interface. This step builds the `/dashboard/chat` Next.js page featuring a dual-pane sidebar/chat panel layout. Users can create, list, and delete chat sessions. Input questions trigger the backend RAG pipeline via custom SSE (Server-Sent Events) chunk streaming. The chat client progressively renders markdown response text, parses inline source citation tags (e.g. `[Source 1]`) as interactive buttons, displays overall answer confidence scores, and exposes a detailed citation inspector showing cited document metadata, location page numbers, and vector chunk snippets.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **SSE Stream Chunking** | Consuming progressive stream blocks using browser `ReadableStream` | Allows real-time typing responses in the client rather than waiting for complete LLM generation |
| **Interactive Inline Citations** | Parsing source citation patterns and replacing them with buttons | Connects text claims directly to primary sources, increasing platform trust and accountability |
| **Eager DB Relationship Loading** | Preloading multi-level tables (Citation -> Leaf -> Parent -> Doc) | Avoids async SQLAlchemy lazy-loading attribute errors when returning session histories |
| **Multi-turn History Rewriting** | Restructuring questions using the last 5 turns of conversation | Resolves pronouns (e.g. "what does it say?") into standalone queries before vector retrieval |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `backend/app/api/v1/query.py` | Backend query router handling Ask SSE and eager message loading | Modified |
| `backend/app/schemas/query.py` | Pydantic response models containing dynamic citation resolution | Modified |
| `frontend/app/dashboard/chat/page.tsx` | Main chat view panel, conversation sidebar, and citation modals | Created |

---

## Engineering Standards Applied (§5)

- **Strict In-Memory JWT Injection** — The chat stream fetch call injects authorization headers directly from memory state, keeping access tokens completely clean of `localStorage`.
- **Eager Relationship Joins** — The backend database query uses `.options(selectinload(...))` to recursively preload parent chunks and source documents in a single query.
- **Graceful SSE Fallbacks** — Streaming fetch loop handles server disconnects and parsing issues cleanly without freezing the user interface.

---

## How to Test This Step

```bash
# Verify backend query router compiles successfully
python -m py_compile backend/app/api/v1/query.py

# Verify frontend Next.js compilation is clean
npx tsc --noEmit

# Run local development servers
npm run dev # inside frontend
uvicorn app.main:app --reload # inside backend (if running locally)

# Open browser at http://localhost:3000/dashboard/chat
# 1. Click "New" to start a chat session
# 2. Enter a query referencing uploaded document concepts
# 3. Verify real-time token-by-token streaming
# 4. Click the superscript [1] citation badge and verify citation modal shows original text snippet
# 5. Type a follow-up ("summarize that") and check query rewriting in logs
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `DetachedInstanceError` in SQLAlchemy | Messages fetched in route handler accessed unloaded citation/chunk variables after session closed | Add `selectinload` options chain to fetch the child citation leaf-chunks, parent-chunks, and documents eagerly in the SQL query |
| `TypeError: Failed to execute 'fetch' on 'Window'` | Fetch base URL was incorrect or relative in the client | Set correct `NEXT_PUBLIC_API_URL` environment variable in the `.env` configuration file |

---

## What's Next

**Step 25** — Dashboard & Settings: implement the user settings dashboard displaying monthly token and document ingestion usage metrics, switchable Free/Pro tiers, API key CRUD interfaces, and workspace membership invites.
