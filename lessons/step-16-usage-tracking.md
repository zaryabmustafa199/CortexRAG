# Step 16 — Usage Tracking & Quota Enforcement

## What You're Building
The user usage tracking and subscription quota enforcement system. This tracks monthly query and token count metrics for each user, enforces quota checks before querying the RAG pipeline (raising `QuotaExceededException` if user-tier limits are met), calculates token costs per query based on a local LLM pricing scheme, and exposes a `/usage/me` endpoint to present usage data and subscription limits to the user.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Usage Auditing** | Accumulating prompt and completion tokens for both input queries and generated replies | Necessary for calculating system load, operational metrics, and computing overall costs |
| **Quota Enforcement** | Query limits dynamically assigned by tier ("free" vs. "pro") and evaluated prior to executing RAG endpoints | Prevents system abuse, secures server capacity, and drives monetization funnels |
| **Numeric Precision** | Preserving precise cost values using SQLAlchemy Numeric types and Python Decimal | Avoids floating-point rounding errors when tracking small fractional API costs |
| **Upsert Logic** | Dynamically inserting or updating database records based on month boundaries | Keeps billing cycles clean and tracks user habits month over month |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/usage_service.py` | Business logic checking quotas and updating monthly usage records | Created |
| `app/schemas/usage.py` | Pydantic response schema for usage summary data | Created |
| `app/api/v1/usage.py` | `/usage/me` API router returning user usage metrics | Created |
| `app/api/v1/query.py` | Plugs pre-query quota check and post-stream usage recorder | Modified |
| `app/api/v1/router.py` | Registered `/usage` router under general API prefix | Modified |

---

## Engineering Standards Applied (§5)

- **Numeric Database Mapping** — Fractional costs are mapped using PostgreSQL numeric columns, handled via standard Decimal values.
- **Fail-Fast Quota Check** — Limits are evaluated at the beginning of API requests, preventing expensive embedding and hybrid-retrieval steps from running if quota is exhausted.
- **Transactional Consistency** — Usage writes happen inside the completed streaming block alongside message persistence under same workspace RLS settings.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# Call usage endpoint (initially will return 0 usage)
curl -X GET http://localhost:8000/api/v1/usage/me \
  -H "Authorization: Bearer <access_token>"

# Expected output:
# {
#   "month": "2026-06-01",
#   "query_count": 0,
#   "query_limit": 100,
#   "token_count": 0,
#   "cost_usd": 0.0,
#   "tier": "free"
# }

# Execute a query ask request to record token consumption
curl -X POST http://localhost:8000/api/v1/query/ask \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id": "<workspace_uuid>", "question": "Explain the project goal."}'

# Fetch usage again to verify query_count incremented and token_count recorded
curl -X GET http://localhost:8000/api/v1/usage/me \
  -H "Authorization: Bearer <access_token>"
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `QuotaExceededException` | User has reached the maximum permitted queries for the month | Toggle tier to `pro` via `/users/me/tier` or increase limits in profile table |
| Cost remains `0.000000` | Cost multiplier rounds down due to extremely short prompt/completion tokens | Normal for small queries; cost accumulates progressively as total token count rises |

---

## What's Next

**Step 17** — Conversation History & Session Management: extend conversation sessions with active thread context persistence, allowing users to retrieve, resume, delete, and pagination-load chat histories.
