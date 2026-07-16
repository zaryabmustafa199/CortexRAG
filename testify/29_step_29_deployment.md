# Step 29 — Docker & Deployment Pipeline

## What You're Building
A production-ready Docker configuration and a complete CI/CD automation pipeline. This step implements multi-stage Dockerfiles for both the backend (FastAPI/Celery) and the frontend (Next.js), a production Compose override (`docker-compose.prod.yml`) that strips out local volume mounts and closes internal ports, and a GitHub Actions workflow (`ci.yml`) automating linting, type-checking, testing, and container build checks.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Multi-Stage Builds** | Segregating build-time tools from runtime environments in Docker | Minimizes the final image size and reduces the surface area for security vulnerabilities |
| **Compose Overrides** | Using layered compose configurations (e.g. base + prod) | Separates local development requirements (like code hot-reloading) from strict production environments |
| **Port Isolation** | Blocking direct external access to internal backing services | Ensures databases, caches, and AI engines are only reachable within the internal Docker bridge network |
| **CI Type-Checking & Verification** | Validating TypeScript and Python types before image compilation | Prevents runtime exceptions from reaching production |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| [Dockerfile](file:///d:/Projects/PORTFOLIO/CORTEXRAG/frontend/Dockerfile) | Multi-stage Dockerfile for Next.js (base → builder → runner) | Created |
| [.dockerignore](file:///d:/Projects/PORTFOLIO/CORTEXRAG/frontend/.dockerignore) | Excludes node_modules and Next cache folders from the build context | Created |
| [.dockerignore](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/.dockerignore) | Excludes Python caching, virtual environments, and test files | Created |
| [docker-compose.yml](file:///d:/Projects/PORTFOLIO/CORTEXRAG/docker-compose.yml) | Updated base configuration to include the frontend service and Caddy routing dependencies | Modified |
| [docker-compose.prod.yml](file:///d:/Projects/PORTFOLIO/CORTEXRAG/docker-compose.prod.yml) | Production override that closes ports, switches targets to prod stages, and clears mounts | Created |
| [Caddyfile](file:///d:/Projects/PORTFOLIO/CORTEXRAG/caddy/Caddyfile) | Routing rules separating frontend, API backend, and blocking administrative paths | Modified |
| [ci.yml](file:///d:/Projects/PORTFOLIO/CORTEXRAG/.github/workflows/ci.yml) | GitHub Actions automation runner for lints, types, testing, and builds | Created |

---

## Engineering Standards Applied (§5)

- **Non-Root Execution** — Configured `cortexrag` and `nextjs` non-root system users inside Dockerfiles to mitigate container breakout risks.
- **Unified Domain Routing** — Configured Caddy to route traffic to the Next.js frontend and FastAPI backend behind a single domain, eliminating complex CORS setups.
- **Port Minimization** — Cleared all host ports (except 80/443 for Caddy) in `docker-compose.prod.yml` using modern Docker Compose `!reset` list overrides.

---

## How to Test This Step

```bash
# Verify base dev environment runs successfully
docker compose up --build -d

# Verify Next.js frontend compiles cleanly
cd frontend
npx.cmd tsc --noEmit

# Test production overrides compilation
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| Host port conflicts on production spin-up | Base compose exposes host ports (5432, 6379, 9000, etc.) | Apply `docker-compose.prod.yml` as an override using `-f` flags. Confirm that `!reset []` correctly clears base lists |
| Next.js hydration or CORS errors | Frontend making calls to `localhost:8000` from public clients | Set the API URL to relative `/api/v1` since Caddy hosts both services on the same port and domain |
| Node.js Out-Of-Memory during build stage | Next.js build uses extensive memory | Enforce minimal base images (like `node:20-alpine`) and run Next build in an isolated `builder` stage |
