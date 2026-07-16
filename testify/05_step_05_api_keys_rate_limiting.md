# Step 05 — API Key Management & Rate Limiting

## What You're Building
Programmatic access via API keys: users can generate keys, list their generated keys, and revoke (deactivate) keys. Additionally, rate limiting has been integrated into the authentication pipeline via a Redis fixed-window counter, supporting both per-user (JWT sessions) and per-key (API keys) throttling.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **API Keys** | Cryptographically secure tokens for programmatic integrations | Allows users to authenticate without interactive browser logins (e.g. CLI or automated webhooks) |
| **One-Way Key Hashing** | Storing only the SHA-256 hash of the key in the database | If the database is compromised, keys cannot be stolen or decrypted (similar to password hashing) |
| **Redis Rate Limiting** | Fast, temporary counters that track request volume within a window | Protects application servers and database connections from resource exhaustion / DDoS attacks |
| **Fail-Open Rate Limiter** | Throttling mechanism that permits requests if the rate-limit storage (Redis) is unreachable | Prevents downstream database outages from blocking user traffic |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/schemas/keys.py` | Pydantic schemas for API key creation, listing, and response | Modified (completed) |
| `app/services/key_service.py` | KeyService: key generation, hashing, listing, and validation business logic | Created |
| `app/core/rate_limiter.py` | Redis fixed-window rate limiter module | Created |
| `app/api/v1/keys.py` | API key endpoint router: POST /keys, GET /keys, DELETE /keys/{key_id} | Created |
| `app/core/deps.py` | Unified `get_current_user` dependency supporting JWT & API key auth | Modified |
| `app/api/v1/router.py` | Register keys router under the `/api/v1` routes prefix | Modified |

---

## Engineering Standards Applied (§5)

- **`secrets.token_urlsafe(32)`** — Cryptographically secure key generation.
- **SHA-256 hex digest (64 chars)** — Raw keys are hashed and never persisted in database.
- **Fail-Open Limiting** — Rate limiter catches all Redis errors, logging them and failing open.
- **Unified auth** — JWT and API key schemes resolve to the same `User` object, preserving workspace RLS policies downstream.

---

## How to Test This Step

```bash
# Start backend services
docker compose up -d

# 1. Create a new API key
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "production-service"}' | jq .

# Expected:
# {
#   "id": "uuid",
#   "name": "production-service",
#   "raw_key": "cr_XXXXXX...",
#   "created_at": "timestamp"
# }

# 2. List all active keys (verify raw key is NOT shown)
curl -X GET http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer <access_token>" | jq .

# 3. Authenticate using API Key
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: ApiKey cr_XXXXXX..." | jq .

# Alternatively, using header format:
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "X-API-Key: cr_XXXXXX..." | jq .

# 4. Trigger rate limiting (make >60 requests within a minute)
for i in {1..61}; do curl -s -o /dev/null -w "%{http_code}\n" -X GET http://localhost:8000/api/v1/users/me -H "X-API-Key: cr_XXXXXX..."; done
# 61st response should return 429
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Invalid key prefix or key hashed mismatch | Ensure you copy the key immediately on creation (it starts with `cr_`) |
| `429 Too Many Requests` | Rate limit threshold exceeded | Wait 60 seconds for the window bucket to expire |
| Rate limiting not occurring | Redis connection is down | Check `docker compose logs backend` to see if rate_limiter fails open with warning logs |

---

## What's Next

**Step 6** — Secure File Upload & MinIO Storage: build the document upload router, validate magic bytes, secure against path traversal, and persist in private object buckets.
