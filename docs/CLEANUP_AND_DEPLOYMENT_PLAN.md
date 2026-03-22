# Cleanup, Testing, and Deployment Plan

## Overview
Preparing the personal finance app for public repository, deployment to home server (money.your-domain.com), and establishing a proper development workflow optimized for Claude Code.

---

## 1. Repo Sanitization (Remove Personal Data)

### Files to Delete
- `2023 W2.pdf`, `2024 W2.pdf`, `2025 W2 (1).pdf` — Personal W2 forms
- `etrade_holdingsbystatus_expanded.xlsx`, `etrade_holdingsbytype_expanded.xlsx` — RSU data
- `Screenshot 2026-03-11 at 8.52.25 PM.png` — Personal screenshot
- `data/` directory — Contains SQLite DB and JSON/CSV exports with real financial data
- `monarch_session.pickle` — Session cookie

### Code to Sanitize
- `config.yaml` — Replace personal data with example/placeholder values. Move real values to `.env`
- `backend/app/api/property.py` — Remove hardcoded escrow amount ($842.17), use config
- `backend/app/api/planning.py` — Remove hardcoded config path, use relative path or env var
- `backend/app/api/ingest.py` — Remove `chrome_extension` source references

### .gitignore Updates
Add: `*.pdf`, `*.xlsx`, `*.xls`, `Screenshot*`, `*.pickle`, `data/*.db`, `data/*.json`, `data/*.csv`, `.DS_Store`, `frontend/dist/`

### Git History
Use `git filter-repo` or BFG to scrub any accidentally committed sensitive files from git history before making public.

---

## 2. Test User & Fake Data

### Test Persona: "Alex Rivera"
- Age 30, software engineer, homeowner
- Property: 456 Oak Street, Springfield, MA 01101 ($520,000 value)
- Mortgage: $380,000 @ 4.25%, $2,450/month
- Salary: $145,000 base + $65,000 RSU = $210,000 gross
- 401(k): $185,000 (70% Roth, 30% pretax), 10% deferral
- Vehicles: 2019 Toyota RAV4 (45K mi, good, $22,000), 2015 Honda Civic (98K mi, fair, $8,500)
- RSU: 8 grants from "ACME Corp" (ticker: ACME), various vest dates

### Fake Documents to Generate
- Fake W2 PDFs (2023, 2024, 2025) with Alex Rivera's data
- Fake mortgage statement PDF
- Fake 401(k) statement PDF
- Fake E-Trade holdings spreadsheet
- Fake pay stubs

### Database Seed Script
- `scripts/seed_test_data.py` — Creates the test persona's complete financial picture
- Populates: accounts, balance_snapshots, transactions (generated), W2 records, RSU grants, vest events, mortgage, property valuation, vehicles, retirement account
- Can be run with: `make seed-test`

---

## 3. Testing Infrastructure

### Backend Tests (pytest)
```
backend/tests/
├── conftest.py          # Fixtures: test DB, test client, test data
├── test_api/
│   ├── test_accounts.py
│   ├── test_income.py
│   ├── test_import.py
│   ├── test_property.py
│   ├── test_retirement.py
│   ├── test_rsu.py
│   ├── test_spending.py
│   └── test_planning.py
├── test_engine/
│   └── test_projection.py
└── test_models/
    └── test_schemas.py
```

### Test Configuration
- Use SQLite in-memory for test DB (fast, isolated)
- `conftest.py` provides: test FastAPI client, seeded DB with Alex Rivera data
- Tests can run with: `make test` or `pytest backend/tests/`

### Frontend Tests (Vitest)
- Basic component render tests for key views
- API mock for testing without backend
- Run with: `make test-frontend` or `npm run test`

### Claude Code Integration
- `CLAUDE.md` at repo root with project context, conventions, and test commands
- Pre-commit hook suggestion for running tests
- Test commands in Makefile for easy execution

---

## 4. Basic Authentication

### Approach: Simple JWT auth (not full SSO)
- User model: `id`, `email`, `password_hash`, `display_name`, `is_admin`
- JWT tokens issued on login, stored in httpOnly cookie
- Middleware checks JWT on all API routes
- Two initial users: "Mark" (your real data) and "Alex Rivera" (test data)
- Database isolation: user_id column on key tables (or separate DBs)

### Implementation
- `POST /api/auth/login` — Email + password → JWT
- `POST /api/auth/register` — Create account (admin only initially)
- `GET /api/auth/me` — Current user info
- `POST /api/auth/logout` — Clear cookie
- Frontend: Login page, auth store, route guards

