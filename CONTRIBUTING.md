# CortexRAG Development Guide & Standards

Welcome to the CortexRAG codebase. To maintain code quality, security, and performance across both development and production environments, all contributors must adhere to the engineering standards detailed below.

---

## 1. Code Quality & Formatting

The codebase enforces strict linting and type checks:
- **Python**: Checked using `ruff` and typed using `mypy`.
- **TypeScript**: Strictly checked using `tsc`.

Before submitting changes, verify code locally:
```bash
# Backend lint & type check
cd backend
poetry run ruff check .
poetry run mypy .

# Frontend type check
cd frontend
npx.cmd tsc --noEmit
```

---

## 2. Exception Hierarchy & Handling

### Hierarchy
All domain-specific exceptions must inherit from `CortexException` (defined in [exceptions.py](file:///d:/Projects/PORTFOLIO/CORTEXRAG/backend/app/core/exceptions.py)). Never raise bare `HTTPException` inside services.

| Domain Exception | HTTP Status | Code | Usage |
|---|---|---|---|
| `AuthenticationException` | 401 | `AUTH_FAILED` | JWT validation, invalid logins |
| `ForbiddenException` | 403 | `FORBIDDEN` | Rate limits, unauthorized actions |
| `WorkspaceNotFoundException`| 404 | `WORKSPACE_NOT_FOUND` | Missing tenant workspace |
| `QuotaExceededException` | 403 | `QUOTA_EXCEEDED` | Exceeding document or query limits |
| `InvalidFileException` | 400 | `INVALID_FILE` | Blocked files, extensions, MIME mismatch |
| `FileParsingException` | 422 | `PARSE_FAILED` | Extraction errors on PDF/DOCX |

### Query Rules (No Crash on `.one()`)
When fetching rows from the database:
- **Avoid** `.one()` or `.scalar_one()` directly unless wrapped in a try/except block.
- **Use** `.first()` or `.scalar_one_or_none()` and execute a explicit check:
```python
user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
if user is None:
    raise UserNotFoundException()
```

---

## 3. Asynchronous Programming Rules

To prevent freezing the event loop or causing cascading failures, strictly apply these async rules:

| Operation | Don't Use | Use Instead |
|---|---|---|
| Sleeping | `time.sleep(1)` | `await asyncio.sleep(1)` |
| Random Tokens | `random.hex()` | `secrets.token_urlsafe(32)` |
| External API Calls | `httpx.post(...)` (unbounded) | `asyncio.wait_for(client.post(...), timeout=30.0)` |
| Concurrent Tasks | `asyncio.gather(*tasks)` | `asyncio.gather(*tasks, return_exceptions=True)` |
| Sync in Event Loop | Block the event loop with filesystem/MinIO calls | `await asyncio.get_event_loop().run_in_executor(None, sync_call)` |

---

## 4. Multi-Tenant Postgres Row-Level Security (RLS)

All tenant-isolated tables (documents, chunks, sessions, messages) have Postgres RLS policies active.
Every SQLAlchemy session used in routers or endpoints must establish the tenant context first. This is handled automatically by using the `get_rls_db` dependency:

```python
async def get_rls_db(workspace_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(f"SET LOCAL app.workspace_id = '{workspace_id}'")
        )
        yield session
```

If making raw database calls or scripting:
1. Always open a transaction.
2. Set the `app.workspace_id` setting local to that transaction.

---

## 5. Structured JSON Logging

Every log line in the application must use `structlog` and output JSON containing correlation IDs:

```python
from app.core.logging import get_logger
logger = get_logger()

# Log events with structured metadata
logger.info(
    "file_upload_blocked",
    user_id=str(user.id),
    filename=file.filename,
    detected_mime=mime
)
```
Do not output raw strings or string-formatted parameters (`f"Uploaded {filename}"`). Always bind context fields.
