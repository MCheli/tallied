# Tallied — Architecture

How the code is put together and the rules that keep it that way. What the product *is* lives in `docs/PRODUCT.md`; what is required and proven lives in `docs/requirements/ledger.yaml`. Last reviewed 2026-10-29.

## Stack

- **Backend** `backend/`: FastAPI, SQLAlchemy 2.0 (`Mapped` / `mapped_column`), Alembic, Pydantic v2, psycopg2. Python 3.13 (`.python-version`, the image and CI); the pinned floors are in `backend/requirements.txt`.
- **Frontend** `frontend/`: Vue 3 `<script setup lang="ts">`, Vite, Tailwind v4 (`dark:` variants), ECharts via `vue-echarts`, Pinia, Vue Router.
- **Database**: PostgreSQL 16, one schema per tenant plus `public` for platform tables. Tests use SQLite in memory.
- **AI**: Anthropic Claude for document parsing, receipt parsing and asset valuation, through `backend/app/ai/` (one client, one place to pick models).
- **Runtime**: one Docker image (`Dockerfile`) that serves the built SPA and the API with gunicorn; `backend/entrypoint.sh` runs `alembic upgrade head` first. The sync scheduler runs in the web process unless `APP_ROLE=web|scheduler` splits it out (`backend/app/scheduler/__main__.py`).

## Layout

```
backend/app/
  api/          one router module per domain; thin: parse request, call service, shape response
  services/     business logic and writes (tenant_service, planning_service, sync_scheduler, ...)
  engine/       pure calculation: projection, sensitivity, net worth, cash flow, spending, variance
  models/       SQLAlchemy models; register new ones in models/__init__.py
  schemas/      Pydantic request/response models
  ai/           Claude client (structured outputs), schemas, model ids from settings
  services/providers/  bank/broker provider protocol + registry (SimpleFIN)
  middleware/   rate limit, API usage logging
  database.py   engine, SessionLocal, pool-checkout search_path reset
  dependencies.py  TenantContext, get_tenant_context, get_tenant_db, require_admin
  config.py     Settings (env prefix FINANCE_, loaded from backend/.env)
backend/alembic/versions/   migrations
backend/tests/              pytest (unit: SQLite; e2e: Postgres, marker e2e)
frontend/src/
  views/        one page per route
  components/   common/ (MetricCard, ChartContainer, InfoTooltip, SqlViewerModal), per-domain folders
  composables/  useChartDefaults, useFormatters, useImportModal, ...
  api/          client.ts: the only place that calls fetch
  stores/       Pinia (auth, ...)
  router/       routes + auth guard
  types/        shared TS types for API payloads
scripts/        seed_test_data.py, screenshot_tour.mjs, ledger_check.py, generate_test_documents.py
fixtures/       Claudius Banks documents used by the seed, tests and screenshots
artifacts/screens/  screenshots from the tour, referenced as ledger evidence
docs/           PRODUCT.md, this file, CONTRIBUTING-FEATURES.md, DEPLOYING.md, requirements/, research/, archive/
```

## Multi-tenancy

Tallied is a household app, but it was built multi-tenant and that structure stays because it is what isolates data and what the deployment runs. It must keep working; it is not a place to add features.

- `public` holds the platform tables listed in `tenant_service.PLATFORM_TABLES`: `users`, `tenants`, `tenant_memberships`, `api_keys`, `api_usage_logs`, `db_credentials`, `webhook_subscriptions`, `audit_logs`, `email_forwarding_addresses`, `alembic_version`.
- Every other model lives in each tenant's schema (`tenant_<8 hex>`), created by `create_tenant_schema()` with `Base.metadata.create_all` at tenant creation. Existing tenants only change through migrations.
- A request's tenant comes from the JWT cookie `tallied_token` or an `X-API-Key` header (`get_tenant_context`). `get_tenant_db` opens a session with `search_path = "<tenant>", public` and re-applies it on every new transaction. The pool `checkout` listener in `database.py` resets `search_path` to `public` so nothing leaks between requests.
- Code that needs a tenant session outside a request (scheduler, email webhook, seed) must use the same helper, not its own `SET search_path`. A single `SET` is undone by the checkout reset after the next commit; this bit the seed in October 2026.
- Tenant schema names are validated against `Tenant.validate_schema_name` before they are interpolated into SQL. Nothing else from a request is ever interpolated into SQL.
- The SQL runner on the Database page runs with `search_path` limited to the tenant schema, in a read-only transaction, under a statement timeout, as a role with no privileges on `public`. It must never be able to read platform tables or call superuser functions.

## Auth

- Production: Google SSO. New users land in `pending` until an admin approves them.
- Dev (`FINANCE_DEV_MODE=true`): email/password login. Claudius Banks (`claudius@tallied.dev` / `demo123`) is the only persona.
- Access token: 4h JWT in an httpOnly cookie. Refresh token: 30 days, rotated on `/auth/refresh`. Both refresh and API-key auth must check `user.status` so a suspended user loses access at the next refresh, not in 30 days.
- API keys are HMAC-SHA256 hashed with a pepper. Their `permissions` (`read` / `write` / `admin`) are enforced: a read key cannot reach a mutating route.

## Data flow

Data enters through these paths only (details and current status in `PRODUCT.md`, "Data sources"):

