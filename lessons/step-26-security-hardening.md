# Step 26 — Security Hardening

## What You're Building
System-wide security safeguards to protect the RAG engine against XSS, clickjacking, MIME sniffing, and database injection. This step introduces a secure response headers middleware (`SecurityHeadersMiddleware`), integrates the `bleach` library via custom Pydantic `SanitizedStr` types to automatically strip HTML tags from user-provided inputs (questions, names, session titles), adds a Caddy reverse-proxy block to restrict internal administrative routes, and creates a `/admin/security-check` endpoint to verify configuration readiness.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Secure HTTP Headers** | Response headers like CSP, HSTS, XFO, and MIME sniffing tags | Prevents browser-side exploits including framing attacks, cross-site scripting, and credential leaks |
| **XSS Input Sanitization** | Stripping active scripts and HTML markup tags from payload text | Shields downstream vector stores and administrators viewing session metrics from stored XSS injections |
| **Reverse Proxy Access Control** | Restricting routing groups within Caddy configuration | Shields sensitive endpoints like `/admin/*` from public internet exposure without backend overhead |
| **Active Security Auditing** | Internal route scanning databases and configuration settings | Provides automated confirmation that RLS holds are active and secure keys are deployed |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `backend/app/core/sanitizer.py` | Declares Pydantic `SanitizedStr` types running HTML-cleansing filters | Created |
| `backend/app/core/middleware.py` | Implements `SecurityHeadersMiddleware` applying headers | Modified |
| `backend/app/main.py` | Registers security middleware, startup assertions, and audit check route | Modified |
| `backend/app/schemas/query.py` | Sanitizes query questions and session titles | Modified |
| `backend/app/schemas/workspace.py` | Sanitizes workspace creation and renaming names | Modified |
| `backend/app/schemas/keys.py` | Sanitizes user API key labels | Modified |
| `backend/app/schemas/user.py` | Sanitizes user profile names | Modified |
| `caddy/Caddyfile` | Blocks `/admin/*` paths from being accessed by public requests | Modified |

---

## Engineering Standards Applied (§5)

- **Sanitize Prior to Database Storage** — Every text field received from API clients is processed through Pydantic validators running `bleach.clean(..., tags=[], strip=True)` to convert tags to safe plain text.
- **Fail-Safe Startup Verification** — Startup hooks assert key lengths and block default example secret tokens from starting the app.
- **Restrictive CSP Headers** — The API response headers declare `default-src 'none'; sandbox` to limit execution if responses are loaded directly in-browser.

---

## How to Test This Step

```bash
# Verify backend files compile successfully
python -m py_compile backend/app/main.py backend/app/core/middleware.py

# Verify frontend types compile cleanly
npx tsc --noEmit

# Query security check internally (bypass Caddy)
curl http://localhost:8000/admin/security-check

# Query security check externally (through Caddy)
curl http://localhost:80/admin/security-check
# Expected response: 403 Access Denied
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| API documentation routes return `404 Not Found` | fastapi `docs_url` is disabled in production settings | Ensure settings `APP_ENV` is set to `development` for local testing |
| Bleach strips valid characters | Bleach treated brackets (`<`, `>`) as raw HTML tags and wiped them | Cleanse inputs using a custom whitelist or allow them if encoded, or strip HTML structures explicitly |
