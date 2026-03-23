.PHONY: dev dev-backend dev-frontend test test-e2e test-all seed-test lint build clean db-start db-migrate pre-commit typecheck setup-db-roles

# Development
dev: dev-backend dev-frontend

dev-backend:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Database (PostgreSQL)
db-start:
	docker compose up -d postgres
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec postgres pg_isready -U tallied 2>/dev/null; do sleep 1; done
	@echo "Postgres is ready on localhost:5432"

db-migrate:
	cd backend && source .venv/bin/activate && PYTHONPATH=. python ../scripts/migrate_sqlite_to_postgres.py

setup-db-roles:
	cd backend && source .venv/bin/activate && PYTHONPATH=. python ../scripts/setup_postgres_roles.py

seed-test:
	cd backend && source .venv/bin/activate && PYTHONPATH=. python ../scripts/seed_test_data.py --reset

generate-docs:
	cd backend && source .venv/bin/activate && python ../scripts/generate_test_documents.py

# Testing
test:
	cd backend && source .venv/bin/activate && pytest tests/ -v

test-e2e:
	cd backend && source .venv/bin/activate && pytest tests/test_e2e/ -v -m e2e

test-all: test typecheck
	cd frontend && npm run test 2>/dev/null || echo "Frontend unit tests not configured yet"

# Linting & type checking
lint:
	cd backend && source .venv/bin/activate && ruff check app/ 2>/dev/null || echo "Install ruff: pip install ruff"

typecheck:
	cd frontend && npx vue-tsc --noEmit

# Run before committing — catches what CI would catch
pre-commit: test typecheck

# Build
build:
	docker build -t tallied .

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
	find . -type f -name "*.pyc" -delete 2>/dev/null
	rm -rf frontend/dist backend/build

# Install dependencies
install:
	cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

# Help
help:
	@echo "Tallied — Personal Finance Dashboard"
	@echo ""
	@echo "  make dev          Start backend + frontend dev servers"
	@echo "  make db-start     Start PostgreSQL container"
	@echo "  make db-migrate   Migrate data from legacy SQLite to Postgres"
	@echo "  make setup-db-roles  Create restricted tallied_app Postgres role"
	@echo "  make seed-test    Reset DB with Claudius Banks test data"
	@echo "  make test         Run backend tests (fast, SQLite)"
	@echo "  make test-e2e     Run E2E tests against PostgreSQL"
	@echo "  make typecheck    Run frontend TypeScript strict check"
	@echo "  make pre-commit   Run tests + typecheck (always run before pushing)"
	@echo "  make lint         Run linters"
	@echo "  make build        Build Docker image"
	@echo "  make clean        Remove build artifacts"
	@echo "  make install      Install all dependencies"
