# Adding to Tallied

How to add or change something without breaking the shape of the codebase. Read `docs/PRODUCT.md` first for what the product is, and `docs/ARCHITECTURE.md` for the rules this file applies.

## Ground rules

1. A requirement is done only with evidence: a test that exercises the real code path, and a screenshot from `make tour` for anything visible. Add or update the ledger entry in the same commit.
2. Never show a success message for something that did not happen. Do not ship a button whose action is a stub.
3. AI output is never saved without review. Imports stage changes; valuations are stored as labelled estimates with a source and date.
4. Every schema change ships an Alembic migration that iterates all tenant schemas.
5. Financial routes use `get_tenant_db`; platform routes use `get_db`. Nothing from a request is interpolated into SQL.
6. `make pre-commit` passes before every commit.

## Commands

```bash
make dev           # backend :8000 + frontend :5173 (Postgres must be running)
make seed-test     # drop and rebuild the Claudius tenant from fixtures/
make test          # backend unit tests (SQLite)
make test-e2e      # backend e2e tests (Postgres + seed)
make typecheck     # vue-tsc
make tour          # screenshots of every route into artifacts/screens/
make ledger-check  # validate docs/requirements/ledger.yaml
make pre-commit    # test + typecheck + ledger-check
```

## 1. A new tile or chart on an existing page

1. Backend: add or extend an endpoint in the page's `api/<domain>.py`. Keep the handler thin; put any calculation in `engine/` or `services/`. Add a unit test in `backend/tests/test_api/` that seeds the SQLite session and checks the numbers, including the empty case.
2. Frontend: add the typed call to `frontend/src/api/client.ts` and the payload type to `frontend/src/types/index.ts`. Render with `MetricCard` or `ChartContainer`, give it an `InfoTooltip` with a plain-language explanation, and an empty state.
3. Charts: build options through `useChartDefaults()` so colours follow the theme and labels behave on a phone (bottom legend, rotated or thinned axis labels).
4. Run `make tour <route>` and look at both captures. The tour log must show no overflow for the route.
5. Ledger: add or update the entry under the page's area with `done_means` naming the Claudius numbers it must show, and evidence pointing at the test and the screenshot.

## 2. A new page

Only when `PRODUCT.md` has a paragraph for it. Then:

1. Route in `frontend/src/router/index.ts` with `meta.title`; nav entry in `App.vue` under the right group.
2. View in `frontend/src/views/<Name>View.vue` built from `PageHeader`, `MetricCard`, `ChartContainer`, `DataTable`. No raw `fetch`, no local formatter functions, no `any` at the data boundary.
3. Add the route to `ROUTES` in `scripts/screenshot_tour.mjs` and to the Guide page's `pages` list.
4. Ledger entries for each thing the page promises.

## 3. A new endpoint

- Router module per domain under `backend/app/api/`, included in `main.py` on the `v1` app only.
- Request and response models in `backend/app/schemas/`. Decimal in the database, float in JSON.
- Mutating routes require write permission (`require_permission("write")`) so read-only API keys cannot call them.
- Test in `backend/tests/test_api/`: status, shape, tenant scoping (data from another schema must not appear), and the empty case.

## 4. A new import context (document type)

The unified import flow is `upload → extract → review → confirm`.

1. Add the Pydantic model describing what the AI must extract to `backend/app/ai/schemas.py` and the context prompt next to the existing ones in `import_unified.py`.
2. Extraction uses structured outputs through the shared client (`backend/app/ai/client.py`), never free-text JSON parsing.
3. The writer that applies confirmed changes lives in a service and whitelists the fields it may set per table.
4. Add a fixture document to `fixtures/test_documents/` with its expected extraction in the manifest, and a unit test that feeds a recorded AI response through review and confirm.
5. The modal (`components/import/ImportModal.vue`) picks the context from `useImportModal({ context })`; add the launch button on the page that owns the data.

## 5. A new data provider (bank or broker sync)

Providers implement the protocol in `backend/app/services/providers/base.py` (`get_connection(db)` and `fetch(credential) -> ProviderSnapshot`) and register once in `providers/__init__.py`; the scheduler's generic loop does the rest. SimpleFIN (`providers/simplefin.py`, routes in `api/simplefin_routes.py`) is the reference.

- Credentials are encrypted at rest with `services/crypto.encrypt_secret` (FINANCE_CREDENTIAL_KEY). The connect route never stores a raw password.
- The provider's accounts map to `Account` rows with `source` set to the provider name and `account_type` chosen at connect time, not guessed per sync.
- Syncs run through `sync_jobs` (NOTIFY wakes the scheduler, advisory lock prevents overlap, watchdog fails stuck jobs). Never fetch synchronously inside a request.
- Settings gets a tab rendered from the provider's metadata, not a copy of another provider's tab.
- Research notes for a provider go in `docs/research/<provider>.md`: what the API offers, what it does not, and what was verified against real accounts.

## 6. An AI feature

- All calls go through `backend/app/ai/client.py`: one client, model ids from settings (`FINANCE_AI_MODEL_IMPORT`, `FINANCE_AI_MODEL_FAST`), timeouts, usage logging.
- Output is a Pydantic model via structured outputs. No scanning for `{` in free text.
- User-supplied text (emails, documents) goes in as data with a clear instruction boundary; the model's output is validated before it touches a database field.
- Anything the model produces is shown to the user as a proposal or labelled estimate. It is not written as fact.
- Tests run on recorded responses. Add the document and the recording to `fixtures/`.

## 7. A migration

```bash
cd backend && source .venv/bin/activate
alembic revision -m "add_<thing>"
```

Iterate tenant schemas (pattern in `ARCHITECTURE.md`), use `IF NOT EXISTS` / `IF EXISTS`, and reset `search_path` to `public` at the end. Platform tables are changed directly in `public`. Run `alembic upgrade head` locally and confirm `make test-e2e` still passes. CI migrates an empty database; if your migration cannot run on an empty database, it is wrong.

## 8. Ledger evidence

Evidence strings:

- `backend/tests/<file>.py::<test_function>`
- `frontend/tests/<file>.spec.ts#<test title>`
- `artifacts/screens/<route>/<viewport>.png`
- any other repository path (a committed document, a research note)

`done` needs at least one test. `visible: true` + `done` needs at least one screenshot. `deprecated` needs a dated note and evidence it is off (for example a test asserting the route returns 404). The gate is `make ledger-check`.

## 9. Before you commit

- `make pre-commit`
- `make tour` for any visible change; commit the new captures
- Ledger updated
- No secrets, no personal documents (`.gitignore` blocks `*.pdf` outside `fixtures/`)
