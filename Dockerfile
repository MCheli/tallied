# Tallied — Multi-stage Docker build
# Stage 1: Build Vue frontend (Node.js)
# Stage 2: Production Python server (FastAPI + Gunicorn + static files)
#
# Build:  docker build -t tallied .
# Run:    docker run -p 8000:8000 --env-file backend/.env tallied
#
# ── Required Environment Variables ──────────────────────────────────────────
#   DATABASE_URL              PostgreSQL connection string
#   FINANCE_SECRET_KEY        JWT signing key (generate with: python3 -c "import secrets; print(secrets.token_urlsafe(64))")
#   FINANCE_GOOGLE_CLIENT_ID  Google OAuth client ID
#   FINANCE_GOOGLE_CLIENT_SECRET  Google OAuth client secret
#
# ── Optional Environment Variables ──────────────────────────────────────────
#   FINANCE_ANTHROPIC_API_KEY  Anthropic API key (for AI document parsing)
#   FINANCE_PLAID_CLIENT_ID    Plaid client ID (for bank sync)
#   FINANCE_PLAID_SECRET       Plaid secret (for bank sync)
#   FINANCE_BASE_URL           Public URL (e.g. https://money.markcheli.com)
#   FINANCE_DEV_MODE           Set to "true" for local dev only — NEVER in prod

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Build frontend
# ═══════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --silent --legacy-peer-deps
COPY frontend/ ./
RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2: Production Python server
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.13-slim

# Labels
LABEL org.opencontainers.image.title="Tallied"
LABEL org.opencontainers.image.description="Personal Finance Dashboard"
LABEL org.opencontainers.image.source="https://github.com/MCheli/tallied"

WORKDIR /app

# Install system deps (curl for healthcheck, libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend code
COPY backend/ ./backend/
COPY config.yaml ./

# Copy built frontend
COPY --from=frontend-builder /build/dist ./static/

# Copy scripts and fixtures (for seeding)
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/

# Copy alembic config for migrations
COPY backend/alembic.ini ./backend/alembic.ini

# Create non-root user
RUN groupadd --gid 1000 tallied && \
    useradd --uid 1000 --gid tallied --shell /bin/bash --create-home tallied && \
    mkdir -p /app/data && \
    chown -R tallied:tallied /app

USER tallied

# Environment
ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Run with Gunicorn + Uvicorn workers
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--chdir", "/app/backend"]
