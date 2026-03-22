# Tallied

**Your finances, tallied.**

A comprehensive personal finance dashboard that tracks net worth, income, spending, investments, property, and retirement planning — all in one place.

![Dashboard](https://img.shields.io/badge/status-active-green) ![Python](https://img.shields.io/badge/python-3.12+-blue) ![Vue](https://img.shields.io/badge/vue-3-green) ![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Dashboard** — Net worth overview, liquidity layers, compensation split, upcoming RSU vests, recent spending
- **Cash** — Checking & savings accounts with balance history, notable transaction markers, and account-level detail
- **Spending** — Category breakdown, recurring expense detection, monthly trend, searchable transaction table
- **Income** — W2 data with gross-to-net waterfall, compensation history, salary vs RSU split across years
- **RSU** — Stock holdings with live prices, vest schedule, tax lot analysis (long/short term), vesting projections
- **401(k)** — Retirement account with Roth/pretax breakdown, contribution rates, holdings, balance history
- **Property** — Mortgage details, amortization schedule with principal/interest/escrow visualization, equity tracking (appreciation vs payments)
- **Assets** — Fixed capital assets (vehicles) with AI-estimated market values
- **Planning** — Year-by-year retirement projection table with editable assumptions, collapsible column groups, and "What You Need to Believe" narrative summaries

## Data Import

Tallied uses AI (Claude) to parse financial documents:

- **W2 forms** — Upload PDF, AI extracts tax/income fields
- **Pay stubs** — AI extracts salary/RSU split from YTD totals
- **Mortgage statements** — AI extracts balance, rate, payment breakdown
- **401(k) statements** — AI extracts balances, contribution rates, holdings
- **E-Trade exports** — RSU grants and vest schedules from spreadsheet exports
- **Plaid** — Automatic transaction sync from linked bank accounts

All imports go through a unified review workflow where you can accept/reject individual changes and chat with AI about the findings before anything is saved.

## Tech Stack

- **Backend**: FastAPI (Python) with SQLAlchemy ORM
- **Frontend**: Vue 3 + TypeScript + Tailwind CSS + ECharts
- **Database**: SQLite (PostgreSQL planned for multi-tenant)
- **AI**: Anthropic Claude API for document parsing
- **Bank Sync**: Plaid API for transaction imports
- **Stock Prices**: Yahoo Finance API (cached daily)

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Anthropic API key (for document parsing)

### Setup

```bash
# Clone
git clone https://github.com/your-username/tallied.git
cd tallied

# Install dependencies
make install

# Seed test data (Claudius Banks test persona)
make seed-test

# Start development servers
make dev
```

The app will be available at:
- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Environment Variables

Create `backend/.env`:
```
FINANCE_ANTHROPIC_API_KEY=sk-ant-...  # Required for AI document parsing
FINANCE_PLAID_CLIENT_ID=...           # Optional, for bank sync
FINANCE_PLAID_SECRET=...              # Optional, for bank sync
```

### Test Persona

The app ships with a test persona — **Claudius Banks** — a 30-year-old software engineer with realistic (but fake) financial data. Use `make seed-test` to populate the database with his data.

Login: `claudius@tallied.dev` / `demo123`

## Development

```bash
make dev          # Start backend + frontend
make test         # Run backend tests
make seed-test    # Reset DB with test data
make lint         # Run linters
make build        # Build Docker image
```

See [CLAUDE.md](CLAUDE.md) for full development documentation.

## Docker

```bash
# Build
docker build -t tallied .

# Run
docker run -p 8000:8000 -v tallied-data:/app/data tallied
```

## Architecture

```
backend/
├── app/
│   ├── api/          # FastAPI route handlers
│   ├── models/       # SQLAlchemy ORM models
│   ├── engine/       # Projection engine
│   ├── services/     # Business logic
│   └── schemas/      # Pydantic schemas
frontend/
├── src/
│   ├── views/        # Page components
│   ├── components/   # Reusable UI components
│   ├── composables/  # Vue composables
│   └── stores/       # Pinia state management
```

## License

MIT
