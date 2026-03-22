# Tallied — Multi-stage Docker build
# Stage 1: Build Vue frontend
# Stage 2: Python production server (FastAPI + static files)

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
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend code
COPY backend/ ./backend/
COPY config.yaml ./

# Copy built frontend
COPY --from=frontend-builder /build/dist ./static/

# Create data directory for SQLite
RUN mkdir -p /app/data

# Copy scripts and fixtures
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/

# Environment
ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Expose port
EXPOSE 8000

# Run with Gunicorn + Uvicorn workers
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--chdir", "/app/backend"]
