# Step 28 — Test Suite

## What You're Building
A comprehensive and production-grade unit and integration test suite targeting core system capabilities including authentication, security (HTML sanitization, double-extension rejection, RLS DB activation), retrieval math (RRF merging, citation extraction, caching JSON serialization), and RAG quality evaluation (LLM-as-judge prompt formatting and scoring).

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **SQLAlchemy TextClause String Comparison** | Comparing the string representation of compiled SQL text expressions | Avoids assertion failures in mocks due to distinct object instances of `text(...)` |
| **RLS Verification** | Asserting that the Postgres connection sets the local workspace context | Ensures that database-level multi-tenant Row-Level Security is active before any query executes |
| **RAG Evaluation (LLM-as-judge)** | Parsing and scoring LLM answers against context grounding and retrieval precision | Provides an automated method to evaluate system performance without manual inspection |
| **Mocking Event Loop Blockers** | Mocking clients like Redis and database sessions | Keeps tests isolated, lightning fast (sub-second), and runnable without external infrastructure dependencies |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| [conftest.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/tests/conftest.py) | Test configuration, environment setup, and global fixtures (Redis mock, client dependency overrides) | Created |
| [test_auth.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/tests/test_auth.py) | Tests for password complexity rules, PBKDF2 hashing, JWT generation, and token rotation | Created |
| [test_security.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/tests/test_security.py) | Tests for HTML stripping, malicious extensions, and database Row-Level Security isolation | Modified |
| [test_rag.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/tests/test_rag.py) | Tests for reciprocal rank fusion, source citations extraction, and JSON serialization | Created |
| [test_rag_eval.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/tests/test_rag_eval.py) | Tests for LLM-as-judge prompt templating and quality score parsing | Created |

---

## Engineering Standards Applied (§5)

- **Circular Imports Avoidance** — Preloaded `app.db.base.Base` inside `conftest.py` before loading `app.main` to prevent testing execution cycles.
- **Fail-Safe Mocking** — Used `AsyncMock` and `MagicMock` to isolate network-bound endpoints (Redis/Postgres) so tests remain fully local and fast.
- **Strict Validation Rules** — Password complexity validations are asserted against standard ValidationError types to ensure weak user inputs fail fast.

---

## How to Test This Step

```bash
# Verify and run the entire test suite from the backend directory
python -m pytest

# Run only security tests
python -m pytest tests/test_security.py

# Run only authentication tests
python -m pytest tests/test_auth.py
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `AssertionError: Expected 'SET LOCAL app.workspace_id = '...'` | SQLAlchemy `text()` creates distinct memory objects which fail standard mock equality | Compare string representation: `assert str(call_arg) == expected_string_expression` |
| `ImportError: circular import dependency` | Importing models after App factory without initializing Base first | Import Base first in `conftest.py` to pre-register declarative schemas |
| Redis Connection Error during testing | Real Redis client called instead of mock | Wrap imports/mocks inside global fixtures using `monkeypatch` to substitute clients before server starts |
