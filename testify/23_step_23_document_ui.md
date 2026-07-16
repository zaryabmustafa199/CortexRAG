# Step 23 — Document Management UI

## What You're Building
The document intelligence management dashboard interface. This step builds the `/dashboard/documents` page which allows users to drag-and-drop document files, see real-time processing status updates powered by WebSocket event channels, generate presigned download URLs, open a deletion cascade prompt with safety locks, and inspect hierarchical section/leaf database chunks inside a structured inspector window.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Drag & Drop API** | HTML5 drag-and-drop file ingestion handlers | Improves UX by allowing simple file drops directly into the browser viewport |
| **Real-Time Badge Updates** | Updating document cards instantly when receiving WebSocket events | Keeps UI in sync with async Celery extraction workers without requiring page refreshes |
| **Chunk Hierarchical View** | A tree structure mapping ParentChunks to child LeafChunks | Provides transparency to audit parser and splitter quality, crucial for RAG fine-tuning |
| **Delete Safety Gating** | Forcing modals that explain database-cascade dependencies | Prevents users from accidentally deleting vectors or storage objects without understanding the RAG impacts |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `hooks/useDocumentStatus.ts` | React Hook subscribing to backend WebSocket events | Created |
| `app/dashboard/layout.tsx` | Dashboard shell layout featuring sidebar and workspace selectors | Created |
| `app/dashboard/page.tsx` | Simple route redirection component | Created |
| `app/page.tsx` | Redirection gateway pointing to `/dashboard/documents` or `/login` | Modified |
| `app/dashboard/documents/page.tsx` | Main Document Management UI containing the file table and chunk inspector | Created |

---

## Engineering Standards Applied (§5)

- **WebSocket Reconnection** — Socket triggers clean-up on unmount and uses token authorizations inside handshake parameters.
- **Fail-Safe UI Statuses** — Failed status tags display the backend-generated parse error string inside interactive tooltips.

---

## How to Test This Step

```bash
# Verify TypeScript compile is clean
npx tsc --noEmit

# Run local development server
npm run dev

# Open browser at http://localhost:3000/dashboard/documents
# 1. Drag and drop a valid PDF/TXT file
# 2. Verify status transitions: Pending -> Processing -> Ready
# 3. Click the Database icon to open the Chunk Inspector
# 4. Attempt to delete and verify Warning Prompt modal appears
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| WebSocket fails to connect | `NEXT_PUBLIC_WS_URL` is undefined or incorrect | Set `NEXT_PUBLIC_WS_URL=localhost:8000` in the frontend `.env` configuration file |
| `TypeError: Cannot read properties of undefined (reading 'map')` | Documents array is empty or endpoint failed | Verify database contains workspace documents and verify RLS workspace credentials match |

---

## What's Next

**Step 24** — Chat Interface: construct the conversational chat client with streaming SSE response rendering, inline clickable citation tags that link to document pages, and multi-turn query rewriter integration.