### For Now (MVP)
- Simple password auth (bcrypt)
- No OAuth/SSO yet (that's Phase 2 per PLATFORM_VISION.md)
- User switching via login page
- Each user sees only their data

---

## 5. Documentation & Claude Code Optimization

### CLAUDE.md (Root)
```markdown
# Personal Finance App

## Quick Start
make dev          # Start backend + frontend
make test         # Run all tests
make seed-test    # Seed test database with Alex Rivera data
make lint         # Run linters

## Architecture
- Backend: FastAPI (Python 3.14) at /backend
- Frontend: Vue 3 + TypeScript at /frontend
- Database: SQLite (dev), PostgreSQL (prod planned)

## Key Directories
- backend/app/api/     — API route handlers
- backend/app/models/  — SQLAlchemy models
- backend/app/engine/  — Projection/calculation engines
- frontend/src/views/  — Page components
- frontend/src/components/ — Reusable components

## Testing
pytest backend/tests/   — Backend tests (uses in-memory SQLite)
cd frontend && npm test — Frontend tests

## Conventions
- Use existing patterns from similar files
- All monetary values stored as Decimal in DB
- API responses use float for JSON serialization
- Vue components use <script setup lang="ts">
- Tailwind CSS with dark mode (dark: prefix)
```

### Makefile
```makefile
dev:           Start backend + frontend dev servers
test:          Run pytest
test-frontend: Run vitest
seed-test:     Seed Alex Rivera test data
lint:          Run ruff + eslint
build:         Build frontend + Docker image
deploy:        Push Docker image to ghcr.io
clean:         Remove build artifacts
```

### pyproject.toml
- Replace `requirements.txt` with proper `pyproject.toml`
- Use `uv` for fast dependency management
- Define test dependencies, dev dependencies

---

## 6. Deployment (Home Server)

### Architecture
```
money.your-domain.com
        │
   ┌────▼────┐
   │  Nginx  │  (home-server reverse proxy)
   └────┬────┘
        │
   ┌────▼──────────────────┐
   │  Docker Container     │
   │  ┌──────────────────┐ │
   │  │ Nginx (static)   │ │  ← Serves Vue SPA
   │  │ Port 80          │ │
   │  └────────┬─────────┘ │
   │           │ /api/*     │
   │  ┌────────▼─────────┐ │
   │  │ Gunicorn+Uvicorn │ │  ← FastAPI with workers
   │  │ Port 8000        │ │
   │  └────────┬─────────┘ │
   │           │            │
   │  ┌────────▼─────────┐ │
   │  │ SQLite DB        │ │  ← Volume mount for persistence
   │  │ /data/finance.db │ │
   │  └──────────────────┘ │
   └───────────────────────┘
```

### Dockerfile (multi-stage)
```
Stage 1: Build frontend (node:20-alpine)
  → npm install && npm run build

Stage 2: Production (python:3.14-slim)
  → Install Python deps
  → Copy built frontend to /static
  → Copy backend code
  → Nginx config to serve /static and proxy /api to uvicorn
  → CMD: supervisord (nginx + gunicorn)
```

Alternative simpler approach:
```
Stage 1: Build frontend
Stage 2: Python + uvicorn only
  → Serve static files via FastAPI's StaticFiles mount
  → No nginx in container (simpler, adequate for personal use)
  → CMD: gunicorn -k uvicorn.workers.UvicornWorker
```

### FastAPI Production Serving
- **Gunicorn** with **Uvicorn workers** (standard for FastAPI production)
- `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000`
- No uWSGI needed — Gunicorn + Uvicorn is the standard stack
- The home server's Nginx handles TLS termination and proxying

### Docker Compose (for home server)
```yaml
# In home-server docker-compose.yml
finance:
  image: ghcr.io/your-username/personal-finance:latest
  container_name: finance
  restart: unless-stopped
  volumes:
    - finance-data:/app/data  # Persist SQLite DB
  environment:
    - FINANCE_ANTHROPIC_API_KEY=${FINANCE_ANTHROPIC_API_KEY}
    - FINANCE_PLAID_CLIENT_ID=${FINANCE_PLAID_CLIENT_ID}
    - FINANCE_PLAID_SECRET=${FINANCE_PLAID_SECRET}
  networks:
    - infrastructure
```

### CI/CD (GitHub Actions)
```yaml
on push to main:
  1. Run tests (pytest + vitest)
  2. Build Docker image
  3. Push to ghcr.io/your-username/personal-finance:latest
  4. (Optional) Trigger deploy on home server via webhook
```

### Database Considerations
- **SQLite for now**: Single-file, works great in Docker with volume mount
- **Postgres migration later**: Per PLATFORM_VISION.md, when multi-tenancy is needed
- **Backups**: Cron job on home server to backup `/data/finance.db` daily

---

## 7. Dead Code Cleanup

### Delete These Directories
- `/pages/` — Old Streamlit pages (6 files)
- `/analysis/` — Old analysis scripts (5 files)
- `/loaders/` — Old root-level loaders (3 files, backend has replacements)
- `/models/` — Old root-level models (backend has proper models)

### Delete These Files
- `app.py` — Old Streamlit entry point
- `monarch_login.py` — Old manual login script
- `monarch_pull.py` — Old data pull script
- `snapshot_loader.py` — Old snapshot loader
- `frontend/src/views/AssetsView.vue` — Orphaned (replaced by NewAssetsView)

### Rename
- `frontend/src/views/NewAssetsView.vue` → `frontend/src/views/AssetsView.vue`
- Update router reference accordingly

### Fix References
- `ingest.py`: Change `source="chrome_extension"` to `source="document_upload"`
- `property.py`: Move hardcoded escrow to config/env
- `planning.py`: Use relative path for config.yaml

---

## 8. Project Naming

Brainstorm (down-to-earth, says what it does):

1. **Ledger** — Simple, classic. "My financial ledger." Domain: ledger.your-domain.com
2. **Cashbook** — Physical thing that tracks money. Familiar.
3. **Clearview** — Clear view of your finances. Clean.
4. **Tally** — Short, memorable. "Keep a tally of your money."
5. **Numera** — From "numbers." Sounds like software.
6. **Vault** — Where you keep valuables. Secure feel.
7. **Steadfast** — Financial stability. Maybe too abstract.
8. **Basecamp Finance** — Grounded, organized. But might conflict with 37signals.
9. **Mint** (taken), **Monarch** (taken), **YNAB** (taken)
10. **Folio** — As in "portfolio." Short, clean. money.your-domain.com still works.

**Final Decision**: **Tallied** — "Your finances, tallied." Not an existing product. Clean namespace.

---

## Final Decisions

- **Project name**: Tallied — "Your finances, tallied."
- **Test persona**: Claudius Banks (Claude-inspired gentleman)
- **Deployment**: Single container, FastAPI serves Vue SPA + API (Gunicorn + Uvicorn workers)
- **Auth**: Pre-seeded users only (Mark + Claudius Banks), JWT with httpOnly cookies
- **Test docs**: Generate fake PDFs with reportlab using Claudius Banks' data
- **Database**: SQLite for now, volume-mounted in Docker
- **URL**: money.your-domain.com
- **Docker registry**: ghcr.io/your-username/tallied:latest (follows cookbook pattern)

---

## Claudius Banks — Test Persona

- **Name**: Claudius Banks, age 30
- **Address**: 456 Oak Street, Springfield, MA 01101
- **Employer**: Microsoft (ticker: MSFT)
- **Salary**: $145,000 base + $65,000 RSU = $210,000 gross
- **Mortgage**: $380,000 @ 4.25%, $2,450/month on $520,000 property
- **401(k)**: $185,000 (70% Roth / 30% pretax), 10% pretax + 2% Roth deferral
- **RSU**: 8 grants of MSFT stock, various vest dates, current price ~$95/share
- **Vehicles**: 2019 Toyota RAV4 (45K mi, good, $22,000), 2015 Honda Civic (98K mi, fair, $8,500)
- **Cash**: ~$35,000 across checking ($12,000) + savings ($18,000) + HYSA ($5,000)

---

## Implementation Order

**CRITICAL**: Step 1 must happen before deleting personal data.

### Step 1: Create Claudius Banks test data FIRST
a. Define Claudius Banks' full financial profile
b. Generate fake PDF documents (W2s, mortgage statement, 401k statement, pay stubs) using reportlab
c. Create `scripts/seed_test_data.py` to populate DB
d. Store fake docs in `fixtures/test_documents/` (committed to repo)
e. Verify seed script runs and fake PDFs parse through import workflow

### Step 2: Repo sanitization (only after step 1 verified)
a. Delete personal PDFs, spreadsheets, screenshots from repo root
b. Sanitize `config.yaml` — use Claudius Banks defaults
c. Remove hardcoded personal data from source code
d. Update `.gitignore`
e. Scrub git history before making public

### Step 3: Dead code cleanup
a. Delete old Streamlit app (pages/, app.py, analysis/, loaders/, models/)
b. Rename NewAssetsView.vue → AssetsView.vue
c. Remove chrome_extension references from ingest.py
d. General code cleanup

### Step 4: CLAUDE.md + Makefile + pyproject.toml
Dev workflow optimized for Claude Code

### Step 5: Testing infrastructure
pytest with Claudius Banks fixtures, key API tests

### Step 6: Basic auth
User model, JWT, login page, pre-seeded users

### Step 7: Dockerfile + CI/CD
Multi-stage build, GitHub Actions, push to ghcr.io

### Step 8: Deploy to home server
Add tallied service to home-server, nginx config for money.your-domain.com
