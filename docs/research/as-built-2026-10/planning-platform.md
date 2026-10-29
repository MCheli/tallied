# Tallied — Planning and Platform pages: as-built brief (2026-10-29)

Scope: Planning, Database, API, Settings (all tabs), Admin Portal (+ user/tenant detail), Guide, Login, Pending Approval, and the unified Import modal. Read-only investigation of `/Users/mcheli-mini/repos/tallied` plus curl/psql probing of the running backend (http://localhost:8000, dev mode, seeded tenant `tenant_claudius`, user `claudius@tallied.dev`, who is **not** an admin; no admin user exists in the seed DB, so admin-only endpoints could only be verified as 403).

Global facts that apply to every page below:

- Routing: `frontend/src/router/index.ts`. Every non-public route runs the guard at lines 131-152: unauthenticated -> `/login`; authenticated with no `current_tenant` -> `/pending-approval`. Public routes: `/login`, `/pending-approval`.
- Nav gating: `frontend/src/App.vue:124-130` hides `adminOnly` items (Admin Portal) when `auth.user.is_admin` is false. The three admin views additionally render an "Access Denied" card client-side; the backend enforces with `require_admin` (`backend/app/dependencies.py:98-108`, returns 403).
- Auth context: `get_tenant_context` (`dependencies.py:26-48`) reads `X-API-Key` first, else the `tallied_token` JWT cookie (claims: sub, email, tenant_id, tenant_schema). `get_tenant_db` (`dependencies.py:111-146`) opens a session and runs `SET search_path TO "<schema>", public` on every transaction begin. Note the trailing `, public` — tenant sessions can resolve unqualified names in `public`.
- Two mounts: the versioned app at `/api/v1` (with `SessionMiddleware`, `RateLimitHeaderMiddleware`, `UsageLoggerMiddleware`) and a **legacy mount at `/api`** with the same routers minus monarch/simplefin/email-* and with no middleware (`backend/app/main.py:319-349`). Two frontend clients still use the legacy base: `frontend/src/api/planning.ts:1` (`BASE='/api'`, used by Planning) and `frontend/src/api/admin.ts:1` (unused anywhere).
- Usage logging: `UsageLoggerMiddleware` (`backend/app/middleware/usage_logger.py`) writes one `public.api_usage_logs` row per `/api/v1/*` request for cookie **and** API-key auth, so the "API usage" numbers on the API page include normal browser traffic (verified: 188 requests, `per_key: []`).
- Env on this machine (`backend/.env` keys): DATABASE_URL, SECRET_KEY, DEV_MODE, DEV_USER_EMAIL, DEV_USER_PASSWORD, BASE_URL. No `FINANCE_ANTHROPIC_API_KEY`, no Plaid, no Google, no `FINANCE_EMAIL_WEBHOOK_SECRET`.

---

## 1. Planning (`/planning`)

Files: `frontend/src/views/PlanningView.vue`, `frontend/src/api/planning.ts`, `frontend/src/components/planning/AssumptionPanel.vue`, `backend/app/api/planning.py`, `backend/app/services/planning_service.py`, `backend/app/engine/projection.py` (+ `engine/forecast.py` for the unused forecast endpoint).

### 1. Purpose
Show a year-by-year table from the first W2 year to the configured retirement year, mixing actuals (past W2s + balance snapshots), a current-year forecast, and engine-projected plan years, so the user can see whether a named retirement scenario works and compare two scenarios.

### 2. Sections (page order)
1. Header "Financial Planning" with InfoTooltip (legend explanation). Status spinner: "Recalculating…" (assumption PUT in flight) or "Loading…".
2. Assumptions toggle button (gear icon) — opens the right sidebar.
3. **Plan selector** (`plan1Id`) — `GET /api/plans/` (legacy mount, `planning.ts:40`). On load picks the first plan with `is_active`, else the first plan. Changing it triggers `GET /api/plans/{id}/table` and `GET /api/v1/plans/{id}` (`client.ts:122`, for the assumptions list).
4. **"+ New Plan"** toggle -> inline form: Plan Name (text), Type select (base/optimistic/pessimistic/custom), Create button -> `POST /api/v1/plans/` with `{name, scenario_type, assumptions: []}`. Backend fills `DEFAULT_ASSUMPTIONS` (`planning.py:48-63`, 14 keys), runs the engine and stores projections; UI reloads list and selects the new plan.
5. **Compare selector** (`plan2Id`, "None" default; the plan-1 id is disabled) — `GET /api/plans/{id}/table`. When set, a Δ column appears after every metric column; Δ = plan1 − plan2, green/red coloured with "lower is better" for mortgage_balance, tax_paid, expenses_annual (`PlanningView.vue:304-311`). Footer line "Δ = A minus B".
6. Error banner (any of plansError/plan1Error/plan2Error).
7. Legend: Actuals (green), Forecast (amber), Plan (white, "click to expand").
8. **Projection table** (hover shows a `</>` "View SQL" button -> `SqlViewerModal` with hand-written SQL text, tables `plan_versions, plan_projections, actual_snapshots, forecasts`; the modal's "Run in SQL Runner" stores the SQL in `sessionStorage['sql-runner-query']` and navigates to `/database`).
   - Sticky columns: Year (current year highlighted indigo), Status badge (actuals/forecast/plan).
   - Four collapsible column groups (collapse state persisted in `localStorage['planning-collapsed-groups']`, default collapsed: Savings, Wealth):
     - Income: gross_income, base_salary, rsu_income
     - Tax & Take-home: tax_paid, take_home, contributions_401k
     - Savings: expenses_annual, savings_rate (always "—", see §5)
     - Wealth: net_worth, liquid_net_worth, investment_balance, retirement_balance, home_equity, mortgage_balance
   - Formatting: $K/$M abbreviations; savings_rate as percent; null -> "—".
   - Clicking a **plan** row expands a narrative row ("What {year} assumes") built client-side in `buildNarrative()` (`PlanningView.vue:327-405`) from the row, the previous row, `_meta` (rsu_source, rsu_vest_count) and the assumption map (keys `rsu_pct_of_comp`, `rsu_pct_annual_increase`, `investment_return`, `monthly_cash_savings`, `home_appreciation`).
   - Empty state "No projection data available for this plan."
9. **Assumptions sidebar** (w-80, sticky): title, hover "View SQL" (hand-written SQL over `plan_assumptions`), Close. `AssumptionPanel` groups assumptions by `category` (labels known: career, markets, spending, tax, housing, other; anything else shows the raw category string) and renders one range slider per assumption. Slider ranges: percentage keys 0..1 step 0.005; `retirement_age` 30..80 step 1; otherwise 0..max(5×value,1000) (or 3×value if >100k), step 10/100/1000. Every slider input -> local state update + debounced 600 ms `PUT /api/v1/plans/{id}` with `{assumptions:[{key,value},…]}` for **all** assumptions, then re-`GET /api/plans/{id}/table`.

### 3. Data flow
Tables (all in the tenant schema): `plan_versions` (1 row), `plan_assumptions` (15), `plan_projections` (58), `actual_snapshots` (0), `forecasts` (0), `contribution_configs` (0); reads `w2_records`, `balance_snapshots`+`accounts`, `mortgages`, `vest_events`, `rsu_grants`, `stock_prices`.

Endpoints:
- `GET /plans/` -> `plan_versions` ordered by created_at desc.
- `GET /plans/{id}` -> plan + assumptions + stored projections (PlanResponse).
- `POST /plans/` -> `planning_service.create_plan`: inserts `plan_versions`, `plan_assumptions` (defaults merged with user keys), then `build_projection_input(db)` + `run_projection` and inserts one `plan_projections` row per age from current_age to 90. Any engine exception is swallowed (`planning_service.py:192-194`) and the plan is saved without projections.
- `PUT /plans/{id}` -> `update_plan`: **deletes all** `plan_assumptions` and `plan_projections` for the plan, re-inserts the submitted assumptions, re-runs the engine (`planning_service.py:200-262`).
- `GET /plans/{id}/table` -> assembled on the fly (`planning.py:540-745`), no table writes except the stock-price cache (see below).
- Not used by the page but mounted: `DELETE /plans/{id}`, `GET /plans/compare?ids=`, `GET /plans/{id}/sensitivity`, `GET /plans/{id}/variance`, `POST /plans/actuals`, `GET /plans/forecasts/latest`, `POST /plans/forecasts/generate` (writes `forecasts`). `frontend/src/stores/planning.ts` wraps compare/sensitivity/variance/delete but no view imports it (dead code). `api.generateForecast` and `api.importData` in `client.ts` have no callers.

**Engine inputs** (`build_projection_input`, `planning_service.py:22-111`) — all come from other pages' data, *not* from the plan's own assumptions:
- Starting balances: latest `balance_snapshots` per account, summed by `accounts.display_group` for accounts with `is_active` and `include_in_nw`; keys are the lower-snake display group (`cash`, `investments`, `company_stock`, `home_equity`, `retirement`). The seed uses groups Cash/Investments/Retirement/Home Equity, so `company_stock` starts at 0.
- Salary and RSU income: `base_salary` / `rsu_income` of the W2 with the highest `tax_year` (2025: 145,000 / 65,000).
- Mortgage balance/rate/monthly payment: most recently updated `mortgages` row (362,450.75 @ 4.25%, $2,450/mo).
- 401(k) employee rate / employer match / IRS limit: latest `contribution_configs` row, else hard-coded 0.10 / 0.06 / 23,500 (table is empty, so defaults apply; `config.yaml` has 0.12/0.03 but is not read here).
- `current_age` is **hard-coded 33** (`planning_service.py:93`); `current_year` = today.

**Engine assumptions** consumed (`_assumptions_to_engine`, `planning.py:66-84` and the duplicate in `planning_service.py:114-132`): retirement_age, total_comp_growth, rsu_pct_of_comp, rsu_pct_annual_increase, rsu_pct_cap, rsu_tax_rate, investment_return, retirement_return, stock_price_growth, inflation, home_appreciation, monthly_cash_savings, retirement_spending, retirement_tax_rate. Any other key is stored but ignored.

**Engine mechanics** (`engine/projection.py:90-242`): working phase per year — total_comp grows by total_comp_growth (not in year 0), rsu_pct starts at actual rsu/total_comp then ramps by rsu_pct_annual_increase up to rsu_pct_cap; salary = total_comp×(1−rsu_pct); 401k = min(salary×employee_rate, limit×(1+inflation)^n) + salary×match; retirement grows at investment_return; RSU after-tax (×(1−rsu_tax_rate)) is split 50/50 into company_stock (grows at stock_price_growth) and investments (grows at investment_return); cash += monthly_cash_savings×12 with no growth; home value appreciates and the mortgage amortises monthly. Retired phase — no income; spending = retirement_spending inflated from current_year; gross withdrawal = spending/(1−retirement_tax_rate) drawn cash→investments→company_stock→retirement; balances then grow at retirement_return (cash 1%). Runs to age 90.

**Projection table columns** (what each cell means, by row status):
- `actuals` (year < current): gross_income = W2 `gross_pay`; base_salary = W2 `base_salary`; rsu_income = W2 `rsu_income`; tax_paid = federal+state+SS+medicare; contributions_401k = pretax+roth; take_home = gross − tax − 401k − cafeteria_125 − transit; expenses_annual and savings_rate = null; wealth columns = sum of the latest balance snapshot **within that calendar year** per account grouped by display_group (`_balances_for_year`), net_worth = sum of all groups, liquid = NW − home_equity − retirement, investment_balance = investments + company_stock; mortgage_balance = the *current* mortgage balance regardless of year.
- `forecast` (year == current): if a W2 for the year exists, all W2 figures × (12/current_month); if not (the seed case), base_salary = last year's W2 base, rsu_income = Σ vest_events in the year (actual events at fmv_at_vest×shares, future events at **today's Yahoo price**×shares), gross = base + rsu, tax = 0.30×base + 0.40×rsu, 401k = min(base×employee_401k_rate, 23,500), take_home = gross − tax − 401k; wealth columns from the latest snapshot per account (any date); mortgage_balance = current.
- `plan` (year > current): from the stored `plan_projections` row — gross = total_comp, base = salary, rsu = rsu_income **unless** the year has vest_events, in which case rsu is replaced by the vest-schedule amount and gross recomputed; tax = 0.35×base + rsu_tax_rate×rsu; 401k = min(base×employee_401k_rate, 23,500×(1+inflation)^n) where `employee_401k_rate` is read from the plan assumptions with fallback **0.15** (`planning.py:574`; the engine itself used 0.10); take_home = gross − tax − 401k; investment_balance = investments + company_stock; retirement, home_equity, net_worth straight from the row; liquid = NW − home_eq − retirement; mortgage_balance = null; `_meta.rsu_source` = vest_schedule|projection and `_meta.rsu_vest_count`.
- Year range: first W2 tax_year .. current_year + (retirement_age − age), where age and retirement_age come from **`config.yaml` `personal:` (30/60)**, not from the plan (`planning.py:552-561`). Metrics list is fixed (`_PLAN_METRICS`).
- Stock price: `get_or_fetch_price` (`services/stock_price.py`) hits Yahoo Finance over the network on the first table load per day and caches into `stock_prices` (source=yahoo), deleting any other row for today. Verified: `stock_prices` now holds MSFT 2026-10-29 531.01 from Yahoo.

### 4. Verified against seed (HTTP)
- `GET /api/v1/plans/` 200, 1 plan ("Retire at 60", base, is_active). `GET /api/v1/plans` (no slash) 307.
- `GET /api/plans/` (legacy base the view really uses) 200, same body.
- `GET /api/v1/plans/1` 200: 15 assumptions, 58 projections (ages 33..90, years 2026..2083).
- `GET /api/v1/plans/1/table` 200: years 2023..2056 (34 rows); 2023-2025 actuals, 2026 forecast, 2027-2056 plan. Populated. Row details: 2023/2024 wealth columns all 0 (no snapshots in those years); 2025 NW 409,481; 2026 forecast gross **299,386** (rsu 154,386); 2027 gross 327,596 (`vest_schedule`, 5 events), 2028 269,259 (3 events), 2029+ projection; income columns drop to 0 from **2053** (engine retirement at age 60 with hard-coded age 33) while the table keeps going to 2056; NW 11.09 M in 2056; mortgage_balance 362,451 for every actual/forecast row, null for plan rows.
- `GET /api/v1/plans/1/sensitivity` 200 (unused by UI). `GET /api/v1/plans/1/variance` 200 `[]` (no actual_snapshots). `GET /api/v1/plans/compare?ids=1` 200. `GET /api/v1/plans/forecasts/latest` 200 `{"forecasts":[]}`.
- Unauthenticated `GET /api/v1/plans/` 401.
- PUT not exercised (would rewrite seed assumptions); behaviour inferred from code.

### 5. Broken or suspicious
- **Age mismatch**: engine age hard-coded 33 (`planning_service.py:93`) vs `config.yaml` age 30 used for the table's year range (`planning.py:554`) vs the seed assumption `current_age=33` which nothing reads. Result: projections retire in 2053 but the table runs to 2056 with three zero-income "working" years, and the ages stored in `plan_projections.age` are wrong for the persona.
- **Retirement age from config, not the plan** (`planning.py:555,561`): moving the `retirement_age` slider re-runs the engine (so wealth columns change) but the table's last year never moves and the Status/phase display gives no hint of retirement.
- **Assumption vocabulary split**: `DEFAULT_ASSUMPTIONS` (14 keys, categories career/markets/spending/tax) vs the seed plan's 15 keys (categories personal/income/savings/returns/retirement; includes `current_age`, `life_expectancy`, `total_comp`, `pretax_401k_pct`, `roth_401k_pct`, `employer_match_pct`, `social_security_monthly`). The engine ignores the seed-only keys (sensitivity confirms 0 impact), the seed plan silently runs with engine defaults for rsu_pct_cap/rsu_tax_rate/stock_price_growth/retirement_return, and `AssumptionPanel.vue:20-27` has no labels for the seed categories (shows raw "personal", "income", …).
- **Slider PUT wipes metadata**: `onAssumptionUpdate` sends only `{key,value}` (`PlanningView.vue:211-213`); `update_plan` deletes and re-creates rows with `display_name = a.display_name or a.key`, `category = "general"`, `sensitivity = "medium"`, `description = ""` (`planning_service.py:219-227`). After the first slider move every assumption is renamed to its key and lands in the "Other" group, and sensitivity analysis loses its high/medium/low filter.
- **employee_401k_rate** fallback differs: table uses 0.15 (`planning.py:574`) while the engine used 0.10 from `build_projection_input`; `config.yaml` says 0.12. Table 401k column therefore disagrees with what the stored retirement balance was computed from.
- **Forecast year is inflated**: with no current-year W2, 2026 rsu_income = all 2026 vest events (actual + future) at today's price (`planning.py:590-597,654-661`) -> gross 299 K vs the persona's 210 K; and the 2027/2028 overrides use *unvested* future events at today's price, making those plan years spike above the engine's own trend (327 K then back to 236 K in 2029).
- `expenses_annual` and `savings_rate` are always null (`planning.py:629-630,674-675,722-723`) yet are rendered as columns and listed in `METRIC_TOOLTIPS`-less headers; the "Savings" group collapses by default so the gap is hidden.
- Actual-year wealth is 0 for 2023/2024 because `_balances_for_year` only looks at snapshots inside that year, with no carry-forward; the mortgage column instead carries today's balance back into every past year (`planning.py:579,633,678`).
- `_balance_metrics` sums **every** display_group into net_worth including credit cards/loans, but liquid NW only subtracts `home_equity` and `retirement`; groups named differently from the engine keys (e.g. "Company Stock") are just dropped.
- Engine failures are swallowed (`planning_service.py:192-194, 258-259`): a plan with no W2/balances saves with zero projections and the UI shows "No projection data available" with no reason.
- `planning.ts` uses the legacy `/api` mount and does **not** send `credentials: 'include'` nor the 401-refresh retry that `client.ts` has (`planning.ts:3-9`), so after the 4 h access token expires the table load fails until something else refreshes.
- Network dependency inside a GET: every `/plans/{id}/table` call can block on Yahoo Finance (5 s timeout) and writes to `stock_prices` (`stock_price.py:56-76`), deleting seed rows for today.
- Plan selection on load is by `is_active` but nothing ever sets `is_active=false`; every plan is "active".
- `compare` requires a plan2 table fetch but deltas for `savings_rate` would be formatted as dollars (`formatDelta` ignores PERCENT_METRICS, `PlanningView.vue:271-280`).
- Dead code: `frontend/src/stores/planning.ts`, `api.generateForecast`, `api.importData`, sensitivity/variance/compare/actuals/forecast endpoints, `engine/{cash_flow,net_worth,sensitivity,spending,variance}.py` have no importers outside the engine package.

### 6. Must never do
- Must keep `get_tenant_db` on every plan route (plans are tenant-scoped rows; no `tenant_id` column exists, isolation is purely by schema).
- `PUT /plans/{id}` must stay atomic (delete + reinsert + reproject in one commit) or a failed engine run leaves a plan with assumptions but no projections.
- Engine must remain pure/no-DB (`engine/projection.py` docstring) so tests in `backend/tests/test_engine` keep working.
- Do not change `_PLAN_METRICS` keys or the `rows[year][metric] = {value,status}` shape without updating `PlanningView` (`orderedMetrics`, `getCellValue`) and `METRIC_GROUPS`.
- `plan_assumptions` has UNIQUE(plan_id,key); `plan_projections` UNIQUE(plan_id,year).

### 7. Interactions with other pages
- Reads what Settings → Income (W2 records), Settings → Accounts (display_group, include_in_nw, is_active), Property (mortgages), RSU (vest_events, rsu_grants.symbol), 401(k)… (no, `contribution_configs` has no UI writer) produce. Editing a W2 or account group changes actual/forecast rows immediately and plan rows only after the next `PUT`.
- The import modal (income/property/rsu/retirement contexts) feeds the same tables.
- "View SQL" hands off to Database → Query tab via `sessionStorage`.
- Dashboard/other pages do not read plan data.

---

## 2. Database (`/database`)

Files: `frontend/src/views/DatabaseView.vue`, `frontend/src/composables/useSqlHighlight.ts`, `backend/app/api/schema.py` (prefix `/admin`), `backend/app/api/db_credentials.py`, `backend/app/services/db_credentials.py`. (`backend/app/api/admin.py` is a separate, hidden `/admin/tables` API used by `components/common/DataExplorer.vue` on the data pages, not by this view.)

### 1. Purpose
Let the user see their own tenant schema (ERD, row counts, column docs), peek at rows, run read-only SQL, and mint direct Postgres credentials for external tools.

### 2. Sections
1. Header "Database" + tooltip; right side "N tables · M relationships"; exit-fullscreen ×.
2. Loading / error (with Retry) states for the schema call.
3. **Left panel "Tables"**: filter input (name substring); tables grouped into Financial / Investments / Property / Planning / System by name-prefix rules (`DatabaseView.vue:256-276`); each row: name, preview icon (opens preview modal), row count, description. Click = select + pan ERD to card.
4. **Center tab bar**: Schema | Query | Access, plus tooltip.
5. **Schema tab (ERD canvas)**: zoom +/−/Fit/1:1/fullscreen controls, zoom % indicator; SVG with orthogonal FK edges (active edges glow when a table is selected), one card per table (header colour by category, preview icon, row count, columns with 🔑 PK / 🔗 FK markers, type badge, `?` nullable marker, `i` info icon with column comment). Click card = select; click again = open preview. Pan by drag/space/middle mouse; wheel = zoom or pan. Data: `GET /api/v1/admin/schema`.
6. **Query tab (SQL runner)**: textarea with a syntax-highlight overlay, ⌘Enter / Run button -> `POST /api/v1/admin/query` `{sql, limit:100}`; error box; results table with row/col counts; empty hint. Pre-filled from `sessionStorage['sql-runner-query']` on mount (set by `SqlViewerModal` on any data page) and auto-switches to this tab.
7. **Access tab**: "Create Database Credential" form (Name, Access Level read/readwrite, Expires 7/30/90/180/365/Never) -> `POST /api/v1/db-credentials/`; success notice; "Active Credentials" table (Name, Username, Access badge, Created, Expires with amber warning <14 days, Revoke -> `DELETE /api/v1/db-credentials/{id}`); static "Connection Examples" (psql, Python, DBeaver, Excel/ODBC). List loads lazily on first switch to this tab via `GET /api/v1/db-credentials/`.
8. **Credential-created modal** (Teleport): one-time display of username/password/host/port/database/schema with copy buttons, connection string, psql + Python snippets, "Download as .md", Done.
9. **Data preview modal** (Teleport): table name + total, description banner, paginated (20/page) rows via `GET /api/v1/admin/tables/{table}/preview?limit=20&offset=N`; PK/FK coloured headers with type badge and column-comment tooltip; FK cell values are buttons that call `jumpToFk` (switches the modal to the referenced table at offset 0 and sets the SQL textarea to `SELECT * FROM t WHERE col = 'v' LIMIT 20` but does not run it); Prev/Next.

### 3. Data flow
- `GET /admin/schema` (`schema.py:17-108`): SQLAlchemy inspector over `ctx.tenant_schema` + `pg_description` comments, `COUNT(*)` per table; skips `alembic_version`. Read-only.
- `GET /admin/tables/{t}/preview` (`schema.py:111-148`): table name validated against the inspector list; `SELECT * … LIMIT/OFFSET` on the tenant search_path. Read-only.
- `POST /admin/query` (`schema.py:268-332`): first word must be SELECT/WITH/EXPLAIN; blocks tokens DROP/DELETE/INSERT/UPDATE/ALTER/CREATE/TRUNCATE/GRANT/REVOKE; regex blocks `public.`/`pg_*.`/`information_schema.`/`tenant_*.` prefixes and `SET search_path`; appends `LIMIT n` if the text lacks "LIMIT"; runs `SET TRANSACTION READ ONLY` + savepoint. Read-only at the DB level (verified: `nextval()` refused).
- Also mounted but unused by the UI: `POST /admin/tables/{t}/rows`, `PUT /admin/tables/{t}/rows/{id}`, `DELETE /admin/tables/{t}/rows/{id}` (`schema.py:151-260`) — generic write endpoints on any tenant table, reachable by any authenticated user or API key.
- `GET/POST /db-credentials/`, `DELETE /db-credentials/{id}` (`db_credentials.py`): rows in `public.db_credentials` (user_id, tenant_id, pg_username, access_level, name, is_active, expires_at); `create_db_credential` (`services/db_credentials.py:27-84`) runs `CREATE ROLE … LOGIN PASSWORD`, revokes public, `ALTER ROLE SET search_path`, `GRANT USAGE/SELECT[/INSERT/UPDATE/DELETE]` + default privileges on the tenant schema; connection string host/port from `FINANCE_DB_PUBLIC_HOST/PORT` else from `database_url`. Password is never stored. Listing auto-revokes expired rows (drops the role). Revoke = `REASSIGN OWNED … TO tallied; DROP OWNED; DROP ROLE`.
- Column/table descriptions come from `COMMENT ON` statements seeded by `scripts/seed_test_data.py` (import of a schema-descriptions module at the end of the seed); 13 of 30 tables have descriptions.

### 4. Verified against seed
- `GET /api/v1/admin/schema` 200, 30 tables, 11 edges, row counts match psql; descriptions present for accounts, balance_snapshots, transactions, w2_records, rsu_grants, vest_events, stock_prices, mortgages, property_valuations, plan_versions, plan_assumptions, retirement_accounts, retirement_holdings, vehicles, import_sessions, plaid_links.
- `GET /api/v1/admin/tables/accounts/preview?limit=20&offset=0` 200, 8 rows.
- `POST /api/v1/admin/query` `SELECT 1 AS one` -> 200 `{"columns":["one"],"rows":[{"one":1}],"row_count":1,"query":"SELECT 1 AS one LIMIT 100"}`.
- `GET /api/v1/db-credentials/` 200 `[]`. (POST/DELETE not exercised per instructions.)
- Unauthenticated `POST /admin/query` 401.

### 5. Broken or suspicious
- **SQL runner reaches the public schema**: because `get_tenant_db` sets `search_path TO "<tenant>", public`, unqualified `SELECT … FROM users` returns `public.users` including `password_hash` (verified: returned claudius's argon2 hash prefix). Likewise `api_keys` (key hashes, all tenants), `db_credentials`, `tenants`, `tenant_memberships`, `audit_logs`, `api_usage_logs`, `webhook_subscriptions` (contains plaintext `secret`), `email_forwarding_addresses` are all readable. The regex at `schema.py:295` is also bypassed by quoting: `SELECT id, email FROM "public"."users"` -> 200 (verified). `"tenant_x".accounts` would bypass the same way (not testable here: only one tenant). `pg_namespace` without a prefix lists every schema name (verified).
- Generic row write endpoints (`schema.py:155-260`) exist with no UI and no extra authz; they accept any column in any tenant table.
- Preview `jumpToFk` quotes values naively into the SQL textarea (`DatabaseView.vue:613`) — only cosmetic, since it just pre-fills.
- `loadCredentials` failures are silently swallowed (`DatabaseView.vue:655-657`), so a 500 from role creation shows "No database credentials yet".
- The Access tab's "Connection Examples" hard-code port 5432 and database `tallied`.
- `categoryPatterns` ("retirement", "property", "plan_") classify by prefix; new tables (email_receipts, sync_jobs, monarch_*, simplefin_*, vehicles, asset_value_histories) fall into System.
- `GET /admin/schema` runs 30 `COUNT(*)` per load; fine at this size.

### 6. Must never do
- Query runner must stay on `get_tenant_db` and inside `SET TRANSACTION READ ONLY` (SEC-3.1); preview/rows must keep the inspector allow-list for table names (SEC-4.5).
- Any refactor must not widen `search_path`; ideally narrow it so platform tables stop resolving from tenant sessions.
- Credential creation must keep: revoke public, `ALTER ROLE … SET search_path`, grants limited to the tenant schema, password returned once and never persisted. Expiry enforcement lives in the list endpoint (there is no scheduler) — keep that or add one.
- `db_credentials` rows must stay keyed by (user_id, tenant_id); list filters by both, delete by user only.

### 7. Interactions
- Entry point from every data page's `SqlViewerModal` ("Run in SQL Runner" -> sessionStorage -> `/database`).
- `DataExplorer.vue` (data pages) and Admin → Tenant detail both compute row counts from the same schema; DataExplorer uses the hidden `/admin/tables` API in `admin.py`.
- Admin → User detail shows `db_credential_count` from `public.db_credentials`.

---

## 3. API (`/developer`)

Files: `frontend/src/views/ApiView.vue`, `backend/app/api/api_keys.py`, `backend/app/api/webhooks.py`, `backend/app/services/webhook_service.py`, `backend/app/models/{api_key,webhook,api_usage}.py`, `backend/app/middleware/{usage_logger,rate_limit}.py`, Scalar at `/api/v1/scalar`.

### 1. Purpose
Give the user programmatic access: mint/revoke API keys, see usage, register webhooks, and open the OpenAPI reference.

### 2. Sections
1. Header "API" + tooltip. Tab bar: Keys & Usage | Webhooks | API Reference (all three tabs are mounted with `v-show`; all loaders run on mount).
2. **Keys & Usage**
   - "API Key Created" banner (one-time full key, Copy, Dismiss) after `POST /api/v1/api-keys/` `{name, permissions}`.
   - Usage stat tiles: Today / Last Hour / All Time requests, Avg Latency — `GET /api/v1/api-keys/usage/summary` (tenant-wide, cookie + key traffic).
   - **API Keys card**: "New Key" toggles form (Name, Permissions read/write/admin, Create). List rows: name, badge (permissions or "revoked"), "N req/24h" badge from `per_key`, `key_prefix...`, Created, Last used, Revoke -> `DELETE /api/v1/api-keys/{id}`. Empty state.
   - **Most-Used Endpoints** table (method/path/count, top 10 all-time) from the same summary.
   - **Quick Start** (curl / Python / JavaScript hitting `/api/v1/snapshot` with `X-API-Key`), **Base URL** card, **Rate Limits** card (1,000/h sliding window, `X-RateLimit-*` headers, 429 + Retry-After).
3. **Webhooks**
   - "Webhook Created" banner (one-time signing secret) after `POST /api/v1/webhooks/` `{url, events[]}`.
   - **Webhook Subscriptions card**: "New Webhook" form (Payload URL, event checkboxes from the hard-coded list transaction.created / balance.updated / import.completed / account.created). List rows: url, active/inactive badge, "N failures" badge, event chips, Created, Last delivery; actions Test (`POST /webhooks/{id}/test`, result shown inline for 4 s), Pause/Resume (`PUT /webhooks/{id}` `{is_active}`; resume resets failure_count), Delete (`DELETE /webhooks/{id}`).
   - Sidebar: Event Types list, "Verifying Signatures" Python snippet (`X-Webhook-Signature` HMAC-SHA256 hex, `X-Webhook-Event`), Retry Policy text (deactivated after 10 consecutive failures).
4. **API Reference**: card with "Open API Reference" link to `/api/v1/scalar?dark=0|1` (new tab) and the openapi.json path.

### 3. Data flow
- `public.api_keys`: `POST` generates `tld_<token_urlsafe(32)>`, stores HMAC-SHA256(pepper, key) in `key_hash`, first 12 chars in `key_prefix`, `permissions` string. `DELETE` sets `is_active=false` (filter user_id only). `GET` filters user_id + tenant_id.
- Auth via key: `_resolve_api_key` (`dependencies.py:51-96`) looks up the hash, applies the in-memory rate limiter (`apikey:<id>`), updates `last_used`, returns the key's tenant. **`permissions` is never checked anywhere** — a "read" key can call every write route.
- `public.api_usage_logs`: written by `UsageLoggerMiddleware` for every `/api/v1/*` request with identifiable user+tenant (cookie or key). Summary endpoint aggregates by tenant; per-key stats by `api_key_id`.
- `public.webhook_subscriptions`: url, comma-joined events, plaintext `secret`, is_active, failure_count, last_delivery. `deliver_webhook` (`webhook_service.py:26-73`) exists but **has no callers** anywhere in `backend/app` — only `send_test_event` is reachable. Real events are never emitted.
- Scalar page served inline by `main.py` with `data-url="./openapi.json"`; loads `@scalar/api-reference` from jsdelivr.

### 4. Verified against seed
- `GET /api/v1/api-keys/` 200 `[]`; `GET /api/v1/api-keys/usage/summary` 200 (`total_requests_all_time: 188`, top endpoints `/auth/me` 22 …, `per_key: []`).
- `GET /api/v1/webhooks/` 200 `[]`.
- `GET /api/v1/scalar` 200 HTML; `GET /api/v1/openapi.json` 200 (112 KB).
- Key/webhook creation not exercised per instructions.

### 5. Broken or suspicious
- Webhooks are inert in production: no code path calls `deliver_webhook` (`grep deliver_webhook backend/app` -> definition only). The page promises four event types that never fire.
- `permissions` (read/write/admin) is cosmetic; no enforcement in `dependencies.py` or any route.
- Usage tiles conflate browser-session traffic with API-key traffic (`usage_logger.py:67-76` logs cookie requests; `api_keys.py:217-254` aggregates by tenant), so "Today 188 requests" appears with zero keys.
- Rate limiter is per-process in-memory (`rate_limit.py`), so multi-worker deployments enforce N× the limit; cookie sessions are not rate-limited at all (only header middleware with an IP key for display).
- Revoke/delete check `user_id` but not `tenant_id` (`api_keys.py:104-109`), acceptable for single-owner tenants.
- `ApiView` `fetch` calls do not handle non-OK responses (e.g. `createKey` on 400 sets `createdKey = undefined` silently).
- Webhook `url` is accepted as any string (`CreateWebhookRequest.url: str`, `HttpUrl` imported but unused, `webhooks.py:3,16`) — SSRF surface for the test endpoint.
- Dead API on the legacy mount: `/api/api-keys/*` etc. are reachable without usage logging or rate-limit headers.

### 6. Must never do
- Keys must stay hashed with the pepper (`ApiKey.hash_key`); changing the algorithm invalidates all keys (comment at `api_key.py:35-39`).
- Full key and webhook secret must only be returned on create.
- API-key auth must keep resolving to the key's own `tenant_id` (never the user's default tenant) and must refuse inactive tenants.
- Listing must stay filtered by user_id + tenant_id.

### 7. Interactions
- Admin → User detail displays `api_key_count`.
- Any route in the app is callable with a key; the Quick Start targets `/api/v1/snapshot` (Dashboard data).

---

## 4. Settings (`/settings`)

Files: `frontend/src/views/SettingsView.vue`; backend `api/accounts.py`, `api/income.py`, `api/plaid_routes.py`, `api/simplefin_routes.py`, `api/monarch_routes.py`, `api/email_forwarding.py`, `api/email_import.py`, `api/import_data.py` (log), `services/sync_scheduler.py`.

### 1. Purpose
Maintain the reference data that every other page depends on (accounts, W2s), connect external data feeds, and review what was imported.

### 2. Sections (tabs: Accounts | Income | Plaid | SimpleFIN | Email | Import; a Monarch tab exists in code but is removed from `tabs`, `SettingsView.vue:14-23`). All loaders run on mount regardless of tab.

**Accounts tab**
- "Add Account" toggles a form: ID (optional), Name, Institution, Type (cash, investment_401k, investment_stock, real_estate, loan_mortgage, loan_student, credit_card), Display Group (Cash, Investments, Retirement, Home Equity, Credit Cards, Other Loans), Include in Net Worth, Notes -> `POST /api/v1/accounts/`.
- Table: Name, Institution, Type, Group, Source badge (derived from id prefix: monarch-/simplefin-/plaid-/manual), Active, Balance (latest snapshot), Edit (inline row -> `PUT /api/v1/accounts/{id}`), Delete (modal: `GET /api/v1/accounts/{id}/related-counts` lists balance_snapshots/transactions/mortgages/property_valuations/property_value_history counts; cascade checkbox; `DELETE /api/v1/accounts/{id}?cascade=true`). Data: `GET /api/v1/accounts/`.

**Income tab**
- "Add W2" form: Tax Year, Gross Pay, Base Salary, RSU Income, Federal Tax, State Tax, Pre-tax 401k, Roth 401k -> `POST /api/v1/income/w2` (upsert by tax_year).
- Table of W2 records (same 8 columns) with inline Edit -> also `POST /api/v1/income/w2`. Data: `GET /api/v1/income/history` (`w2_records` part; the `rsu_grants` part is ignored).

**Plaid tab**
- "Connect Account" -> `GET /api/v1/plaid/link-token`, then `window.Plaid.create(...)` (Plaid Link JS must be present on the page), on success `POST /api/v1/plaid/exchange` then `POST /api/v1/plaid/sync`. Status line.
- "Connected Institutions" table (Institution, Connected date, Last Synced shown as "Yes/Never" from `link.cursor`) with "Sync All" -> `POST /api/v1/plaid/sync`. Data: `GET /api/v1/plaid/links`.

**SimpleFIN tab**
- Not connected: textarea for a setup token + Connect -> `POST /api/v1/simplefin/connect`.
- Connected: last-synced line; Sync All (`POST /api/v1/simplefin/sync` 202 then polls `GET /api/v1/simplefin/sync/status` every 2 s up to 10 min), Refresh credentials (inline textarea -> `POST /api/v1/simplefin/refresh-credentials`), Disconnect (`DELETE /api/v1/simplefin/disconnect`).
- "Account Sync Configuration" table (Account, Institution, Balances checkbox, Transactions checkbox -> `PUT /api/v1/simplefin/accounts/{config_id}`). Data: `GET /api/v1/simplefin/status`, `GET /api/v1/simplefin/accounts`.

**Email tab**
- Instructions card showing `receipts@<current host's registrable domain>` (computed client-side from `window.location.hostname`, `SettingsView.vue:343-345`; on localhost it shows `receipts@localhost`).
- "Forwarding Addresses": add input -> `POST /api/v1/email-forwarding`; list with Remove -> `DELETE /api/v1/email-forwarding/{id}`. Data `GET /api/v1/email-forwarding`.
- "Recent Receipts" table (Date, From, Subject, Merchant, Amount, Status parsed/failed/other) from `GET /api/v1/email-import/receipts?limit=20`.

**Import tab**
- "Import History" table (Date, Source, Capture Mode, Status, Records Created, Error) from `api.getImportLog()` = `GET /api/v1/import/log`.

**Monarch (hidden)**: full connect (email/password/MFA or session token), refresh-credentials, Sync All (balances then 202 job + polling), disconnect, per-account toggles; routes `/api/v1/monarch/*` still mounted and functional.

### 3. Data flow (per feature)
- Accounts: tenant `accounts` (id string PK, name, institution, account_type, display_group, include_in_nw, is_active, opened/closed, notes); balances from `balance_snapshots`. Cascade delete removes balance_snapshots, transactions, mortgages, property_valuations, property_value_histories for that account and nulls `local_account_id` in monarch/simplefin configs (`accounts.py:184-236`). Accounts are populated by the seed, by the sync providers (prefixed ids), by the import modal (property creates an account for the mortgage), and manually here.
- Income: tenant `w2_records` (UNIQUE tax_year). Populated by seed, this tab, and the import modal (income context).
- **Plaid**: reachable in UI, but not configured on this machine. Stores `plaid_links` (access_token plaintext, cursor, institution). `POST /plaid/sync` is synchronous (no job row) and writes `transactions` (ids `plaid-<txid>`, amount sign flipped, category from personal_finance_category) and `accounts`; `POST /plaid/sync-balances` writes `balance_snapshots`. **Not part of the scheduler** (`ALL_PROVIDERS` excludes it); only manual sync.
- **SimpleFIN**: reachable in UI. Stores `simplefin_links` (one per tenant: `access_url` plaintext, last_synced_at) and `simplefin_account_configs` (per upstream account, sync_balances default true, sync_transactions default false, local_account_id). Sync runs via `sync_scheduler._sync_tenant_simplefin` (`sync_scheduler.py:403-567`): one fetch of the access URL, then for configured accounts create/update `accounts` (`simplefin-<id>`), add a `balance_snapshots` row for today (source simplefin) when sync_balances, and upsert ~45 days of `transactions` (`source='simplefin'`, category left blank) when sync_transactions. Job lifecycle in tenant `sync_jobs` (provider, status running/succeeded/failed, trigger manual/scheduled, counts, error; partial unique index enforces one running job per provider). Manual sync: `create_job_row` then either `asyncio.create_task(run_sync_with_job)` in-process (APP_ROLE unset, which is this machine) or `NOTIFY tallied_sync` to the scheduler process (APP_ROLE=web).
- **Monarch**: not reachable (tab hidden) but routes work. Stores `monarch_links` (email + session token plaintext) and `monarch_account_configs`; sync fn registered but excluded from the scheduler loop.
- **Scheduler** (`services/sync_scheduler.py`): started in lifespan unless `APP_ROLE in (web, scheduler)` (`main.py:92-111`); takes a Postgres advisory lock so one worker runs; immediately runs `sync_all_tenants()` then every 12 h; for every `tenant_%` schema and each provider in `ALL_PROVIDERS == ("simplefin",)` with a link row, creates a `scheduled` job and runs it. Also `reap_stuck_jobs` at boot (running > 15 min -> failed), `mark_running_jobs_failed` at shutdown, `claim_orphan_jobs`, and a LISTEN loop on `tallied_sync`.
- **Email forwarding**: `public.email_forwarding_addresses` (user_id, tenant_id, email, is_active). Inbound path `POST /email-import/inbound` (no cookie auth; requires `X-Email-Webhook-Secret` == `FINANCE_EMAIL_WEBHOOK_SECRET`, unset locally so always 401) resolves `forwarded_by` to a tenant, inserts tenant `email_receipts`, calls `parse_receipt_with_ai` (Anthropic), and `create_transaction_from_receipt` -> `transactions`. Receipts list reads tenant `email_receipts`.
- **Import log**: tenant `import_logs` (source, capture_mode, status, records_created, error_message, created_at). Written by `import_unified.confirm_import` (`source="unified_import", capture_mode="pdf"`) and by the legacy `/import-legacy/*` service.

### 4. Verified against seed
- `GET /api/v1/accounts/` 200, 8 accounts with balances (balance_date 2026-03-01), `source: "manual"`.
- `GET /api/v1/income/history` 200, 3 W2s (2023-2025) + 8 grants.
- `GET /api/v1/plaid/links` 200 `[]`; `GET /api/v1/plaid/link-token` **500 Internal Server Error** (no Plaid credentials; exception is not a `plaid.ApiException`, `plaid_routes.py:113-116`).
- `GET /api/v1/simplefin/status` 200 `{"connected":false}`; `/simplefin/accounts` 200 `[]`; `/simplefin/sync/status` 200 `{"job_id":null,"status":"none"}`.
- `GET /api/v1/monarch/status` 200 `{"connected":false}`; `/monarch/accounts` 200 `[]`; `/monarch/sync/status` 200 none.
- `GET /api/v1/email-forwarding` 200 `[]` (note: `/email-forwarding/` with slash is 307); `GET /api/v1/email-import/receipts?limit=20` 200 `[]`.
- `GET /api/v1/import/log` **404 `{"detail":"Session not found"}`** — see §5. `GET /api/v1/import-legacy/log` 200 `[]`.
- `sync_jobs` empty; scheduler ran at startup but no tenant has a SimpleFIN link, so no job rows.

### 5. Broken or suspicious
- **Import History tab is permanently empty**: `client.ts:139` calls `/import/log`, but the legacy import router moved to prefix `/import-legacy` (`import_data.py:19`), so the request now matches `import_unified`'s `GET /import/{session_id}` with `session_id="log"` -> 404; `loadImportLog` swallows the error and renders "No import logs found" even though `confirm_import` writes rows.
- Plaid "Connect Account" expects `window.Plaid` (Plaid Link script) — nothing in `frontend/index.html`/App loads it; also `link-token` throws 500 when unconfigured.
- Plaid "Last Synced" column shows `link.cursor ? 'Yes' : 'Never'` but the API returns `has_cursor`, not `cursor` (`SettingsView.vue:1189` vs `plaid_routes.py:266-274`) -> always "Never".
- `email_forwarding.py:51-55` duplicate check is global (no user/tenant filter) so an address registered by one user blocks every other user with a 409, and the error message reveals that the address exists.
- Settings "Email" instructions compute `receipts@<domain>` from the browser hostname; the backend has no notion of the inbound address.
- Email inbound parsing requires Anthropic; with no key `parse_receipt_with_ai` fails -> receipts land as `failed` (not probed; endpoint rejects without the webhook secret anyway).
- W2 inline edit posts `editW2Form` which is the trimmed 8-field form, so fields not on the form (social_security, medicare, cafeteria_125, transit, employer_health, w2_wages) are preserved only because `exclude_unset` on the backend ignores absent keys — but the form sends explicit `null` for empty inputs, which **overwrites** those 8 fields with NULL when the user clears a box; fine, but note `gross_pay=0` is serialised as null by `_serialize_w2` (`income.py:110`, `if w.gross_pay` truthiness) so zeros vanish on reload.
- Account edit UI cannot change `is_active` (`AccountUpdate` is sent without it); the Active column is read-only. Deactivated accounts can only come from sync providers/DB.
- Settings `tabs` typed `Tab` still includes `'monarch'`; ~250 lines of Monarch script/template are dead until re-enabled.
- `GET /api/v1/plaid/links` and `/email-forwarding` are called on every Settings mount even when not needed; harmless.
- SimpleFIN `access_url` and Plaid `access_token`, Monarch `token` are stored in plaintext in tenant tables — and are readable through the Database page SQL runner.
- Scheduler log messages still say "Monarch sync scheduler" though only SimpleFIN runs (`sync_scheduler.py:814-847`).
- `sync_all_tenants` runs synchronously inside the web process on startup when `APP_ROLE` is unset; a slow SimpleFIN call blocks the event loop's task but not requests.

### 6. Must never do
- Keep account deletion two-phase (409 with counts unless `cascade=true`) and keep nulling `local_account_id` in provider configs rather than deleting them.
- W2 `tax_year` must stay unique; `POST /income/w2` is an upsert and the only write path the UI uses.
- One `simplefin_links` / `monarch_links` row per tenant; one running `sync_jobs` row per provider (partial unique index).
- Provider-created accounts must keep their id prefixes (`simplefin-`, `monarch-`, `plaid-`) — the Source badge and `_account_source` depend on them.
- Sync must always land a job in a terminal state (`run_sync_with_job` contract), and the scheduler must only run under the advisory lock.
- `email-import/inbound` must keep the shared-secret check and must resolve the tenant from `forwarded_by` only.

### 7. Interactions
- Accounts (display_group/include_in_nw/is_active) drive Dashboard liquidity layers, Cash, Planning engine inputs and actual-year rows, and the Spending account-type filter.
- W2 edits drive Income page tables and Planning actuals/forecast/engine salary.
- SimpleFIN/Plaid syncs populate `transactions` (Spending/Cash) and `balance_snapshots` (Dashboard trend, Cash, Planning).
- Import log rows are written by the Import modal's confirm step (but never displayed, see §5).

---

## 5. Admin Portal (`/admin-portal`, `/admin-portal/users/:id`, `/admin-portal/tenants/:id`)

Files: `frontend/src/views/AdminPortalView.vue`, `AdminUserDetailView.vue`, `AdminTenantDetailView.vue`; `backend/app/api/platform_admin.py` (prefix `/platform`), `backend/app/api/tenants.py`, `backend/app/services/tenant_service.py`, `backend/app/services/audit_service.py`. (`backend/app/api/admin.py` and `frontend/src/api/admin.ts` are *not* the admin portal; `admin.ts` is unused.)

### 1. Purpose
Let a platform admin approve Google-SSO sign-ups, toggle user active/admin flags, manage tenants, and see platform stats.

### 2. Sections
**AdminPortalView**
1. Access Denied card when `auth.user.is_admin` is false (client-side only).
2. Tabs: Pending Users (badge = count), All Users, Tenants, Stats. On mount loads users if admin; other tabs load lazily on first switch.
3. **Pending Users**: card per `status === 'pending_approval'` user (name, email, provider, signed-up date) with Approve -> `POST /api/v1/platform/users/{id}/approve`, and Deactivate/Activate -> `PUT /api/v1/platform/users/{id}` `{is_active}`.
4. **All Users** table: Email (link to detail), Name, Status, Provider, Admin, Tenant chips, Last Login, Actions (Activate/Deactivate, Make/Remove Admin -> `PUT /platform/users/{id}`). Data `GET /api/v1/platform/users`.
5. **Tenants** table: Name (link), Owner (name/email), Slug, Schema, Active, Members, Created, Activate/Deactivate -> `PUT /platform/tenants/{id}` `{is_active}`. Data `GET /api/v1/platform/tenants`.
6. **Stats** tiles: total_users, active_users, total_tenants, active_tenants from `GET /api/v1/platform/stats`.

**AdminUserDetailView** (`GET /api/v1/platform/users/{id}`): back link; header with Approve (if pending), Make/Remove Admin, Activate/Deactivate; "User Info" grid (email, name, provider, status, admin, active, created, last login); tiles API Keys count / DB Credentials count; "Tenant Memberships" table (tenant link, slug, role, default dot).

**AdminTenantDetailView** (`GET /api/v1/platform/tenants/{id}`): back link; header + Activate/Deactivate; "Tenant Info" (name, slug, schema, active, created, member count); "Members" table (email link, name, role, default); "Schema Stats" table of per-table row counts + total.

### 3. Data flow
- All routes use `require_admin` + `get_db` (public schema). Reads `users`, `tenants`, `tenant_memberships`, `api_keys`, `db_credentials`; tenant detail runs `COUNT(*)` on every table in `information_schema.tables` for that schema.
- Approve (`platform_admin.py:122-179`): sets `status='active'`, creates a `tenants` row with generated schema name, `create_tenant_schema()` (CREATE SCHEMA + `Base.metadata.create_all` for non-platform tables), owner membership, and two `audit_logs` events. Update user writes `audit_logs` `admin_action`. Tenant update writes none.
- Also mounted but without UI: `POST/DELETE /platform/users/{uid}/tenants/{tid}` (membership add as "viewer"/remove).
- Users are created only by Google callback (`status=pending_approval`), dev `seed-users`, or the seed script. There is no "create user" UI.

### 4. Verified against seed
- As claudius (non-admin): `GET /api/v1/platform/users|tenants|stats|users/1|tenants/1` all **403 `{"detail":"Admin access required"}`**. Unauthenticated: 401.
- No admin user exists in the local DB (`users`: only claudius, is_admin=false); `POST /auth/seed-users` would create `admin@tallied.dev` but was not run (persistent write). Admin happy paths are therefore code-verified only.

### 5. Broken or suspicious
- `require_admin` opens its own `SessionLocal()` per request (`dependencies.py:98-108`); fine but duplicative.
- Deactivating a tenant does not invalidate existing JWTs; `get_tenant_context` from a cookie does not check `tenants.is_active` (only the API-key path does, `dependencies.py:77-78`). A user keeps access until the 4 h token expires and `_resolve_tenant` picks another active tenant on refresh (or errors with IndexError at `auth.py:155` if none remain).
- Deactivating a user (`is_active=false`) is only enforced at dev login and refresh (`auth.py:305,394`); the cookie path in `get_tenant_context` never re-checks `is_active`.
- Approve creates a tenant even if the user already has memberships (no guard) — only reachable for `pending_approval` users so benign today.
- Tenant detail `COUNT(*)` loop uses f-string schema/table names from `information_schema` (safe source) but runs 30+ queries.
- Toggle buttons in AdminPortalView re-fetch the whole user list after each action; no optimistic update, no confirmation dialogs for destructive toggles.
- `getattr(u, "status", "active")` fallbacks suggest `status` was added late; DB has the column now.

### 6. Must never do
- Every `/platform/*` route must keep `require_admin`; the frontend check is cosmetic.
- Approval must remain the only path that creates a tenant for a pending Google user (Google callback never auto-creates; `_resolve_tenant` auto-create only runs for active users at login/refresh).
- Schema creation must go through `create_tenant_schema` so new tenants get all non-platform tables; `PLATFORM_TABLES` (`tenant_service.py:7`) must list every public-schema model or it will be created inside tenant schemas.
- `audit_logs` entries for approve/update must be kept.

### 7. Interactions
- Pending Approval page polls `/auth/me` and unblocks once approval created the tenant.
- Tenant switcher (`components/common/TenantSwitcher.vue`, visible when a user has >1 tenant) uses memberships that admins can add via the un-UI'd membership endpoints or `POST /tenants/`.
- Counts shown here come from the API page (keys) and Database page (credentials).

---

## 6. Guide (`/guide`)

File: `frontend/src/views/GuideView.vue` (static, no API calls).

### 1. Purpose
Static orientation page describing what the app does, how pages are grouped, where data comes from, and the import workflow.

### 2. Sections
1. Header "Tallied Guide".
2. "The Big Picture" prose (retirement question; data sources Plaid / AI uploads / Yahoo / manual; SQL transparency).
3. "Navigation": six nav groups with emoji and page lists (Overview, Money, Investments, Property, Planning, Platform with note "Admin Portal is admin-only").
4. "Platform Features": Multi-tenancy, Google SSO, API Keys, SQL Transparency, Import Workflow, API Reference, Admin Portal, Database Viewer.
5. "How Wealth Is Organized": four liquidity layers (Cash, Investments, Home Equity, Retirement) with badges.
6. "Pages": expandable accordion per page with a description (toggle state in a reactive map).
7. "How Data Gets In": Plaid, Document Import, E-Trade, Yahoo Finance, Manual Entry, each with "feeds" list.
8. "Import Workflow": four numbered steps.
9. "Getting Started" checklist.

### 3. Data flow
None; all content is hard-coded arrays in the `<script setup>` (`GuideView.vue:10-226`).

### 4. Verified
No endpoints. Route `/guide` requires auth.

### 5. Broken or suspicious
- Content is stale relative to the code: says data flows from Plaid and never mentions SimpleFIN (the only scheduled provider) or email receipts; Settings description omits SimpleFIN/Email tabs; Planning description promises "Sensitivity analysis shows which assumptions matter most" (no UI); API description says "Link to the interactive Scalar-powered API reference at /developer" (it is at `/api/v1/scalar`); "Import Workflow" lists PDFs only though XLSX/CSV are accepted.
- Emoji icons render differently across platforms; no `InfoTooltip`s here.

### 6. Must never do
Nothing functional; keep the route public-to-authenticated only (it is behind the auth guard today).

### 7. Interactions
Links/explanations only; no cross-page state.

---

## 7. Login (`/login`) and Pending Approval (`/pending-approval`)

Files: `frontend/src/views/LoginView.vue`, `frontend/src/views/PendingApprovalView.vue`, `frontend/src/stores/auth.ts`, `backend/app/api/auth.py`.

### 1. Purpose
Authenticate (Google SSO in prod, email/password in dev), issue the tenant-scoped JWT cookie, and hold new SSO users in a waiting room until an admin approves them.

### 2. Sections
**Login**
1. On mount: `auth.checkAuth()` (`GET /api/v1/auth/me`, with a `POST /api/v1/auth/refresh` fallback) — redirects to `/` if already authenticated; then `GET /api/v1/auth/config` -> `{dev_mode, google_sso}` decides which controls to show.
2. "Sign in with Google" button (`window.location = /api/v1/auth/google/login`) when `google_sso`.
3. "or" divider when both.
4. Dev form (Email, Password, Sign in) -> `POST /api/v1/auth/login` via the store; error box; hint line "claudius@tallied.dev / demo123 · admin account also available".
5. "No authentication methods configured." fallback.

**Pending Approval**
1. On mount `GET /auth/me`: if `current_tenant` present -> `/`; if unauthenticated -> `/login`.
2. Card: clock icon, "Your account is being reviewed", user name/email, "Check status" button (re-GETs `/auth/me`; "approved! Redirecting…" or "still being reviewed"), "Sign out" (`POST /auth/logout` then `/login`).

### 3. Data flow
- `POST /auth/login` (dev only; 403 otherwise): verifies argon2 (migrates legacy SHA-256), requires `is_active`, `_resolve_tenant` (auto-creates a tenant + schema if the user has no membership), sets `last_login`, `audit_logs` login/login_failed, sets cookies `tallied_token` (4 h, httpOnly, samesite=lax, secure when not dev) and `tallied_refresh` (30 d, path `/api/v1/auth/refresh`).
- `GET /auth/google/login` -> authlib redirect; `GET /auth/google/callback`: find/create user (`status='pending_approval'` for new users, `auth_provider='google'`); pending users get a tenant-less JWT and a 302 to `/pending-approval`; active users get the full token + refresh and a 302 to `/` (or `cors_origins[0]` in dev).
- `POST /auth/refresh`: rotates both tokens; `GET /auth/me`: decodes cookie, returns user + current_tenant (from the JWT's tenant_id) + tenants; `POST /auth/select-tenant`: membership check, re-issues the JWT; `POST /auth/logout`: clears cookies + audit; `POST /auth/seed-users` (dev only, hidden): creates claudius and the FINANCE_DEV_USER admin.
- Tables: `public.users`, `tenants`, `tenant_memberships`, `audit_logs`.

### 4. Verified
- `POST /api/v1/auth/login` 200 with user payload, cookies set; `GET /api/v1/auth/me` 200 authenticated; `GET /api/v1/auth/config` 200 `{"dev_mode":true,"google_sso":false}`; unauthenticated `GET /auth/me` 200 `{"user":null,"authenticated":false}`.
- Google flow untestable locally (no client id -> 501 by code).
- Pending flow untestable (no pending user).

### 5. Broken or suspicious
- Login hint text advertises a demo password in the UI whenever dev mode is on (`LoginView.vue:125-129`).
- `_resolve_tenant` crashes with IndexError if all of a user's tenants are inactive (`auth.py:155`); refresh then 500s instead of 401.
- `get_tenant_context` trusts the JWT's tenant claims for 4 h with no DB check of user `is_active` or tenant `is_active` (see Admin §5).
- Pending-approval JWT has no `tenant_id`; `get_tenant_context` raises 401 "Invalid token" (KeyError) for any data route, which the client treats as "try refresh", and `refresh` for a pending user would call `_resolve_tenant` and **auto-create a tenant** (`auth.py:398`) — bypassing approval if the pending user ever obtains a refresh cookie (the callback does not set one, so not reachable today, but fragile).
- `auth.ts.login` does not use `checkAuth` after login; `selectTenant` reloads the page.
- `seed-users` endpoint is unauthenticated (dev only).

### 6. Must never do
- Dev login must stay behind `settings.dev_mode`, and lifespan must keep refusing default secrets outside dev (`main.py:53-66`).
- JWT must always carry `tenant_id` + `tenant_schema`; those are what every tenant route trusts.
- New Google users must start `pending_approval` and must not get a tenant until approved.
- Refresh cookie path must stay `/api/v1/auth/refresh`; logout must clear both cookies.

### 7. Interactions
- Router guard everywhere; `TenantSwitcher` uses `select-tenant`; Admin Portal approve flips the Pending page.

---

## 8. Unified Import modal (launched from Income, RSU, 401(k), Property)

Files: `frontend/src/components/import/ImportModal.vue` (mounted once in `App.vue:279`), `frontend/src/composables/useImportModal.ts`, `backend/app/api/import_unified.py` (prefix `/import`), model `ImportSession`, `ImportLog`.

Launch sites: `IncomeView.vue:573` (context income), `RSUView.vue:244` (rsu), `RetirementView.vue:441` (retirement), `PropertyView.vue:663` (property); each passes `onComplete` = that page's refresh, invoked by `closeImport()` whenever the modal closes (even on cancel). No page uses the `general` context.

### 1. Purpose
Turn a PDF/XLSX/CSV into reviewed, accepted database changes (W2, mortgage, 401(k) account+holdings+snapshot, RSU grants+vests) with an AI chat for corrections.

### 2. Sections / steps
1. Header: "Import Data", context label (Income / 401(k) / Retirement / Property / Mortgage / RSU Holdings / Financial Document), "File i of n", close ×.
2. **Upload step**: drop zone (accept .pdf,.xlsx,.xls,.csv, multiple), queued file list with Remove, guidance box from `GET /api/v1/import/config/{context}` (guidance + examples), "Process N files".
3. **Processing step**: spinner "Analyzing {file}…" while `POST /api/v1/import/upload` (multipart `file`, `context`) runs. On success the modal immediately also calls `POST /import/{session}/chat` with a canned "Briefly summarize…" message to seed the chat.
4. **Review step** (left): AI summary box; "Expected data not found" amber list (`missing_fields`); Review | SQL Preview toggle; "Everything is up to date" green state when no proposed changes; Review view = "Database Changes" header with Summary/Show details toggle, "Operations" summary lines, one card per proposed change (checkbox accepted by default, table name, New Record/Update badge with record label or tax year, per-field current → new with (manual) marker), collapsible "View SQL" with client-generated UPDATE/INSERT text; SQL Preview view = per-table before/after table + the same generated SQL.
   Right panel "Ask AI": message list (assistant markdown via `marked`), Accept button on the last message with an `action` -> `POST /import/{session}/apply-action` then re-`GET /import/{session}`; input + send -> `POST /import/{session}/chat`.
5. Footer (review): "k of n changes selected", Skip File / Cancel, "Accept Selected Changes" -> `PUT /import/{session}/accept` then `POST /import/{session}/confirm`; moves to next file or Done. "Close" when nothing to apply.
6. **Done step**: "Import Complete — N changes applied", Done.

### 3. Data flow
- `POST /import/upload` (`import_unified.py:177-302`): requires `settings.anthropic_api_key` (500 "Anthropic API key not configured" otherwise, **before** any row is written); creates tenant `import_sessions` row (12-char id, status processing, context, filename, file_type); sends the PDF as a base64 document block, XLSX as openpyxl-dumped text, else raw text to `claude-sonnet-4-20250514` with the context prompt (`CONTEXT_CONFIG`); parses JSON findings; `_build_proposed_changes` diffs against current `w2_records` (by tax_year), latest `mortgages`, latest `retirement_accounts`, or `rsu_grants` by grant_number; stores findings/proposed/missing/ai_summary; status `review`. Errors set status `error` and return 502/500.
- `GET /import/{id}`, `PUT /import/{id}/accept` (stores accepted ids), `POST /import/{id}/chat` (Anthropic; also requires key; may return an `action` dict add_field/update_field which is stored in `chat_messages`), `POST /import/{id}/apply-action` (mutates `proposed_changes` JSON), `GET /import/config/{context}` (static).
- `POST /import/{id}/confirm` (`import_unified.py:339-415`): status must be `review`; applies accepted changes: `w2_records` upsert by tax_year; `mortgages` latest row updated (creates an `accounts` row + mortgage if none); `retirement_accounts` fields (+ `retirement_snapshots` upsert by statement end date, `retirement_holdings` replaced); `rsu_grants` + `vest_events` upsert; writes an `import_logs` row (source unified_import, capture_mode pdf, status confirmed, records_created) and an `audit_logs` `data_import` event; session -> confirmed.
- Legacy `/import-legacy/*` (paste/screenshot flow via `services/import_service.py`) still mounted, hidden from docs, no UI.

### 4. Verified against seed
- `GET /api/v1/import/config/income` 200 (guidance + 5 expected fields); `/config/general` 200.
- `POST /api/v1/import/upload` with a dummy text file and `context=income` -> **500 `{"detail":"Anthropic API key not configured"}`**; `import_sessions` count stayed 0 (check happens before the insert). In the modal this surfaces as the review step with the summary box reading `Error: {"detail":"Anthropic API key not configured"}`, no changes, and a "Close" button (`ImportModal.vue:132-135`).
- `GET /api/v1/import/log` 404 (route shadowing, see Settings §5).
- Chat/accept/confirm not exercisable without a session.

### 5. Broken or suspicious
- Hard dependency on Anthropic for every step including the canned summary chat; no key means the feature is dead with a raw JSON error in the UI.
- Route order: `GET /import/{session_id}` is declared before `GET /import/config/{context}` but FastAPI matches `/import/config/income` to the two-segment route correctly; `/import/log` however has one segment and is captured as a session id.
- `confirm_import` accepts all changes when `accepted_change_ids` is empty (`import_unified.py:348-349`), so unchecking every box and calling confirm would apply everything — the UI disables the button at 0 selected, so only an API caller hits this.
- `upload` reads the whole file into memory and sends up to 16 k output tokens; no size limit on the upload.
- Mortgage/retirement apply targets "the most recently updated row" (`ORDER BY updated_at DESC LIMIT 1`) regardless of address/plan — multi-property/multi-401k tenants would overwrite the wrong record. The client-side SQL preview mirrors this with `WHERE id = (SELECT id … ORDER BY updated_at DESC LIMIT 1)`.
- The "SQL Preview" is synthesised in the browser (`ImportModal.vue:257-309`) and is not what the backend executes (backend uses ORM upserts); it also wraps every string in single quotes without escaping.
- Closing the modal at any step fires `onComplete` (page refresh) even when nothing was imported (`useImportModal.ts:16-22`).
- `chat` seeds happen even if `ai_summary` is an error string (any truthy summary).
- `_strip_html`/`marked` render assistant markdown with `v-html` (`ImportModal.vue:607`) — model output is injected as HTML without sanitisation.
- Session rows are never cleaned up; a failed upload after the insert leaves `status='error'` rows.

### 6. Must never do
- Keep the upload gated on the API key before creating the session row, and keep sessions tenant-scoped (`get_tenant_db`; `import_sessions` is a tenant table).
- Confirm must stay idempotent-ish: only `review` sessions can be confirmed; one `import_logs` + one audit event per confirm.
- Keep `W2_FIELDS`/`MORTGAGE_FIELDS` mapping as the only way AI findings reach columns (no arbitrary column writes from the model); `TEXT_DB_FIELDS` governs string vs Decimal.
- Never return ORM attributes after `db.commit()` in these handlers (search_path reset issue noted at `import_unified.py:289-293`).

### 7. Interactions
- Writes exactly the tables that Income (w2_records), Property (mortgages, accounts), 401(k) (retirement_*), RSU (rsu_grants, vest_events) read; the launching page refreshes on close.
- Planning picks up new W2/mortgage/vest data on its next table load (actuals/forecast immediately, engine rows after the next assumption PUT).
- Settings → Import tab is meant to show the resulting `import_logs` rows but cannot (route shadowing).

---

## Cross-cutting notes for the spec

- Legacy `/api` mount: Planning is the only live page still on it (`planning.ts`), and it bypasses usage logging/rate-limit headers and the 401-refresh path. `frontend/src/api/admin.ts` (legacy base) has no importers.
- Platform tables readable from tenant sessions: `search_path = "<tenant>", public` (`dependencies.py:124,136`) is what makes the SQL runner leak `public.users` etc. Narrowing the search_path or reverting to `"<tenant>"` only (as the seed script's `SET search_path TO tenant, public` suggests was deliberate) must be checked against every place that joins public tables from a tenant session (none found in the pages above; `ImportLog`/`EmailReceipt` are tenant tables).
- Hidden-but-live routes a refactor must either keep or consciously remove: `/admin/tables/*/rows` writes, `/import-legacy/*`, `/monarch/*`, `/plans/{sensitivity,variance,compare,forecasts,actuals}`, `/platform/users/{u}/tenants/{t}`, `/auth/seed-users`.
- Dead frontend: `stores/planning.ts`, `api/admin.ts`, Monarch tab code in `SettingsView.vue`, `api.generateForecast`, `api.importData`.
- Config files: `config.yaml` (repo root) is read only by `plan_table` for age/retirement_age; everything else in it (mortgage, contributions, w2_2025, account overrides) is unused by the backend.
