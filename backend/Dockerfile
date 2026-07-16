# =============================================================================
# CortexRAG Backend — Dockerfile
# Multi-stage: base → development | production
# Uses pip + requirements.txt for fast, cache-friendly builds (no poetry/CUDA bloat)
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: base — shared Python setup
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

WORKDIR /app

# System deps: libmagic (python-magic), libgomp (sentence-transformers compat), curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching — only reinstalls on requirements.txt change
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: development — includes hot reload support
# ---------------------------------------------------------------------------
FROM base AS development

# Copy app source (volume-mounted in dev, so this is mostly for non-mounted starts)
COPY . .

EXPOSE 8000

# Uvicorn with --reload for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Stage 3: production — minimal image, non-root user
# ---------------------------------------------------------------------------
FROM base AS production

COPY . .

# Create non-root user for security
RUN groupadd --gid 1001 cortexrag \
    && useradd --uid 1001 --gid 1001 --no-create-home cortexrag

USER cortexrag

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
