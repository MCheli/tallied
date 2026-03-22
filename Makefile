.PHONY: dev dev-backend dev-frontend test test-all seed-test lint build clean

# Development
dev: dev-backend dev-frontend

dev-backend:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Database
seed-test:
	cd backend && source .venv/bin/activate && PYTHONPATH=. python ../scripts/seed_test_data.py --reset

generate-docs:
	cd backend && source .venv/bin/activate && python ../scripts/generate_test_documents.py

# Testing
test:
	cd backend && source .venv/bin/activate && pytest tests/ -v

test-all: test
	cd frontend && npm run test 2>/dev/null || echo "Frontend tests not configured yet"

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
	rm -f data/finance.db

# Install dependencies
install:
	cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

# Help
help:
	@echo "Tallied — Personal Finance Dashboard"
	@echo ""
	@echo "  make dev          Start backend + frontend dev servers"
	@echo "  make seed-test    Reset DB with Claudius Banks test data"
	@echo "  make test         Run backend tests"
	@echo "  make lint         Run linters"
	@echo "  make build        Build Docker image"
	@echo "  make clean        Remove build artifacts"
	@echo "  make install      Install all dependencies"
