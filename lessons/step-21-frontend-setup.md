# Step 21 — Next.js Setup & Design System

## What You're Building
The frontend foundation. This initializes a Next.js 14 application workspace using TypeScript, ESLint, and Tailwind CSS. It configures the platform's global dark-mode-first styling tokens (dark background `#0A0A0F`, surface `#1A1A2E`, accent violet `#7C3AED`), integrates Inter (sans-serif body font) and JetBrains Mono (monospaced code font) via `next/font/google`, creates a reusable core UI component library (`Button`, `Card`, `Badge`, `Spinner`, `Avatar`, `Tooltip`, `Modal`), and configures a global API HTTP client using `axios` with automatic token injection and unique request-level correlation IDs.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **App Router & next/font** | Next.js's native file-system-based router combined with optimized Google Font serving | Minimizes Cumulative Layout Shift (CLS) by loading fonts server-side and pre-compiling CSS variables |
| **Tailwind CSS v4 @theme** | Dynamic styling specification declared directly in CSS rather than JS files | Accelerates style rendering and keeps the theme tokens centralized in a single stylesheet (`globals.css`) |
| **Component Reusability** | Abstracting styles into modular components like `Button` and `Card` using class merging | Standardizes UI layouts, ensures visual coherence, and reduces codebase styling duplication |
| **Axios Interceptors** | Middleware functions executed dynamically before HTTP requests are sent | Centralizes request headers propagation, injecting JWT authorization and tracing correlation IDs globally |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/globals.css` | Implements the core theme CSS tokens and body style rules | Modified |
| `app/layout.tsx` | Embeds Google Fonts and configures metadata for the application | Modified |
| `lib/utils.ts` | Dynamic Tailwind class merging utility | Created |
| `lib/api.ts` | Axios instance preconfigured with interceptors for token injection and correlation ID generation | Created |
| `components/ui/Button.tsx` | Reusable button component supporting variant styles, loading state, and disabled options | Created |
| `components/ui/Card.tsx` | Reusable container component for cards and header/content/footer layouts | Created |
| `components/ui/Badge.tsx` | Reusable status indicators for document processing and confidence labels | Created |
| `components/ui/Spinner.tsx` | Reusable loading animation indicator | Created |
| `components/ui/Avatar.tsx` | Reusable user avatar with initials fallback | Created |
| `components/ui/Tooltip.tsx` | Reusable tooltip helper displaying notes on hover | Created |
| `components/ui/Modal.tsx` | Reusable popup modal with escape key listeners and focus retention | Created |

---

## Engineering Standards Applied (§5)

- **Strict Type Safety** — All components are built with TypeScript interfaces and strict return typings, passing clean `tsc` compiles.
- **Request Tracing** — The global axios client generates a fresh request correlation ID for every request, matching backend logging trace requirements.

---

## How to Test This Step

```bash
# Verify TypeScript compile is clean
npx tsc --noEmit

# Run local development server
npm run dev

# Open browser at http://localhost:3000 to verify Next.js boots successfully
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `@theme directives not resolved` | Tailwind CSS compiler mismatch | Ensure `@tailwindcss/postcss` and post-css configurations are properly matched in project configs |
| `axios default headers are cached` | Interceptors are evaluated statically rather than dynamically | Ensure token fetching happens inside the interceptor callback function (`(config) => { ... }`) to retrieve fresh tokens on each request |

---

## What's Next

**Step 22** — Auth UI: build user interface screens for registration, login, profile tier swapping, and credentials validation using the reusable UI component library.
