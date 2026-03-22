# Tallied — Personal Finance Dashboard

## Quick Start

```bash
make dev          # Start backend + frontend dev servers
make seed-test    # Reset DB and seed with Claudius Banks test data
make test         # Run backend tests
make test-all     # Run backend + frontend tests
make lint         # Run linters
make build        # Build Docker image
```

## Architecture

- **Backend**: FastAPI (Python 3.14) — `/backend/`
- **Frontend**: Vue 3 + TypeScript + Tailwind CSS + ECharts — `/frontend/`
- **Database**: SQLite (dev/prod), PostgreSQL planned for multi-tenant future
- **AI**: Anthropic Claude API for document parsing and vehicle valuation

## Key Directories

```
backend/
├── app/
│   ├── api/          # Route handlers (one file per domain)
│   ├── models/       # SQLAlchemy ORM models
│   ├── engine/       # Projection/calculation engines
│   ├── services/     # Business logic services
│   ├── loaders/      # Data import loaders (E-Trade RSU)
│   ├── parsers/      # Document parsers (Monarch, E-Trade)
│   └── schemas/      # Pydantic request/response schemas
├── alembic/          # Database migrations
└── tests/            # pytest test suite

frontend/
├── src/
│   ├── views/        # Page-level Vue components
│   ├── components/   # Reusable components (by domain)
│   ├── composables/  # Vue composables (useImportModal, useChartDefaults, etc.)
│   ├── api/          # API client + planning API
│   ├── stores/       # Pinia stores
│   └── types/        # TypeScript type definitions
└── index.html

scripts/               # Utility scripts
├── generate_test_documents.py  # Create fake PDFs for Claudius Banks
└── seed_test_data.py           # Populate DB with test data

fixtures/
└── test_documents/    # Fake financial documents for testing

docs/                  # Design documents and plans
```

## Development

### Backend (FastAPI)
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Frontend (Vue + Vite)
```bash
cd frontend
npm run dev  # Runs on port 5173
```

### Database
- SQLite file at `data/finance.db` (auto-created on first run)
- Reset with test data: `make seed-test`
- Models auto-create tables on startup via `Base.metadata.create_all()`

## Conventions

### Backend
- All monetary values stored as `Decimal` in DB, serialized as `float` in JSON
- API routes prefixed with `/api/` (legacy) or `/api/v1/` (new unified import)
- Pydantic models for request validation
- SQLAlchemy 2.0+ with `Mapped` and `mapped_column`

### Frontend
- Vue components use `<script setup lang="ts">`
- Tailwind CSS v4 with `dark:` prefix for dark mode
- ECharts via `vue-echarts` — register components explicitly with `use()`
- `useChartDefaults()` composable for consistent chart styling
- `InfoTooltip` component for hover explanations on every data tile

### Import Workflow
- Unified import modal launched via `useImportModal()` composable
- Context-aware: income, retirement, property, rsu, general
- Backend: `/api/v1/import/upload` → session → review → confirm
- AI chat for Q&A and corrections during review

## Test Persona: Claudius Banks
- Age 30, software engineer at Microsoft (MSFT)
- $145K salary + $65K RSU = $210K gross
- Property: 456 Oak Street, Springfield MA ($520K)
- Mortgage: $380K @ 4.25%
- 401(k): $185K at Fidelity
- Vehicles: 2019 Toyota RAV4, 2015 Honda Civic

## Pages
Dashboard, Spending, Cash, RSU, 401(k), Property, Assets, Planning, Income, Settings, Admin, Guide

## Environment Variables
```
FINANCE_ANTHROPIC_API_KEY=sk-...  # For AI document parsing
FINANCE_PLAID_CLIENT_ID=...       # For bank sync (optional)
FINANCE_PLAID_SECRET=...          # For bank sync (optional)
```
