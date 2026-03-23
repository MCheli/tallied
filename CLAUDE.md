# Tallied — Personal Finance Dashboard

## Quick Start

```bash
make db-start     # Start PostgreSQL container (required first)
make dev          # Start backend + frontend dev servers
make seed-test    # Reset DB and seed with Claudius Banks test data
make test         # Run backend tests
make typecheck    # Run frontend TypeScript strict check
make pre-commit   # Run tests + typecheck (always run before pushing)
make test-all     # Run backend tests + typecheck + frontend tests
make lint         # Run linters
make build        # Build Docker image
```

## Before Pushing
Always run `make pre-commit` before committing/pushing. This runs the same checks as CI:
- Backend pytest suite
- Frontend TypeScript strict checking (`vue-tsc --noEmit`)

If `make pre-commit` passes, CI will pass.

## Architecture

- **Backend**: FastAPI (Python 3.14) — `/backend/`
- **Frontend**: Vue 3 + TypeScript + Tailwind CSS + ECharts — `/frontend/`
- **Database**: PostgreSQL 16 (via Docker Compose), schema-per-tenant isolation
- **Auth**: Google SSO (production) + dev mode email/password login
- **AI**: Anthropic Claude API for document parsing and vehicle valuation

## Key Directories

```
backend/
├── app/
│   ├── api/          # Route handlers (one file per domain)
│   ├── models/       # SQLAlchemy ORM models
│   ├── engine/       # Projection/calculation engines
│   ├── services/     # Business logic services (tenant_service, etc.)
│   ├── loaders/      # Data import loaders (E-Trade RSU)
│   ├── parsers/      # Document parsers (Monarch, E-Trade)
│   ├── schemas/      # Pydantic request/response schemas
│   ├── database.py   # Engine, session factory, get_db (public schema)
│   ├── dependencies.py # get_tenant_db, get_tenant_context, auth helpers
│   └── config.py     # Pydantic settings (env vars)
├── alembic/          # Database migrations
└── tests/            # pytest test suite

frontend/
├── src/
│   ├── views/        # Page-level Vue components
│   ├── components/   # Reusable components (by domain)
│   ├── composables/  # Vue composables (useImportModal, useChartDefaults, etc.)
│   ├── api/          # API client + planning API
│   ├── stores/       # Pinia stores (auth, etc.)
│   ├── router/       # Vue Router with auth guards
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
- PostgreSQL 16 via Docker Compose (`make db-start`)
- Default connection: `postgresql://tallied:tallied_dev@localhost/tallied`
- Override via `FINANCE_DATABASE_URL` env var
- Reset with test data: `make seed-test`
- Tests use in-memory SQLite for speed (no Docker needed for CI)

## Multi-Tenancy

### Schema-Per-Tenant
- Each tenant gets a dedicated PostgreSQL schema (e.g., `tenant_1`, `tenant_2`)
- The `public` schema holds platform tables: `users`, `tenants`, `tenant_memberships`, `api_keys`
- Tenant schemas hold all financial data: accounts, transactions, balances, W2s, RSU grants, etc.
- The application sets `search_path` per request based on the authenticated tenant
- Pool checkout events reset `search_path` to `public` to prevent cross-tenant leaks

### Dependency Injection
- **`get_tenant_db`**: Provides a DB session scoped to the authenticated tenant's schema. Used by all financial data routes (spending, income, cash, RSU, retirement, property, etc.)
- **`get_db`**: Provides a DB session on the `public` schema. Used by auth routes, tenant management, and API key routes
- **`get_tenant_context`**: Extracts `TenantContext` (user_id, email, tenant_id, tenant_schema) from JWT cookie or `X-API-Key` header

### Authentication
- **Google SSO**: Primary auth method in production. Requires `FINANCE_GOOGLE_CLIENT_ID` and `FINANCE_GOOGLE_CLIENT_SECRET`
- **Dev mode**: When `FINANCE_DEV_MODE=true`, enables email/password login for local development. Uses `FINANCE_DEV_USER_EMAIL` and `FINANCE_DEV_USER_PASSWORD`
- JWT tokens stored in httpOnly cookies (`tallied_token`)
- API key auth via `X-API-Key` header for programmatic access

### API Keys
- Users can create API keys scoped to their tenant from the API page (`/developer`)
- Keys are SHA-256 hashed before storage
- Auth via `X-API-Key` header resolves to a `TenantContext` just like JWT auth
- API documentation available at `/api/v1/scalar`

## Conventions

### Backend
- All monetary values stored as `Decimal` in DB, serialized as `float` in JSON
- All API routes under `/api/v1/` prefix
- Financial routes use `get_tenant_db` dependency for tenant-scoped queries
- Auth and platform routes use `get_db` dependency for public schema queries
- Pydantic models for request validation
- SQLAlchemy 2.0+ with `Mapped` and `mapped_column`

### Frontend
- Vue components use `<script setup lang="ts">`
- Tailwind CSS v4 with `dark:` prefix for dark mode
- ECharts via `vue-echarts` — register components explicitly with `use()`
- `useChartDefaults()` composable for consistent chart styling
- `InfoTooltip` component for hover explanations on every data tile
- Auth guard on router redirects unauthenticated users to `/login`

### Import Workflow
- Unified import modal launched via `useImportModal()` composable
- Context-aware: income, retirement, property, rsu, general
- Backend: `/api/v1/import/upload` -> session -> review -> confirm
- AI chat for Q&A and corrections during review

## Test Persona: Claudius Banks
- Age 30, software engineer at Microsoft (MSFT)
- $145K salary + $65K RSU = $210K gross
- Property: 456 Oak Street, Springfield MA ($520K)
- Mortgage: $380K @ 4.25%
- 401(k): $185K at Fidelity
- Vehicles: 2019 Toyota RAV4, 2015 Honda Civic
- Login: `claudius@tallied.dev` / `demo123` (dev mode)

## Pages

Navigation is organized into groups:

- **Overview**: Dashboard, Guide
- **Money**: Spending, Income, Cash
- **Investments**: RSU, 401(k)
- **Property**: Property, Assets
- **Planning**: Planning
- **Platform**: Database, API, Settings, Admin Portal (admin only)

## Environment Variables

All prefixed with `FINANCE_` (loaded from `backend/.env`):

```
# Database
FINANCE_DATABASE_URL=postgresql://tallied:tallied_dev@localhost/tallied

# AI & External Services
FINANCE_ANTHROPIC_API_KEY=sk-ant-...   # Required for AI document parsing
FINANCE_PLAID_CLIENT_ID=...            # Optional, for bank sync
FINANCE_PLAID_SECRET=...               # Optional, for bank sync

# Auth — Google SSO (production)
FINANCE_GOOGLE_CLIENT_ID=...           # Google OAuth client ID
FINANCE_GOOGLE_CLIENT_SECRET=...       # Google OAuth client secret

# Auth — Dev mode (local development)
FINANCE_DEV_MODE=true                  # Enable email/password login
FINANCE_DEV_USER_EMAIL=admin@tallied.dev
FINANCE_DEV_USER_PASSWORD=tallied-admin-change-me

# App
FINANCE_SECRET_KEY=...                 # JWT signing key (change in production)
FINANCE_BASE_URL=http://localhost:8000 # Used for OAuth redirect URLs
```
