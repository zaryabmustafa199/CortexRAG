# Step 17 — Conversation History & Session Management

## What You're Building
A robust, secure chat session persistence engine. It enables users to create chat sessions (sessions mapping to workspaces), list chat threads, retrieve paginated message histories within a session, and delete entire conversation threads with cascade deletions extending down to individual messages, citations, and feedback records under Row-Level Security (RLS) workspace bounds.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Session Persistence** | Storing chat sessions, messages, and associated metadata in a relational database | Allows conversational context to persist across page reloads and multiple client logins |
| **Workspace Boundaries** | Isolating chat threads by workspace ID under database RLS constraints | Prevents cross-tenant leakages of chat histories, keeping sensitive document queries private |
| **Paginated History** | Retrieving message history using offset/limit constraints | Avoids overloading API responses and client memory when loading extremely long chat threads |
| **Cascade Message Deletion** | SQL cascades that delete child records (citations, feedback) automatically when a parent query session is deleted | Maintains referential integrity and prevents orphaned data from littering the database |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/schemas/query.py` | Pydantic response models and requests for query sessions and messages | Modified |
| `app/api/v1/query.py` | Mounts session endpoints (create, list, list messages, delete) in the query router | Modified |

---

## Engineering Standards Applied (§5)

- **RLS isolation** — Endpoints query database sessions activated with current tenant workspace ID settings, preventing cross-tenant access.
- **Fail-Safe Checks** — Router methods raise specific `SessionNotFoundException` if a query session does not exist or isn't accessible.
- **Cursor/Limit Pagination** — Page retrievals default to standard pagination limits to avoid unbounded memory usage.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# Create a session in a workspace
curl -X POST "http://localhost:8000/api/v1/query/sessions?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "My Workspace Chat"}'

# Expected output:
# {
#   "id": "session_uuid",
#   "workspace_id": "workspace_uuid",
#   "title": "My Workspace Chat",
#   "created_at": "...",
#   "messages": []
# }

# List sessions for the workspace
curl -X GET "http://localhost:8000/api/v1/query/sessions?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"

# Fetch session message history
curl -X GET "http://localhost:8000/api/v1/query/sessions/<session_uuid>/messages?workspace_id=<workspace_uuid>&limit=20" \
  -H "Authorization: Bearer <access_token>"

# Delete session
curl -X DELETE "http://localhost:8000/api/v1/query/sessions/<session_uuid>?workspace_id=<workspace_uuid>" \
  -H "Authorization: Bearer <access_token>"
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `SessionNotFoundException` | Session belongs to another workspace or user lacks permissions to access it | Ensure the correct `workspace_id` is supplied in the query params and the authenticated user is a member of that workspace |
| Delete operation fails with ForeignKey constraint error | Parent cascade delete triggers was not configured in DB | Check that database cascades are enabled on `messages` table and child relationships are configured with `cascade="all, delete-orphan"` |

---

## What's Next

**Step 18** — Document Management API (Full CRUD): extend document endpoints with paginated listings, individual retrieval, upload status tracking, chunk inspection, and bulk purges.
