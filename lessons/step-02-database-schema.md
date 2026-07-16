# Step 02 — Database Schema & Migrations

## What You're Building
All 14 production database tables defined as SQLAlchemy async ORM models, plus a single Alembic migration that creates every table, enum, index, and Row-Level Security policy in one atomic operation. After this step, the database schema is complete and tenant isolation is enforced at the database level.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Mapped Column (SQLAlchemy 2.x)** | Type-safe ORM column definition using `Mapped[type]` annotations | Eliminates runtime surprises — wrong types are caught at startup |
| **UUID Primary Keys** | `uuid_generate_v4()` generates 128-bit IDs server-side | No sequential IDs that attackers can enumerate; globally unique across shards |
| **Cascade Delete** | `ondelete="CASCADE"` — deleting a parent row automatically deletes all child rows | Prevents orphaned chunks/embeddings when a document is deleted |
| **Denormalised workspace_id** | `parent_chunks`, `leaf_chunks`, `chunk_embeddings`, `messages` all carry `workspace_id` directly | Eliminates multi-table JOINs to activate RLS — every query can set `app.workspace_id` and Postgres enforces it directly |
| **HNSW Index** | Hierarchical Navigable Small World — a graph-based Approximate Nearest Neighbour index | Sub-millisecond cosine similarity search over millions of 768-dim vectors; `m=16, ef_construction=64` balances speed and recall |
| **RLS Policy** | `CREATE POLICY ws_isolation ... USING (workspace_id::text = current_setting('app.workspace_id'))` | Every SELECT/INSERT/UPDATE/DELETE is filtered by Postgres — even if application code forgets to filter |
| **FORCE ROW LEVEL SECURITY** | Makes RLS apply even to the table owner | Prevents privilege escalation exploits where a connection temporarily gains owner-level access |
| **JSONB** | PostgreSQL's binary JSON column type | Allows indexable, queryable arrays (e.g. `years_detected`) without a separate join table |

---

## Files Created

| File | Role |
|---|---|
| `app/models/user.py` | User, Profile, APIKey, UsageRecord ORM models |
| `app/models/workspace.py` | Workspace, WorkspaceMember with `MemberRole` enum |
| `app/models/document.py` | Document, UploadJob, ParentChunk, LeafChunk, ChunkEmbedding |
| `app/models/query.py` | QuerySession, Message, Citation, FeedbackRecord |
| `app/db/base.py` | Updated — imports all models for Alembic discovery |
| `alembic/versions/0001_initial_schema.py` | Migration: all tables + HNSW index + RLS policies |

---

## Engineering Standards Applied (§5)

- **`.first()` + None check** — enforced in all service queries built on top of these models
- **RLS** — `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` on all 6 tenant tables
- **Pool pre-ping** — `pool_pre_ping=True` in session.py detects stale connections before every query
- **UUID PKs** — `uuid_generate_v4()` server-side, not Python-generated (avoids clock skew bugs)

---

## How to Run This Step

### Run the migration (from inside the backend container)
```bash
# Start just the database
docker compose up postgres -d

# Wait for postgres to be healthy, then run migrations
docker compose run --rm backend alembic upgrade head
```

### Verify tables and RLS
```bash
docker compose exec postgres psql -U cortexrag -d cortexrag -c "\dt"
# Should list all 14 tables

docker compose exec postgres psql -U cortexrag -d cortexrag \
  -c "SELECT tablename, rowsecurity FROM pg_tables WHERE rowsecurity = true;"
# Should list: documents, parent_chunks, leaf_chunks, chunk_embeddings, query_sessions, messages

docker compose exec postgres psql -U cortexrag -d cortexrag \
  -c "\d+ chunk_embeddings"
# Should show: HNSW index on the vector column
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `could not open extension control file: vector.control` | pgvector extension not installed | Ensure using `pgvector/pgvector:pg16` image (not plain postgres) |
| `type "vector" does not exist` | Migration ran before extension was created | Check that `init_db.sql` ran on container init; recreate with `docker compose down -v && up` |
| `duplicate_object` on enum creation | Migration ran twice | Migration uses `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL END $$` — safe to re-run |
| `ERROR: relation already exists` | Running upgrade on non-empty DB | Check `alembic_version` table; run `alembic current` to see applied revision |
| `ImportError: cannot import model` | Model file missing `__init__` | Verify `app/models/__init__.py` exists |

---

## What's Next

**Step 3** — Authentication system: register/login endpoints, JWT token generation with `python-jose`, bcrypt password hashing, refresh token rotation, and brute-force protection via Redis counters.
