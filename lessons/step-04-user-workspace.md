# Step 04 — User Profile & Workspace Management

## What You're Building
APIs to manage user profile (demo-only tier toggling between "free" and "pro"), update password (verifying old password first), soft-delete account (deactivating the user for asynchronous data purging), and full workspace CRUD, including member invite and role management.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Tier Limits (Free/Pro)** | Restricting document count, storage size, and query quotas based on profile tier | Direct business logic foundation for SaaS platform monetization (mocked here, ready for Stripe integration) |
| **Workspace Isolation** | Separation of projects and data under unique workspace records | Multi-tenancy support allowing collaborative environments within the platform |
| **Workspace Role-Based Access Control (RBAC)** | Restricting member actions (viewer, editor, admin) within a workspace | Security gate preventing unauthorized additions/deletions of workspace assets |
| **Soft Account Deletion** | Marks `User.is_active = False` rather than hard DB deletion | Allows graceful deactivation immediately, while queuing async workers to purge files/databases safely |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/models/user.py` | Added relationships to Profile and Workspace models | Existing |
| `app/models/workspace.py` | Workspace and WorkspaceMember database models | Existing |
| `app/schemas/user.py` | User and profile request/response schemas (with confirmation validation) | Existing |
| `app/schemas/workspace.py` | Workspace create, update, and invite validation schemas | Existing |
| `app/services/user_service.py` | `UserService` and `WorkspaceService` business logic | Existing |
| `app/api/v1/users.py` | Router mounting `/users` and `/workspaces` endpoints | Existing |
| `app/api/v1/router.py` | Registering `/users` and `/workspaces` into the main API router | Existing |

---

## Engineering Standards Applied (§5)

- **`.scalar_one_or_none()` + None check** — used everywhere in `UserService` and `WorkspaceService` to prevent `NoResultFound` crashes.
- **`asyncio`-safe** — all router endpoints and service calls are async.
- **Strict Input Validation** — Pydantic `field_validator` verifies password complexity and account delete confirmation.
- **No raw exception leakage** — all database/business failures raise typed `CortexException` subclasses.

---

## How to Test This Step

```bash
# Start the backend services
docker compose up -d

# 1. Fetch current profile
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>" | jq .

# 2. Toggle tier to pro
curl -X PUT http://localhost:8000/api/v1/users/me/tier \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"tier": "pro"}' | jq .

# 3. Create a workspace
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Developer Workspace"}' | jq .

# 4. Delete account (requires confirmation string)
curl -X DELETE http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"confirmation": "DELETE"}' | jq .
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `403 FORBIDDEN` on creating workspace | Workspace limit reached for free plan | Upgrade to pro plan first using `/users/me/tier` |
| `422 Unprocessable Entity` on delete | Confirmation string is not exactly `DELETE` | Pass `{"confirmation": "DELETE"}` in JSON request body |
| `404 WORKSPACE_NOT_FOUND` | Workspace ID does not exist | Verify UUID parameter used in the path |

---

## What's Next

**Step 5** — API Key Management & Rate Limiting: programmatically generate secure tokens for API usage and implement Redis-backed rate limiting.