1. **Unified AI import** (`api/import_unified.py`, `components/import/ImportModal.vue`): upload → AI extraction → review → confirm. Nothing is written until confirm.
2. **Provider sync** (`services/providers/`, `services/sync_scheduler.py`): a provider turns its stored, encrypted credential into a `ProviderSnapshot`; one generic loop upserts accounts, balance snapshots and transactions and finalizes the `sync_jobs` row. SimpleFIN is the only provider today.
3. **Email receipts** (`workers/email-receipt`, `api/email_import.py`): a forwarded receipt becomes one transaction.
4. **Manual edits** from Settings and the page-level forms (accounts, income records, vehicles, property, plans).
5. **The seed** (`scripts/seed_test_data.py --reset`), which builds the Claudius tenant from `fixtures/`.

Every write goes through a service function; route handlers do not contain business logic. No `except Exception: pass`: every swallowed exception is logged with context.

## Database migrations

Any schema change ships an Alembic migration in the same commit, and the migration iterates every tenant schema:

```python
def upgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()
    for (schema,) in schemas:
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        # DDL with IF NOT EXISTS / IF EXISTS
    conn.execute(sa.text("SET search_path TO public"))
```

Platform tables are created by migrations too, so `alembic upgrade head` on an empty database produces a bootable system without the app's lifespan creating anything. CI proves it: a job runs `alembic upgrade head` against an empty Postgres and then boots the app.

Local dev on a machine without Docker: `brew services start postgresql@16`, then `make seed-test` (which drops and recreates everything) followed by `alembic stamp head`. See `DEPLOYING.md` for production.

## Frontend conventions

- Views call `api.*` from `frontend/src/api/client.ts`. No `fetch` in a view or component. The client handles 401 refresh, `res.ok` checks and JSON errors once.
- Page chrome comes from shared components: `PageHeader` (title, subtitle, wrapping toolbar), `DataTable` (horizontal scroll container, consistent header styling), `MetricCard`, `ChartContainer`, `InfoTooltip`. A page must not hand-roll these.
- Every data tile has an `InfoTooltip` explaining what it shows and an empty state when there is no data for the selected period.
- Numbers and dates are formatted through `useFormatters`. The null placeholder is a single em dash.
- Charts take their colours and text colours from `useChartDefaults`, which reads a reactive theme store, so switching dark mode re-themes every chart.
- The layout works at 390px: nothing wider than the viewport except tables and code inside their own scroll containers. The tour log (`artifacts/screens/tour-log.json`) lists horizontal overflow per route; a page is not done with overflow in that list.
- Public routes (`/login`, `/pending-approval`, `/plaid-oauth-callback`) render without the sidebar shell.

## Test harness

- `make test`: backend unit tests on SQLite in memory. These cover the engines, services and route shapes.
- `make test-e2e`: tests marked `e2e` against the local Postgres with the Claudius seed.
- `make typecheck`: `vue-tsc -b`.
- `make test-frontend`: Vitest (`frontend/tests/*.spec.ts`, jsdom, Vue Test Utils). Page logic that needs testing lives in composables so the specs stay small.
- `make tour`: `scripts/screenshot_tour.mjs` logs in as Claudius and captures every route at 390 and 1440 into `artifacts/screens/<route>/{mobile,desktop}.png`, writing console errors, failed requests and overflow to `artifacts/screens/tour-log.json`. Requires `make dev` and a seeded database.
- `make ledger-check`: validates the requirements ledger (below).
- `make pre-commit` runs backend tests, typecheck, frontend tests and the ledger check. It must pass before every commit; CI runs the same.

AI paths are tested with recorded responses, never with live calls in CI. `fixtures/test_documents/` plus its manifest is the evaluation set for document import.

## Requirements ledger

`docs/requirements/ledger.yaml` has one entry per requirement:

```yaml
- id: LOOK-001            # UPPER-CASE segments: <JOB or NFR-AREA>-<n>
  title: Net worth at a glance
  job: look               # look | feed | understand | plan | platform
  area: dashboard         # page or subsystem
  priority: p0            # p0 must work, p1 should, p2 nice
  visible: true           # optional; done + visible needs a screenshot
  done_means:             # observable criteria naming the fixture that proves each
    - "With the Claudius seed, the Dashboard shows a Net Worth tile equal to the sum of ..."
  status: todo            # todo | in_progress | done | deprecated
  evidence:
    - backend/tests/test_snapshot.py::test_net_worth_sums_latest_balances
    - artifacts/screens/dashboard/desktop.png
  notes:
    - "2026-10-29: created from the October review"
```

`scripts/ledger_check.py` fails when a `done` entry has no evidence, when evidence does not resolve (a Python test must contain `def <name>`; a `.spec.ts`/`.test.ts` must contain the title; a path must exist), when `done` has no test, when `done` + `visible` has no screenshot, or when `deprecated` lacks a dated note and evidence that the thing is off. The ledger is updated in the same commit as the work it describes.

## Security rules

- Secrets only in environment variables (`backend/.env` locally, the server's env in production). Never in code, fixtures or docs.
- Provider credentials (SimpleFIN access URL, anything similar) are encrypted at rest with `FINANCE_CREDENTIAL_KEY`.
- Inbound webhooks (email receipts) verify a shared secret with a constant-time compare and identify the tenant from something the sender cannot forge.
- Outbound requests to user-supplied URLs (webhooks) refuse private and link-local addresses.
- Dev mode refuses to start against a non-local database. Production refuses to start with default secrets.
- Rate limiting covers login and every authenticated route, not only API keys.
