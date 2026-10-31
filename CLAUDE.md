# Tallied — Household Finance Dashboard

FastAPI + Vue 3 + PostgreSQL (schema per tenant). One household's accounts, transactions, income, RSUs, 401(k), property, vehicles and retirement projection in one database the owner can also query directly. Personal project, not a product.

## Read first

- `docs/PRODUCT.md` — what Tallied is, the five jobs, what every page shows and must never do, data sources and their status, rules, and the decisions awaiting the owner. Source of truth.
- `docs/ARCHITECTURE.md` — layout, tenancy, auth, data flow, migrations rule, frontend conventions, test harness, ledger schema, security rules.
- `docs/CONTRIBUTING-FEATURES.md` — how to add a tile, page, endpoint, import context, provider or AI feature, and what evidence each needs.
- `docs/requirements/ledger.yaml` — every requirement with acceptance criteria, status and evidence.
- `docs/DEPLOYING.md` — production on the home server.
- `docs/DEMO-PLAYBOOK.md` — how the public demo and login page were built; reusable for other apps.
- `docs/research/` — as-built briefs from October 2026 (what each page really does, with file:line evidence) and the Monarch post-mortem.
- `docs/archive/` — the March 2026 documents. Background only; not binding.
- `docs/REVIEW-2026-10-29.md` — the October punch list and the decisions taken on it.

## Rules

- A requirement is done only with evidence: a test on the real code path, plus a screenshot from `make tour` for anything visible. Update `docs/requirements/ledger.yaml` in the same commit.
- Never show a success message for something that did not happen. No stubs behind visible buttons.
- AI output is never saved unreviewed or unlabelled. Imports stage changes for confirmation; valuations carry source, model, date and reasoning.
- Every schema change ships an Alembic migration that iterates all tenant schemas and runs on an empty database.
- Financial routes use `get_tenant_db`; platform routes use `get_db`. Nothing from a request is interpolated into SQL.
- Secrets only in environment variables or encrypted columns. Claudius Banks is the only persona in code, fixtures, tests and screenshots; nothing real is committed.
- Every tile has an `InfoTooltip` that is true, and an empty state.
- Views call `frontend/src/api/client.ts`; no `fetch` in a view. Page chrome comes from the shared components.
- No `except Exception: pass`. Log what you swallow.
- Writes live in services. Any route touched for a feature moves its writes into `app/services/` in the same change, with a test; no new inline writers.
- `make pre-commit` must pass before every commit. It includes `build-smoke`: the minified production bundle served and loaded in a real browser. The dev server and the tour run unbundled modules and cannot see chunk-ordering failures (2026-10-29: a circular chunk blanked production).

## Quick start

```bash
# Postgres: Docker (make db-start) or, without Docker, Homebrew:
brew services start postgresql@16     # role tallied / tallied_dev, database tallied
make seed-test     # drop and rebuild the Claudius Banks tenant from fixtures/
make dev           # backend :8000 (uvicorn --reload) + frontend :5173 (vite)
make test          # backend unit tests (SQLite, fast)
make test-e2e      # backend e2e tests (Postgres + seed)
make typecheck     # vue-tsc -b
make test-frontend # vitest (frontend/tests/*.spec.ts)
make build-smoke   # build the production bundle and load it in headless Chrome (dev server never runs the real chunks)
make tour          # screenshots of every route into artifacts/screens/
make ledger-check  # validate the requirements ledger
make pre-commit    # lint + test + typecheck + test-frontend + build-smoke + ledger-check (same as CI)
```

Backend venv: `backend/.venv`. Env: `backend/.env` (prefix `FINANCE_`; see `backend/app/config.py`). Dev login: `claudius@tallied.dev` / `demo123` with `FINANCE_DEV_MODE=true`. API at `/api/v1`, reference at `/api/v1/scalar`.

## Layout

```
backend/app/{api,services,engine,models,schemas,ai,middleware}/   routes · logic · pure maths · ORM · pydantic · Claude client
backend/alembic/versions/            migrations (iterate tenant schemas)
backend/tests/                       pytest; test_e2e/ marked e2e
frontend/src/{views,components,composables,api,stores,router,types}/
scripts/                             seed_test_data.py · screenshot_tour.mjs · ledger_check.py · generate_test_documents.py
fixtures/test_documents/             Claudius documents + MANIFEST.md
artifacts/screens/                   tour screenshots (ledger evidence)
docs/                                see "Read first"
```

## Multi-tenancy in one paragraph

`public` holds platform tables (`users`, `tenants`, `tenant_memberships`, `api_keys`, `api_usage_logs`, `db_credentials`, `webhook_subscriptions`, `audit_logs`, `email_forwarding_addresses`); every other model lives in each tenant's schema. `get_tenant_context` reads the JWT cookie or `X-API-Key`; `get_tenant_db` sets `search_path` per request and re-applies it on every transaction; the pool checkout listener resets it to `public`. Any code needing a tenant session outside a request uses the same helper. Details and the migration template are in `docs/ARCHITECTURE.md`.

## Test persona: Claudius Banks

Age 30, software engineer at Microsoft (MSFT). $145K salary + $65K RSU. House at 456 Oak Street, Springfield MA ($520K), mortgage $380K at 4.25%. 401(k) at Fidelity. 2019 Toyota RAV4, 2015 Honda Civic. Tenant schema `tenant_claudius`. The seed's dates are relative to the day it runs.

## Pages

Overview: Dashboard, Guide · Money: Spending, Income, Cash · Investments: RSU, 401(k) · Property: Property, Assets · Planning · Platform: Database, API, Settings, Admin Portal (admin only).
