# Tallied

**Your finances, tallied.**

A comprehensive personal finance dashboard that tracks net worth, income, spending, investments, property, and retirement planning — all in one place. Built as a multi-tenant data platform with direct database access, API keys, and SQL transparency.

![Dashboard](docs/screenshots/dashboard.png)

## Features

### Dashboard
Net worth overview, liquidity layers, compensation split, upcoming RSU vests, spending summary, and net worth trend over time.

### Income
W2 and pay stub import via AI parsing. Gross-to-net waterfall chart, compensation breakdown (salary vs RSU), multi-year history.

![Income](docs/screenshots/income.png)

### Cash
Checking & savings account tracking with balance history, account breakdown donut, notable transaction markers, and per-account transaction detail.

![Cash](docs/screenshots/cash.png)

### RSU Holdings
Stock grants with live prices (Yahoo Finance), vest schedule tracking, tax lot analysis (long/short term capital gains), liquidation estimates, and vesting projections.

![RSU](docs/screenshots/rsu.png)

### 401(k) Retirement
Roth vs pretax balance breakdown, contribution rate tracking, fund holdings with live prices, and balance history.

![401k](docs/screenshots/retirement.png)

### Property
Mortgage amortization schedule with principal/interest/escrow visualization, equity position (appreciation vs payments), and property valuation tracking.

![Property](docs/screenshots/property.png)

### Spending
Category breakdown, recurring expense detection, monthly trend, searchable transaction table with time range controls.

![Spending](docs/screenshots/spending.png)

### Planning
Year-by-year retirement projection table with editable assumptions, collapsible column groups, plan comparison, and "What You Need to Believe" narrative summaries for each plan year.

### Assets
Fixed capital assets (vehicles) with AI-estimated market values.

### Unified Import
AI-powered document parsing with a unified modal workflow — upload any financial document, review AI-extracted changes, chat with AI about findings, then accept or reject before saving.

### Database Explorer
Interactive schema canvas (ERD) with Miro-style pan/zoom, SQL runner with syntax highlighting, and data preview — explore your financial data directly.

### SQL Transparency
Every dashboard KPI has a "View SQL" button showing the exact query behind the number. Clickable table references with inline data preview.

### API Access
Programmatic access via API keys. Full OpenAPI documentation at `/api/v1/scalar`. Create and manage keys from the API page.

![Login](docs/screenshots/login.png)

## Data Import

Tallied uses AI (Claude) to parse financial documents:

- **W2 forms** — AI extracts tax/income fields
- **Pay stubs** — AI extracts salary/RSU split from YTD totals
- **Mortgage statements** — AI extracts balance, rate, payment breakdown
- **401(k) statements** — AI extracts balances, contribution rates, holdings
- **E-Trade exports** — RSU grants and vest schedules from spreadsheet exports
- **Plaid** — Automatic transaction sync from linked bank accounts

All imports go through a unified review workflow where you can accept/reject individual changes and chat with AI about the findings before anything is saved.

## Tech Stack

- **Backend**: FastAPI (Python 3.14) with SQLAlchemy ORM
- **Frontend**: Vue 3 + TypeScript + Tailwind CSS v4 + ECharts
- **Database**: PostgreSQL 16 with schema-per-tenant isolation
- **Auth**: Google SSO + dev mode email/password login, JWT tokens
- **AI**: Anthropic Claude API for document parsing
- **Bank Sync**: Plaid API for transaction imports
- **Stock Prices**: Yahoo Finance API (cached daily)

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for PostgreSQL)
- Anthropic API key (for document parsing)

### Setup

```bash
# Clone
git clone https://github.com/MCheli/tallied.git
cd tallied

# Install dependencies
make install

# Start PostgreSQL
make db-start

# Seed test data (Claudius Banks test persona)
make seed-test

# Start development servers
make dev
```

The app will be available at:
- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- API reference (Scalar): http://localhost:8000/api/v1/scalar

### Environment Variables

Create `backend/.env`:
```
# Required
FINANCE_DATABASE_URL=postgresql://tallied:tallied_dev@localhost/tallied

# AI document parsing
FINANCE_ANTHROPIC_API_KEY=sk-ant-...

# Auth — use dev mode for local development
FINANCE_DEV_MODE=true
FINANCE_DEV_USER_EMAIL=admin@tallied.dev
FINANCE_DEV_USER_PASSWORD=tallied-admin-change-me

# Auth — Google SSO (production)
FINANCE_GOOGLE_CLIENT_ID=...
FINANCE_GOOGLE_CLIENT_SECRET=...

# Optional — bank sync
FINANCE_PLAID_CLIENT_ID=...
FINANCE_PLAID_SECRET=...
```

### Test Persona

The app ships with a test persona — **Claudius Banks** — a 30-year-old software engineer at Microsoft with realistic (but fake) financial data. Use `make seed-test` to populate the database.

Login: `claudius@tallied.dev` / `demo123`

## Development

```bash
make db-start     # Start PostgreSQL container (required first)
make dev          # Start backend + frontend
make test         # Run backend tests
make typecheck    # Run frontend TypeScript strict check
make pre-commit   # Run tests + typecheck (always run before pushing)
make seed-test    # Reset DB with test data
make lint         # Run linters
make build        # Build Docker image
```

See [CLAUDE.md](CLAUDE.md) for full development documentation.

## Docker

```bash
# Build
docker build -t tallied .

# Run (requires a PostgreSQL instance)
docker run -p 8000:8000 \
  -e FINANCE_DATABASE_URL=postgresql://user:pass@host/tallied \
  tallied
```

## Architecture

```
backend/
├── app/
│   ├── api/            # FastAPI route handlers
│   ├── models/         # SQLAlchemy ORM models
│   ├── engine/         # Projection engine
│   ├── services/       # Business logic (tenant service, etc.)
│   ├── schemas/        # Pydantic schemas
│   ├── database.py     # DB engine, get_db (public schema)
│   ├── dependencies.py # get_tenant_db (tenant schema), auth
│   └── config.py       # Settings from environment
frontend/
├── src/
│   ├── views/          # Page components
│   ├── components/     # Reusable UI components
│   ├── composables/    # Vue composables
│   ├── stores/         # Pinia state management
│   └── router/         # Vue Router with auth guards
```

### Multi-Tenancy

Tallied uses PostgreSQL schema-per-tenant isolation:
- **`public` schema**: Platform tables (users, tenants, API keys)
- **Tenant schemas** (e.g., `tenant_1`): All financial data (accounts, transactions, balances, etc.)
- The application sets `search_path` per request based on the authenticated user's tenant
- Financial routes use `get_tenant_db`, auth routes use `get_db`

## Copyright

Copyright (c) 2026. All rights reserved.
