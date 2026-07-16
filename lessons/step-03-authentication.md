# Step 03 — Authentication System

## What You're Building
A complete, production-grade authentication system: user registration with workspace auto-creation, login with brute-force protection, JWT access token (15-min) with refresh token rotation (7-day), and secure logout. All tokens generated with `secrets` module. Passwords hashed with PBKDF2-SHA256.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **PBKDF2-SHA256** | A one-way hash recommended by OWASP / NIST with zero native build dependencies | Runs purely on standard libraries, avoiding C-extension compiler issues while remaining secure against brute force |
| **JWT (HS256)** | Compact, self-contained token signed with HMAC-SHA256 | Stateless auth — API validates token without a DB call on every request |
| **Refresh Token Rotation** | Each refresh token can be used exactly once; usage generates a new pair | Stolen refresh tokens are detected: if attacker uses it, victim's next refresh fails → session terminated |
| **HttpOnly Cookie** | `Set-Cookie: httponly; samesite=strict` — JS cannot read the cookie | Prevents XSS from stealing the refresh token even if script injection occurs |
| **Redis Blacklist** | Revoked access tokens stored with remaining TTL as Redis keys | Stateless JWTs can now be invalidated immediately on logout |
| **Brute Force Lock** | Redis counter per email: 5 failures → 900s lock | Stops automated credential stuffing while keeping latency minimal |
| **Token Enumeration Prevention** | Fail counter incremented even for non-existent emails | Prevents `"email not found"` vs `"wrong password"` response differencing |

---

## Files Created

| File | Role |
|---|---|
| `app/core/security.py` | `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `hash_api_key` |
| `app/core/redis_client.py` | Singleton Redis client with retry + timeout config |
| `app/core/deps.py` | FastAPI dependencies: `get_current_user`, `require_workspace`, `require_pro` |
| `app/schemas/auth.py` | `RegisterRequest` (with complexity validator), `LoginRequest`, `AuthResponse`, etc. |
| `app/services/auth_service.py` | `AuthService`: register, login, refresh, logout business logic |
| `app/api/v1/auth.py` | Auth router: POST /register, /login, /refresh, /logout |
| `app/api/v1/router.py` | v1 aggregator router — auth router mounted |
| `app/main.py` | Updated — v1 router now mounted at `/api/v1` |

---

## Engineering Standards Applied (§5)

- **`secrets.token_urlsafe(64)`** — refresh token generation (never `random`)
- **`asyncio`-safe** — all service methods are `async def`
- **`.scalar_one_or_none()` + None check** — used in `get_current_user` and `AuthService`
- **No raw exception leakage** — all failures raise typed `CortexException` subclasses
- **Redis with retry** — `redis_client.py` uses `ExponentialBackoff`, socket timeouts

---

## How to Test This Step

```bash
# Start all services
docker compose up -d

# Register a new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test@1234"}' \
  | jq .

# Expected: {"user": {...}, "access_token": "eyJ...", "expires_in": 900}

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test@1234"}' | jq .

# Test brute force — 5 wrong passwords
for i in {1..6}; do curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "WRONG"}' | jq .error.code; done
# 6th attempt should return: "ACCOUNT_LOCKED"

# Logout
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer <access_token>"
# Then verify the old token is rejected:
curl http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer <same_token>"
# Expected: 401 TOKEN_REVOKED
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `422 Unprocessable Entity` on register | Password fails complexity check | Password needs uppercase + digit + special char |
| `503` on login | Redis not reachable | Check `docker compose ps redis` — verify healthy |
| `401 Token validation failed` | JWT_SECRET changed between requests | Tokens are invalidated when JWT_SECRET changes — log in again |
| `409 CONFLICT` on register | Email already used | Use a different email |

---

## What's Next

**Step 4** — User profile API: update profile, change password, tier toggle (free ↔ pro), account deletion, workspace CRUD with member invitations.
