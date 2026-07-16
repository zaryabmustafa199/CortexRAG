# Step 22 — Auth UI

## What You're Building
The user authentication interface. This step builds the user onboarding screens: a `/login` page for account signing, a `/register` page with complete complexity validators matching backend rules, an `AuthProvider` React Context to store JWT access tokens safely in memory (preventing XSS/storage theft), and response interceptors to automatically retry requests upon token expiration.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **In-Memory Token Storage** | Keeping access tokens in active React memory state rather than persistent localStorage | Blocks malicious extensions from reading access tokens directly, mitigating XSS security risks |
| **HttpOnly Cookies** | A secure cookie header that cannot be read by browser JavaScript engines | Standard mechanism for session rotation via refresh tokens, immune to client-side scripting access |
| **Form Validation via Zod** | Declarative schema validation verifying inputs prior to dispatching network requests | Saves backend CPU/rate limits and aligns client errors with API registration specifications |
| **Silent Session Rotation** | Using client-side timeouts to refresh credentials dynamically 1 minute before token expiry | Maintains a seamless user experience, avoiding abrupt chat interruptions or logouts |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `lib/api.ts` | Configures in-memory JWT tokens and Axios response interceptors to rotate expired keys | Modified |
| `context/AuthContext.tsx` | Implements authentication context provider and silent auto-refresh loops | Created |
| `app/layout.tsx` | Wraps children inside the layout with the `AuthProvider` component | Modified |
| `app/login/page.tsx` | Sign-in page with Zod schema verification and error outputs | Created |
| `app/register/page.tsx` | Registration page implementing backend password strength validation schemas | Created |

---

## Engineering Standards Applied (§5)

- **Secure JWT Handling** — Tokens are stored strictly in-memory. Persistent refreshes leverage backend HttpOnly cookies, ensuring premium web security standards.
- **Complexity Validations** — Registration inputs are validated client-side against length, uppercase, numbers, and special characters.

---

## How to Test This Step

```bash
# Verify TypeScript compile is clean
npx tsc --noEmit

# Run local development server
npm run dev

# Open browser at http://localhost:3000/login
# 1. Attempt to login with invalid emails -> verify Zod alerts
# 2. Attempt to register with weak passwords -> verify complexity warning
# 3. Complete registration -> verify redirections to /dashboard
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `TypeError: Cannot read properties of null (reading 'useContext')` | Component rendered server-side uses context hooks | Add `"use client";` at the top of the file to force next.js to compile it as a Client Component |
| CORS locks on token refresh | Backend hasn't allowed credentials for cookie passage | Verify `allow_credentials=True` is set in the backend CORS middleware |

---

## What's Next

**Step 23** — Document Management UI: build a dashboard file browser interface featuring drag-and-drop file upload zones, listing tables, delete confirmation prompts, and real-time ingestion status indicators driven by WebSocket sockets.
