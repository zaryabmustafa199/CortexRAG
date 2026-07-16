-- scripts/init_db.sql
-- Runs once when the PostgreSQL container first initialises.
-- Creates the pgvector extension required for vector storage.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Allow application to set RLS context variables
-- (Alembic migrations will create the actual tables and RLS policies)
ALTER DATABASE cortexrag SET app.workspace_id = '';
