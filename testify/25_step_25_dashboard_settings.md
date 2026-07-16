# Step 25 — Dashboard & Settings

## What You're Building
The usage statistics dashboard and security settings interface. This step builds the `/dashboard/settings` Next.js page that provides users with a comprehensive operations panel to track monthly RAG search quota volumes against subscription limits, toggle subscription tiers (Mock Free ⇄ Pro switches), rename workspaces, manage collaborative members list, execute secure key generation (with single-exposure modal display), update credentials, and perform GDPR-compliant soft-deletion cascades.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **API Key Generation & Hash** | Creating cryptographically random tokens and storing SHA-256 hashes | Allows secure automated CLI / programmatic integrations without exposing raw database secrets |
| **Progressive Quota Auditing** | Progress tracking computed on actual usage vs profile tier limits | Motivates subscription upgrades and protects backend databases from query flood attacks |
| **Workspace Collaboration Invites** | Adding cross-tenant user linkages via user UUID references | Enables team-level document indexing sharing while maintaining workspace RLS boundaries |
| **GDPR Soft Deletion** | deactivating profiles and enqueuing background tasks to clean data | Complies with legal privacy mandates and ensures no storage objects or vector records leak |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `backend/app/api/v1/users.py` | Added workspace rename PUT route and managed membership modifications | Modified |
| `frontend/app/dashboard/settings/page.tsx` | Usage trackers, workspace members/renaming, API keys CRUD, profile forms | Created |

---

## Engineering Standards Applied (§5)

- **Single-Disclosure API Keys** — The raw API key token is displayed inside a modal window exactly once upon creation, preventing subsequent server retrievals.
- **Complexity Validations** — Password changes trigger Pydantic password validator regex patterns, enforcing uppercase, numeric, and special character requirements.
- **Safety Gate Input Lock** — The account delete action is locked behind typing the uppercase word `"DELETE"`, preventing catastrophic misclicks.

---

## How to Test This Step

```bash
# Verify backend routing and schemas compile cleanly
python -m py_compile backend/app/api/v1/users.py

# Verify frontend Next.js compilation is clean
npx tsc --noEmit

# Run local development servers
npm run dev # inside frontend
uvicorn app.main:app --reload # inside backend

# Open browser at http://localhost:3000/dashboard/settings
# 1. Verify usage bar displays correct numbers based on database values
# 2. Toggle "Upgrade to Pro" and verify limits instantly increase
# 3. Enter a key name and generate key - copy the one-time raw token
# 4. Invite a member by typing their User UUID
# 5. Type "DELETE" in the safety gate input card to verify button activates
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| Workspace renaming fails with `403 Forbidden` | Current user is not the workspace owner or is registered as a VIEWER/EDITOR member role | Verify active user role is ADMIN inside `workspace_members` table |
| API Keys list is empty or returns `401 Unauthorized` | Memory token expired and refresh interceptor did not trigger | Refresh browser to trigger silent cookie-refresh loop |

---

## What's Next

**Step 26** — Security Hardening: implement secure HTTP headers (CSPs, XFO, HSTS), sanitize input fields using bleach, and configure startup validation gates blocking default environment secrets.
