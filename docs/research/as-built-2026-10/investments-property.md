# Tallied — RSU, 401(k), Property, Assets: what the pages do today

Read-only investigation of the running app (backend http://localhost:8000, tenant `tenant_claudius`, Claudius Banks seed) on 2026-10-29. No repo files were changed. Every endpoint each page calls was hit with the real params the view sends; results are in each page's "Verified against seed" section. No Anthropic or RapidAPI key is configured, so every AI / Realtor.com path was exercised in its failure mode.

Shared facts that apply to all four pages:

- All four views are page-level monoliths that `fetch()` directly (no API client), each with a `Data` button (`useDataExplorer`, tables listed in `frontend/src/composables/useDataExplorer.ts:6-14`) and hover "View SQL" buttons whose SQL is hand-written documentation text, not what the backend runs (several reference columns that do not exist; see each page).
- RSU, 401(k) and Property have an `Import` button that opens the unified import modal (`useImportModal`, contexts `rsu` / `retirement` / `property`) which posts to `POST /api/v1/import/upload` and, after review, `POST /import/{id}/confirm`. Without `FINANCE_ANTHROPIC_API_KEY` the upload returns **500 `{"detail":"Anthropic API key not configured"}`** before anything is written (`backend/app/api/import_unified.py:184-185`). Assets has no Import.
- `get_tenant_db` (`backend/app/dependencies.py:110-145`) rolls back in `finally`, so any endpoint that `db.add()`/`flush()`es without `commit()` (several GETs below) leaves nothing behind, and any endpoint that raises after a flush is rolled back.
- Nothing on these pages feeds the Dashboard net-worth number. Net worth (`GET /trends/net-worth`, `backend/app/api/trends.py:16-40`) and the Planning engine inputs (`backend/app/services/planning_service.py:28-63`) are built from `balance_snapshots` joined to `accounts.display_group`. The seed writes `cb-property = 520,000` and `cb-401k = 160,000` snapshots (`scripts/seed_test_data.py:124-130`) that are independent of `property_valuations` (520,000) and `retirement_accounts.total_balance` (185,432.50). Nothing syncs them.

---

## 1. RSU (`/rsu`, `frontend/src/views/RSUView.vue`, `backend/app/api/rsu.py`)

### 1. Purpose
"What are my company RSUs worth right now, what would I net if I sold the vested ones today, and when do the rest vest?"

### 2. Sections (page order)

| # | Section | What it shows | Endpoint + params |
|---|---------|---------------|-------------------|
| H | Header (`RSUView.vue:226-250`) | Title "RSU Holdings"; `{{ symbol }} · $price/share` (symbol comes from `grants` response, line 53, default `'PTC'` line 26); link to E-Trade (hard-coded URL line 40); `Data` button → DataExplorer(`rsu`); `Import` button → import modal context `rsu`, `onComplete: fetchData`. | symbol/price from `GET /api/v1/rsu/grants` |
| 0 | Page load (`RSUView.vue:42-61`) | Three parallel fetches; a failure in any one (e.g. Yahoo 502) sets `error` and blanks the whole page (`.json()` on a 502 body still parses, so in practice a Yahoo failure yields `points: undefined` → empty chart, not an error). | `GET /rsu/summary`, `GET /rsu/grants`, `GET /rsu/price-history?symbol=PTC&range=5y` |
| E | Empty state (`255-258`) | "No RSU data found" when no grants and `held_shares` falsy. | – |
| A | Summary cards (`262-289`) | Holdings = `summary.held_value` (sellable+unvested × price) with "N sellable + M unvested"; Sellable = `sellable_value`; Unvested = `unvested_value`; Unrealized Gain = `tax_lots.all.gain` with "Cost basis $X". Tooltips say "PTC" (line 268). | `GET /rsu/summary` |
| B | Stock Price chart (`292-300`) | 5-year weekly line (ECharts), title `{{ symbol }} Stock Price` — **title says MSFT, data is PTC** (see §5). Dashed vertical markLines at each `is_actual` vest date within chart range (`142-160`). | `GET /rsu/price-history?symbol=PTC&range=5y` + vest dates from `/rsu/grants` |
| C | "If You Sold Today" (`305-446`) | Long-Term block, Short-Term block (shares, market value, cost basis, gain, est. tax / tax benefit, net proceeds), Total if sold, collapsible Assumptions (rates 15% / 37% federal + 5% state from `assumed_rates`). Header line: "Estimated tax impact on `tax_lots.all.shares` sellable shares at $price/sh". | `GET /rsu/summary` → `tax_lots` |
| D | Upcoming Vests (`449-477`) | Future (`is_actual=false`) vest events grouped by year: date, "Nd" countdown badge (computed client-side), "Grant YYYY", shares, ≈ est. value (shares × current price). | `GET /rsu/summary` → `upcoming_vests` |
| F | Vest Event Value by Year (`481-503`) | One tile per year: value; actual years use shares × FMV-at-vest, future years use shares × current price; mixed years show "actual + projected est"; projected-only years greyed with "projected". | `GET /rsu/summary` → `vesting_income_by_year` |
| G | All Grants (N) (`506-608`) | Grants sorted unvested-first then grant date desc (`94-104`). Each row: progress ring `vested/total` %, "Grant #id", grant date, "N unvested" or "Fully vested" pill, "total shares · sellable", held value and sellable value. Click expands a vest-event table: Vest Date, Shares, Withheld, Released, Cost Basis/sh (`fmv_at_vest`), Gain/sh (`price - fmv`), Tax Paid, Status (Future / Long / Short, Long = ≥366 days since vest). Caption: "Upload: E-Trade → Holdings → Download by Type (expanded) + Download by Status (expanded)". | `GET /rsu/grants` |
| – | `<DataExplorer />` (`611`) | Table browser modal for `rsu_grants`, `vest_events`, `stock_prices`. | its own endpoints |

Controls that write: none on this page except Import (modal). `fetchData` (`63-75`) re-runs the three fetches after import but does **not** update `symbol` (only `onMounted` does, line 53).

### 3. Data flow

Tables: `rsu_grants` (`backend/app/models/investment.py:11-30`), `vest_events` (`33-50`), `stock_prices` (`53-63`, unique `(symbol, price_date)`).

Endpoints:
- `GET /rsu/grants` (`rsu.py:30-98`): all grants + vest events; price via `_current_price(db, symbol)`; per-vest `tax_status` and `gain_per_share`; per-grant `held_value = (sellable + unvested) × price`.
- `GET /rsu/summary` (`rsu.py:217-386`): sums share counts; `upcoming_vests` = all `is_actual=false` vest events (no date filter: a past-dated unvested event would still appear); `vesting_income_by_year`; **tax lots**: for each grant, walk its `is_actual` vest events oldest-first and allocate `min(shares_released, remaining_sellable)` per lot (`282-330`). Rates hard-coded `LTCG 0.15 / STCG 0.37 / STATE 0.05` (`276-278`). Also consumed by Dashboard (`DashboardView.vue:32`) and Income (`IncomeView.vue:119,142`).
- `GET /rsu/price-history?symbol=&range=` (`rsu.py:389-416`): live, uncached call to `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1wk&range={range}` on **every page load**; 502 on any Yahoo error. `symbol` is interpolated unvalidated into the URL (any string, e.g. with `?`, is passed through). Does not touch the DB.
- `GET /rsu/grants/{id}`, `POST/PUT/DELETE /rsu/grants[/{id}]` (`rsu.py:121-214`): CRUD, **no frontend caller** (API-only).
- `POST /rsu/reload` (`rsu.py:419-444`): multipart E-Trade xlsx → `app.loaders.etrade_rsu.load_etrade_rsu`. **Dead**: `pandas` is not installed in the venv; verified `POST /rsu/reload` → 500 `Internal Server Error` (`ModuleNotFoundError: No module named 'pandas'`). No frontend caller.

**Where the stock symbol comes from, and where "PTC" is hard-coded:**
- Backend: symbol = `grants[0].symbol or "MSFT"` in `/rsu/grants` (`rsu.py:40`), `/rsu/summary` (`rsu.py:229`), `/rsu/grants/{id}` (`rsu.py:128`); Planning does the same (`backend/app/api/planning.py:587-589`). "First grant" is grant_date-desc in `/grants` but unordered `select(RSUGrant)` in `/summary` and `limit(1)` in planning — a mixed-symbol tenant gets a different "first grant" per endpoint. Seed grants all carry `symbol="MSFT"` (`seed_test_data.py:283`); E-Trade loader reads the Symbol column of the first Grant row (`loaders/etrade_rsu.py:101`) but writes `company="MSFT"` (`123,134`); unified import writes `company = symbol` (`import_unified.py:1107`).
- Frontend: `PTC` is hard-coded in `RSUView.vue:26` (default of `symbol`), `:47` and `:67` (the `price-history` request, both load paths), `:53` (fallback), and in tooltip/SQL text at `:268, :296, :297, :310, :453, :454, :485, :486, :510`. Also `DashboardView.vue:251, 350` tooltips. The `/rsu/price-history` endpoint itself defaults `symbol="MSFT"` (`rsu.py:390`) but the view always overrides it with PTC.

**Current price (`backend/app/services/stock_price.py:25-78`)**: looks for a `stock_prices` row with `source='yahoo'` for today; otherwise calls Yahoo `interval=1d&range=1d` (5 s timeout); on success **deletes every `stock_prices` row for (symbol, today) regardless of source** (`56-67`) and inserts a `yahoo` row, `commit()`; on Yahoo failure falls back to the newest `yahoo` row (non-yahoo rows are never used as fallback, `48-54`). Consequence verified in the DB: the seed's `MSFT 2026-10-29 95.50 source=seed` row (`seed_test_data.py:309-313`) is gone; `stock_prices` now holds one row `id=2, MSFT, 2026-10-29, 531.01, yahoo`. Every value on the page (and Dashboard / Planning RSU figures) is therefore priced at the live MSFT quote, not the seed's $95.50, while seed FMVs are random $80–110 (`seed_test_data.py:295`), producing a $161K "unrealized gain" on a $35K cost basis.

How tables get populated:
- Seed (`seed_test_data.py:269-314`): 8 grants `MSFT-001..008`, 3 annual vest events each (`is_actual = vest_date <= today`, `shares_released = shares` i.e. no net-of-withholding), one `stock_prices` row (overwritten on first load as above). **Real, exercised.**
- Unified import context `rsu` (`import_unified.py:99-145` prompt; `678-727` proposal; `1100-1184` apply): xlsx is converted to text via openpyxl (`import_unified.py:215-227`) and sent to Claude; proposed `rsu_grants` upserts carry the full grant+vest_events JSON in `data`; confirm upserts grant by `grant_number` and vest events by `(grant_id, vest_period)`. **Real path but requires an Anthropic key; untested here (500 without key).** It never writes `stock_prices`.
- E-Trade loader `POST /rsu/reload`: **theoretical / broken** (pandas missing).
- API CRUD `POST/PUT/DELETE /rsu/grants`: theoretical (no UI).
- Manual edit: none in UI. Database page can edit rows generically.
- External price fetch: Yahoo, real and exercised on every `/rsu/*` and Dashboard/Income/Planning load.

### 4. Verified against seed (real params the view sends)

| Call | Status | Result |
|------|--------|--------|
| `GET /api/v1/rsu/summary` | 200 | populated: `held_shares 1360, total_granted 1540, vested 873, unvested 667, sellable 693, held_value 722,173.60, current_price 531.01, symbol MSFT`; 12 `upcoming_vests` (2026-11-15 … 2028-11-20); `vesting_income_by_year` 2023–2028 (2026 mixed: 15,792.79 actual + 138,593.61 projected); `tax_lots.all = {shares 370, market_value 196,473.70, cost_basis 35,309.89, gain 161,163.81, est_tax 40,506.63, net_proceeds 155,967.07}`, LT 283 sh / ST 87 sh, 8 lots. |
| `GET /api/v1/rsu/grants` | 200 | 8 grants with 24 vest events, `current_price 531.01, symbol "MSFT"`. |
| `GET /api/v1/rsu/price-history?symbol=PTC&range=5y` | 200 | ~260 weekly PTC points from 2021-10-25 (PTC $127 → …). |
| `GET /api/v1/rsu/price-history?symbol=MSFT&range=5y` | 200 | MSFT points (what the page *should* be plotting). |
| `GET /api/v1/rsu/price-history?symbol=ZZZZNOPE&range=5y` | 502 | `{"detail":"Yahoo Finance error: HTTP Error 404: Not Found"}` |
| `POST /api/v1/rsu/reload` (dummy xlsx) | 500 | `Internal Server Error` — pandas missing. |

DB counts: `rsu_grants 8, vest_events 24, stock_prices 1 (yahoo)`.

### 5. Broken or suspicious

1. **Chart plots the wrong stock.** Title renders `MSFT Stock Price` (`symbol` from grants, `RSUView.vue:53,297`) but the series is PTC (`:47,:67`). Vest-date mark lines from MSFT grants are overlaid on PTC prices. Already BUG-4 in `docs/REVIEW-2026-10-29.md`.
2. **"If You Sold Today" silently covers fewer shares than "Sellable".** Sellable card = 693 shares; tax-lot header = 370 shares. FIFO (`rsu.py:282-300`) can only allocate up to `shares_released` of `is_actual` vest events; grants whose `sellable_shares` exceed released actual shares (seed `MSFT-005`: 170 sellable, 67 released; `MSFT-008`: 220 sellable, zero actual vests because its grant row says `vested_shares=250` while all three vest events are in the future) lose the remainder with no indication. The "Unrealized Gain" card is therefore computed on 370 of 693 shares.
3. **Seed stock price is overwritten by Yahoo on first load** (`stock_price.py:56-67`) — `seed_test_data.py:308-314` is effectively a no-op whenever the box has internet, and the demo numbers swing with the real MSFT quote (held value $722K at $531 vs $130K at the seed's $95.50).
4. Seed data is internally inconsistent: `sellable_shares = max(0, vested-30)` (`seed_test_data.py:286`), `shares_released = shares` (no withholding netting, `:301`), `MSFT-008` vested=250 with no actual vests (`:278`), random FMVs (`:295`).
5. `upcoming_vests` has no `vest_date > today` filter (`rsu.py:240-244`); the view's SQL text claims one (`RSUView.vue:453`).
6. `fetchData()` after import does not refresh `symbol` (`RSUView.vue:63-75`).
7. Dead/unused backend: `GET /rsu/grants/{id}`, `POST/PUT/DELETE /rsu/grants` (`rsu.py:121-214`), `POST /rsu/reload` (`419-444`, broken), `loaders/etrade_rsu.py` entire file, `parsers/etrade.py`. `RSUGrant.share_price` and `VestEvent.vest_price` are written but never read by any page.
8. `GET /rsu/price-history` is uncached, hits Yahoo on every page view, and passes `symbol`/`range` unvalidated into the URL (`rsu.py:395`).
9. Tax rates are hard-coded constants (`rsu.py:276-278`); "state 5%" is a Massachusetts assumption baked into every tenant.
10. "View SQL" strings are SQLite dialect and hard-code `'PTC'` (`RSUView.vue:296,453,485,510`); `vest_events.is_actual = 1` etc. Not what Postgres runs.
11. The grants list header tooltip (`RSUView.vue:512`) and caption (`:514`) describe the E-Trade spreadsheet loader path that does not work.
12. `rsu/summary` fetches the grant for every upcoming vest with a `db.get` in a loop (`rsu.py:247-248`) — N+1, harmless at this size.

### 6. Must never do (invariants for a refactor)

- Never show a value for shares the user cannot sell: `held = sellable + unvested`; `vested` is not used for valuation (`rsu.py:72,351`).
- Cost basis for an RSU lot is FMV at vest (`fmv_at_vest`), never grant-date price; long-term threshold is ≥ 366 days from vest date (`rsu.py:51,303`).
- Lots are allocated FIFO (oldest vest first) within a grant, capped at `shares_released` — and a refactor must *surface* any sellable shares that could not be allocated instead of dropping them.
- Actual vest years value at recorded FMV; future years at current price; a year with both is flagged `is_mixed` (`rsu.py:262-271,366-374`). Income page relies on this exact dict shape (`IncomeView.vue:120`).
- Price cache is per `(symbol, price_date)`; only `source='yahoo'` rows are trusted for today; must not pollute another tenant (table is per-schema).
- Dashboard's "RSU Holdings" tile and "Next Vests" (`DashboardView.vue:249-253,349-362`) and Planning's RSU vest income (`planning.py:584-595`) read `/rsu/summary`'s `held_value`, `sellable_shares`, `unvested_shares`, `upcoming_vests[]`, and `vest_events` directly — keep those field names/semantics.
- Grant primary key is the E-Trade grant number string (`rsu_grants.id`), and vest events are unique per `(grant_id, vest_period)` — import upserts depend on this.

### 7. Interactions with other pages

- Depends on: grants/vest events entered via Import (or seed); nothing else.
- Feeds: Dashboard (`RSU Holdings` tile, `Next Vests` list, SQL tooltips), Income (`Vest Event Value by Year` → `rsuByYear`), Planning (`planning.py:577-595` builds `rsu_vest_by_year` from `vest_events` + `get_or_fetch_price`; `planning_service.py:66-67` takes `rsu_income` from the latest W2, not from here), Guide text. The brokerage account `cb-brokerage` ("Investments" group, 45,000) in net worth is unrelated to RSU holdings — RSU value is not in net worth at all.

---

## 2. 401(k) (`/retirement`, `frontend/src/views/RetirementView.vue`, `backend/app/api/retirement.py`)

### 1. Purpose
"How much is in my 401(k), how is it split (Roth / pretax / match), what am I contributing, and how has it grown?"

### 2. Sections (page order)

| # | Section | What it shows | Endpoint |
|---|---------|---------------|----------|
| H | Header (`RetirementView.vue:429-447`) | "401(k) Retirement", subtitle `plan_name · provider`; `Data` → DataExplorer(`retirement`); `Import` (purple) → import modal context `retirement`, `onComplete: fetchData`. | – |
| 0 | Load (`147-164`) | Single fetch; treats 404 as empty (endpoint never 404s — it returns 200 with `account: null`). | `GET /api/v1/retirement/summary` |
| E | Empty state (`453-458`) | "No retirement data yet / Upload a 401(k) statement PDF". | – |
| A | Five cards (`462-534`) | Total Balance (`account.total_balance`, sub "Vested: …"); Account Return (`account_return` as %, "Since `return_period_start`"); Roth Balance (`breakdown.roth`, "N% of total"); Pretax Balance; Est. Monthly Income (`estimated_monthly_income`, "At retirement"). | `/retirement/summary` |
| B | Balance Breakdown (`541-572`) | Horizontal stacked bar Roth / Pretax / Employer Match / Other with inline labels when a segment > 8 %, legend with percentages. | same |
| C | Contribution Rates (`575-636`) | Pretax Deferral % and Roth Deferral % "of salary", "Total deferral: N% + employer match"; **Edit** → two number inputs, Cancel/Save. Save → `PUT /retirement/rates` with `{pretax_deferral_rate: x/100, roth_deferral_rate: y/100}` then re-fetch. | `PUT /api/v1/retirement/rates` |
| D | Holdings / Asset Allocation (`642-683`) | Right column. Donut only when >1 holding (`389-395`), otherwise titled "Holdings"; list of fund cards: fund name, ticker, allocation %, balance, `live_price` "/share", gain/loss. | same |
| F | Holdings Detail table (`688-732`) | Fund, Ticker, Balance, Allocation, Gain/Loss, Live Price. Shown only if ≥1 holding. | same |
| G | Balance History (`735-755`) | Line chart of `snapshots` when >1; single big number + date when exactly 1 ("Upload more statements…"); empty text otherwise. | same |
| I | Contributions (`758-789`) | "Employee (since T. Rowe Price)", "Employer (since T. Rowe Price)", "Roth Basis (lifetime)" with "Growth on Roth = roth − basis". | same |
| J | Footer (`792-797`) | "Statement period: start – end · Last updated: updated_at". | same |
| – | `<DataExplorer />` | `retirement_accounts`, `retirement_snapshots`, `retirement_holdings`. | – |

### 3. Data flow

Tables: `retirement_accounts` (`backend/app/models/retirement.py:12-52`), `retirement_holdings` (`55-68`, FK by convention only: `retirement_account_id` is a bare Integer), `retirement_snapshots` (`71-83`).

Endpoints:
- `GET /retirement/summary` (`retirement.py:78-168`): "the" account = `ORDER BY updated_at DESC LIMIT 1` (one account per tenant is assumed everywhere); holdings for it; snapshots ascending; **for every holding with a ticker it calls Yahoo live (`_fetch_fund_price`, `450-460`, 5 s timeout, no cache, no DB write)** on every page view; breakdown percentages computed here.
- `PUT /retirement/rates` (`225-245`): updates deferral rates on `select(RetirementAccount).limit(1)` — **no ordering**, so with >1 account it may not be the one `/summary` displays. Used by the Edit control.
- `PUT /retirement/account` (`181-217`): balances/plan edit, same `limit(1)` issue; **no frontend caller**.
- `POST /retirement/upload-statement` (`248-438`): legacy direct PDF → Claude (`claude-haiku-4-5-20251001`) → upsert account, holdings, snapshot, `ImportLog`. **No frontend caller** (the page's Import uses the unified modal). Without key: 500 `{"detail":"FINANCE_ANTHROPIC_API_KEY not configured"}` (`254-255`), nothing written. Listed as dead code AI-4 in the review.

How tables get populated:
- Seed (`seed_test_data.py:316-366`): one account "MICROSOFT CORPORATION 401(K) PLAN / Fidelity Investments" 185,432.50 (Roth 129,802.75, pretax 18,543.25, match 37,086.50), rates 0.10/0.02, return 0.123 since 2022-01-01, statement 2025-10-01..12-31, est. monthly income 4,520, one holding FDEEX 100 %, one snapshot 2025-12-31 `source='seed'`. **Real, exercised.**
- Unified import context `retirement` (`import_unified.py:62-76` prompt; `662-676` proposal; `942-1046` `_apply_retirement_changes`; `1048-1078` holdings): account-level fields only applied when the statement's `statement_end` ≥ existing (`is_newer`); percent fields divided by 100; a snapshot is upserted for `statement_end`; holdings are **deleted and replaced** on every confirm. **Real path, needs Anthropic key; 500 without it.**
- Manual edit: only deferral rates via the page (`PUT /rates`). Balances cannot be edited in the UI (only via `PUT /account` API or the Database page).
- External fetch: Yahoo fund price per holding, display only (`live_price` is not stored and not used in any calculation).
- AI valuation: none.

### 4. Verified against seed

| Call | Status | Result |
|------|--------|--------|
| `GET /api/v1/retirement/summary` | 200 | populated: account id 1, `total_balance 185432.5`, breakdown `roth_pct 70.0 / pretax_pct 10.0 / employer_pct 20.0`, 1 holding FDEEX with `live_price 20.55` (live Yahoo), 1 snapshot 2025-12-31. `account_return` serialises as `0.12300000000000001`. |
| `PUT /api/v1/retirement/rates` `{0.10, 0.02}` (same as seed, no net change) | 200 | `{"pretax_deferral_rate":0.1,"roth_deferral_rate":0.02,"total_deferral_rate":0.12}` |
| `POST /api/v1/retirement/upload-statement` (dummy pdf) | 500 | `FINANCE_ANTHROPIC_API_KEY not configured`, nothing written. |
| `POST /api/v1/import/upload` context=retirement | 500 | `Anthropic API key not configured` (not re-run for this context; same guard at `import_unified.py:184`). |

Page renders with: 5 cards populated, breakdown bar, rates 10 % / 2 %, "Holdings" (no donut: single holding), detail table, Balance History single-value state ($185,432 on Dec 31, 2025), Contributions $42,000 / $12,500 / $85,000 (growth $44,803), footer "Oct 1 – Dec 31, 2025 · Last updated Oct 29, 2026".

### 5. Broken or suspicious

1. **Provider name hard-coded as "T. Rowe Price"** in labels and tooltips while the data says Fidelity: `RetirementView.vue:471, 529, 651, 765, 769, 771, 775, 777`. Tooltip at `:781` hard-codes the original owner's personal figures ("Roth balance ($253K) and basis ($137K) = $116K"). `:583` hard-codes "IRS limit … $23,500 for 2025".
2. **"View SQL" text names non-existent columns**: `ra.employer_balance` (`:88`, real column `employer_match_balance`), `rh.account_id` (`:113`), `rs.account_id`, `rs.date` (`:121-128`; real `retirement_account_id`, `snapshot_date`). Running them in the Database page would fail.
3. `PUT /rates` and `PUT /account` use `limit(1)` without ordering (`retirement.py:184-186, 228-230`) while `/summary` uses `updated_at DESC` (`82`) — writes can target a different row than the one displayed if a tenant ever has two accounts (import always upserts "the latest", so today there is one).
4. Live Yahoo lookups per holding on every summary call (`retirement.py:101-106`) — latency, and each failed lookup is swallowed to `null`.
5. `other_balance` is overwritten with `None` by the legacy upload if absent (`retirement.py:331`); unified import leaves it. Display tolerates it.
6. Dead code: `POST /retirement/upload-statement` + `RETIREMENT_PARSE_PROMPT` (`retirement.py:27-75, 248-438`), `PUT /retirement/account` (no UI).
7. Frontend treats 404 as "no data" (`:154`) but the API never returns 404; harmless.
8. Balance History chart needs ≥2 snapshots; the only way to get a second one is a newer statement import — the view's own `updated_at` changes (e.g. editing rates) do not create snapshots, so the "Last updated" footer reflects the rate edit, not the balance.
9. The 401(k) balance shown here (185,432.50) does not match what Dashboard / Planning use for "Retirement" (balance snapshot of account `cb-401k`, ~160,000 + growth); nothing links `retirement_accounts.account_id` (`models/retirement.py:19`, never set) to `accounts.id`.

### 6. Must never do

- Never let an older statement overwrite current balances/rates: `is_newer` gate on `statement_end` (`import_unified.py:978-1000`, `retirement.py:315-337`) — older statements only add snapshots.
- Lifetime totals (`total_employee_contributions`, `total_employer_contributions`, `roth_basis`) only ever increase (`retirement.py:339-348`).
- Rates are stored as decimals (0.10), displayed as whole percents; the Edit form converts both ways (`RetirementView.vue:172-186`).
- One snapshot per `(account, statement_end)`; upserted, never duplicated.
- Holdings import replaces the full set (no stale funds after a new statement).
- `breakdown.*_pct` are server-computed from the four sub-balances over `total_balance`; keep the shape used by the page.

### 7. Interactions with other pages

- Depends on: statement imports (Import modal) or seed; W2 `pretax_401k`/`roth_401k` on the Income page are independent of this page's rates.
- Feeds: nothing reads `retirement_*` tables except this page and the Import modal. Dashboard "Retirement" layer and Planning `retirement_bal` come from `balance_snapshots` of the `investment_401k` account (`planning_service.py:28-63`, `trends.py:16-40`). Planning's 401(k) contribution config comes from `ContributionConfig` (`planning_service.py:83-89`), **not** from the deferral rates edited here.

---

## 3. Property (`/property`, `frontend/src/views/PropertyView.vue`, `backend/app/api/property.py`)

### 1. Purpose
"What is my house worth, what do I owe, how much equity do I have, and how does the mortgage pay down?"

### 2. Sections (page order)

| # | Section | What it shows | Endpoint |
|---|---------|---------------|----------|
| H | Header (`PropertyView.vue:651-669`) | "Property", subtitle = `summary.property.address` or "No property data"; `Data` → DataExplorer(`property`); `Import` → modal context `property`, `onComplete: refreshData`. | – |
| 0 | Load (`137-152`) | summary + amortization in parallel, then value-history in background. | `GET /property/summary`, `GET /property/amortization`, `GET /property/value-history` |
| E | Empty (`673-676`) | when neither property nor mortgage. | – |
| A | Five cards (`680-732`) | Property Value (`property.value`, sub "`valuation_source` · date"); Mortgage Balance (`mortgage.balance`, "of original"); Equity (`summary.equity`, "N% of value"); Interest Rate (`mortgage.rate`, "origination – maturity"); Monthly Payment (`mortgage.monthly_payment`, "P+I+Escrow"). | `/property/summary` |
| B | Property Value Over Time (`735-826`) | Time-axis chart: "Value History" line = all non-projected history points; scatter "Sale Price" (source `sale`, diamond), "Current Estimate" (`realtor_estimate`, purple), "Manual Entry" (`manual`, pink pin, legend only if present); dashed "Projected" line = last actual point + `ai_projection` points. Below: amber "AI Analysis" box (`commentary`), Realtor.com property details (beds/baths/sqft/built/lot), current valuation line, **"Refresh from Realtor.com"** button (`POST /property/refresh-history`), **"Add Entry"** → inline form: date (default today), $ text input, source select `Manual | Redfin | Zillow | Appraisal | Tax Assessment`, Add (`POST /property/valuation {value, source, valuation_date}`) / Cancel. After Add: re-fetch summary, amortization, history. | `/property/value-history`, `POST /property/refresh-history`, `POST /property/valuation` |
| C | Equity Position (`829-910`) | Four figures (value, balance, total equity, equity %); stacked bar Down Payment (amber) / Appreciation (green) / Principal Paid (indigo) / Remaining Mortgage (grey) with legend + %. Client-side: `purchasePrice = property.purchase_price ?? mortgage.original_amount` (`422-424`), `downPayment = purchasePrice − original_amount`, `equityFromPayments = original − balance`, `equityFromAppreciation = value − purchasePrice`. | `/property/summary` |
| D | Amortization Schedule (`915-937`) | Line (balance, left axis) + stacked thin bars Principal/Interest/Escrow (right axis), "Today" dashed markLine at `current_month_index`, shaded past area; footer: months remaining, payoff date, interest paid / remaining, principal paid. `escrow ?? 842` fallback at `:467`. | `/property/amortization` |
| F | Payment Breakdown (`940-982`) | Donut Principal / Interest / Escrow + table with Total. | `/property/summary` → `payment_breakdown` |
| – | `<DataExplorer />` | `mortgages`, `property_valuations`, `property_value_histories`. | – |

No UI exists to edit the mortgage (rate, balance, payment, escrow, address) other than Import or the Database page.

### 3. Data flow

Tables: `accounts` (row with `account_type='real_estate'`), `mortgages` (`backend/app/models/property.py:11-28`; `property_address` col 23), `property_valuations` (`31-43`: point-in-time value, `source` free text), `property_value_histories` (`models/property_value_history.py:12-22`: `source` ∈ `tax_assessment | realtor_estimate | sale | ai_projection | manual`, `is_projected`, `details` JSON).

Two parallel value stores: **cards use `property_valuations`** (latest `valuation_date`), **chart uses `property_value_histories`**. Manual Add and Realtor refresh write both; Import writes neither.

Endpoints:
- `GET /property/summary` (`property.py:34-131`): latest mortgage by `updated_at`; first `real_estate` account; **side effect**: if a mortgage exists with no real_estate account it `db.add()`s one and `flush()`es but never commits (`47-58`) — rolled back each request, so a tenant in that state gets `account_id` of a phantom row every call. Latest valuation by date (ties arbitrary). `equity = value − balance`. `payment_breakdown` is **computed**, not from the statement: `interest = balance × rate/12`, `principal = payment − interest − escrow` (`76-93`). `purchase_price` only from a `property_value_histories` row with `source='sale'` (`95-108`), which only Realtor refresh writes.
- `GET /property/amortization` (`134-211`): recomputes from `original_amount` at `origination_date` (fallback **hard-coded `date(2022, 3, 31)`**, `:151`) with fixed `monthly_payment − escrow` until balance 0 or 400 months; `current_month_index` = first month ≥ today; summary totals split past/future. It does **not** use `current_balance`, so the "Today" balance on the chart is the theoretical one, not the statement's.
- `POST /property/valuation` (`226-282`): inserts `property_valuations(value, source as typed e.g. "Zillow")` **and** `property_value_histories(source = 'manual' for Manual/Redfin/Zillow/Appraisal, 'tax_assessment' for Tax Assessment, details={valuation_source})`. Auto-creates the real_estate account if a mortgage exists; 404 otherwise. Commits.
- `GET /property/value-history` (`440-483`): all history rows for the account ascending; `commentary` and `property_details` pulled from the newest `ai_projection` row's `details` JSON.
- `POST /property/refresh-history` (`486-647`): resolves address (mortgage.property_address else account name; 400 if "Primary Residence"); **deletes every history row whose source ≠ 'manual'** (`521-530`, so user-entered "Tax Assessment" rows are wiped too); calls `get_property_estimate(address)` (`services/property_valuation.py:23-43`: RapidAPI "Realty in US", autocomplete → detail; returns `None` immediately when `rapidapi_key` is empty, `:28-30`; estimate = mean of all source estimates, `:92`); if None → **502 "Could not fetch property data from Realtor.com."** and the delete is rolled back. On success writes: `tax_assessment` rows for the last 8 years (dated Jan 1), one `sale` row (`last_sold_price/date`), one `realtor_estimate` row dated today **plus** a new `property_valuations` row `source="Realtor.com"` (`594-600`), then **AI**: `_ai_property_projections` (`717-817`, `claude-sonnet-4-20250514`, 1024 tokens) returns `{projections:[{year,value}×8], commentary}`; each becomes an `ai_projection` row dated Jan 1 of the year with `is_projected=True` and `details={commentary, property_details}` (`604-623`). Without an Anthropic key the helper returns `None` (`724-725`) and the response simply has no projections / no commentary — no error. Any Claude/JSON failure is `log.warning` + `None` (`814-815`). Commits at `:625`.
- `POST /property/estimate` and `/zillow-estimate` (`425-434` → `_do_property_estimate` `354-422`): Realtor-only; writes one `property_valuations` row on success; on failure returns **200** with `{"estimate": null, "error": "Property not found on Realtor.com…"}`. `realtor_error` is computed and discarded (`389-415`). **No frontend caller.**
- `PUT /property/mortgage` (`285-312`), `DELETE /property/valuation/{id}` (`315-323`, deletes the valuation but not its history twin), `GET /property/valuation-history` (`326-351`): **no frontend callers.**
- `_ai_property_estimate` (`654-714`): **dead** — never called anywhere (grep confirms). The module docstring and `/estimate` docstring ("falls back to AI") are stale.

How tables get populated:
- Seed (`seed_test_data.py:110-113, 242-267`): accounts `cb-property` (real_estate, "83 Roberts Road Ashland MA 01721") and `cb-mortgage`; one mortgage (4.25 %, $2,450/mo, escrow 450, original 380,000, balance 362,450.75, 2021-06-15 → 2051-06-01, `property_address` "83 Roberts Road, Ashland, MA 01721" — note the seed address is not the "456 Oak Street" in CLAUDE.md); one valuation 520,000 `source="Zillow Estimate"` dated today; **zero** history rows. **Real, exercised.**
- Unified import context `property` (`import_unified.py:77-98` prompt; `729-847` proposal; `908-940` apply): maps `mortgage_balance→current_balance, mortgage_rate→rate (÷100), mortgage_monthly_payment, mortgage_original_amount, mortgage_property_address, mortgage_escrow_payment→escrow` (`163-169`); `mortgage_escrow_balance`, principal/interest portions are extracted for review but have no column. Creates a `loan_mortgage` account + `Mortgage` row if none. Never writes a valuation. **Real path, needs key.**
- Manual: Add Entry (valuation + history). Realtor.com refresh: theoretical here (no RapidAPI key; 502). AI projections: theoretical (no key) and only reachable *after* a successful Realtor fetch.
- Settings → Accounts delete with `cascade=true` removes mortgages, valuations and history for the account (`backend/app/api/accounts.py` delete handler).

### 4. Verified against seed

| Call | Status | Result |
|------|--------|--------|
| `GET /api/v1/property/summary` | 200 | `property {address "83 Roberts Road, Ashland, MA 01721", value 520000, valuation_source "Zillow Estimate", valuation_date 2026-10-29, purchase_price null}`, `mortgage {balance 362450.75, rate 0.0425, monthly_payment 2450, original_amount 380000, origination 2021-06-15, maturity 2051-06-01}`, `equity 157549.25`, `payment_breakdown {total 2450, principal 716.32, interest 1283.68, escrow 450}`. |
| `GET /api/v1/property/amortization` | 200 | schedule from 2021-07-01, `is_past` flags, summary populated. |
| `GET /api/v1/property/value-history` | 200 | `{"history":[],"commentary":null,"property_details":null}` → chart shows "No value history yet" with instruction to click Refresh or add manually. |
| `GET /api/v1/property/valuation-history` | 200 | 1 valuation (unused by UI). |
| `POST /api/v1/property/refresh-history` | **502** | `{"detail":"Could not fetch property data from Realtor.com."}`; DB unchanged (0 history rows, 1 valuation). UI shows this text in red under the chart title. |
| `POST /api/v1/property/estimate` / `/zillow-estimate` | 200 | `{"estimate":null,"source":null,"error":"Property not found on Realtor.com. Please enter a valuation manually…"}` — misleading message (the key is missing, the property was never looked up); nothing written. |
| `POST /api/v1/import/upload` context=property (dummy pdf) | 500 | `Anthropic API key not configured`; no `import_sessions` row (guard runs before insert). |

Page renders: 5 cards; empty value chart; Equity Position shows **no Down Payment segment** and "Appreciation $140,000" (= 520,000 − 380,000 because `purchase_price` is null and the fallback uses the loan amount) plus "Principal Paid $17,549"; amortization chart with Today marker; payment donut 29 % / 52 % / 18 %.

### 5. Broken or suspicious

1. **Equity Position mislabels the down payment as appreciation** whenever there is no `sale` history row (always, unless Realtor refresh succeeded): `purchasePrice` falls back to `mortgage.original_amount` (`PropertyView.vue:422-424`), so down payment = 0 and "Appreciation" = value − loan.
2. **Refresh from Realtor.com destroys manual "Tax Assessment" entries**: the Add Entry form maps "Tax Assessment" to `source='tax_assessment'` (`property.py:263-270`) and refresh deletes everything with `source != 'manual'` (`521-530`).
3. **Parallel, divergent value stores**: `property_valuations` (cards) vs `property_value_histories` (chart). Realtor refresh appends a new `Realtor.com` valuation each run with the same date (`594-600`), so "latest" becomes ambiguous; `DELETE /property/valuation/{id}` leaves the history twin. A manual entry dated in the past is written to both but does not become the card value (ordering by `valuation_date`).
4. `GET /property/summary` has a write side effect (auto-create account, `47-58`) that is never committed — each request flushes an INSERT that is rolled back. Same pattern committed in `/valuation` and `/refresh-history`.
5. Amortization ignores `current_balance` and uses a hard-coded fallback origination `date(2022, 3, 31)` (`property.py:151`); the view hard-codes `escrow ?? 842` (`PropertyView.vue:467`). Both are the original owner's numbers.
6. `/property/estimate` returns 200 with an error body and a wrong message when the RapidAPI key is absent (`417-422`); `realtor_error` is computed and never returned.
7. Dead code: `_ai_property_estimate` (`654-714`), `/estimate`, `/zillow-estimate`, `PUT /mortgage`, `DELETE /valuation/{id}`, `GET /valuation-history` (no UI callers), stale docstrings claiming AI fallback (`property.py:4-5, 355, 427`).
8. AI projections are stored as `property_value_histories` rows (LLM guesses labeled only by `source='ai_projection'`), 8 years although the function docstring says 5 (`723, 760`); failures are `except Exception` → warning. Already AI-3 / DEC-3 in the review.
9. "View SQL" strings reference `m.escrow_payment` (`PropertyView.vue:89, 98, 112-113`; real column `escrow`).
10. `payment_breakdown` tooltip says "Source: Mortgage statement payment_breakdown" (`:728, :947`) but it is computed from rate × balance (`property.py:76-93`); the principal/interest portions the import prompt extracts (`import_unified.py:88-90`) are never stored.
11. Seed address "83 Roberts Road, Ashland, MA" contradicts CLAUDE.md's "456 Oak Street, Springfield MA"; the `accounts.name` form lacks commas vs `mortgages.property_address`.
12. Source select values ("Redfin", "Zillow", "Appraisal") are stored verbatim in `property_valuations.source` but collapsed to `manual` in history; the seed's "Zillow Estimate" is a third spelling.

### 6. Must never do

- `equity = latest valuation value − mortgage.current_balance`; never derive it from amortization.
- Manual entries (`source='manual'`) must survive a Realtor refresh; a refactor should extend that protection to anything the user typed (incl. tax assessments).
- A refresh must be atomic: if the external fetch fails, prior history must remain (today guaranteed only by the rollback in `get_tenant_db`).
- Projected points must stay `is_projected=True` and never feed cards, equity, net worth or Planning.
- `property_address` on the mortgage is the lookup key for any external valuation; the "Primary Residence" placeholder must block lookups (`property.py:385, 518`).
- `payment_breakdown` must sum to `monthly_payment` (principal + interest + escrow).
- Dashboard "Home Equity" tile reads `/property/summary.equity` (`DashboardView.vue:277-283`) — keep that field.

### 7. Interactions with other pages

- Depends on: Import (mortgage fields), the `real_estate` account existing (seed/Settings), optional external keys.
- Feeds: Dashboard Home Equity tile (`/property/summary`); Planning reads `mortgages` directly for balance/rate/payment (`planning_service.py:73-80`, `planning.py:577-580`) but takes `home_equity` from balance snapshots of the Home Equity display group, **not** from `property_valuations`. Settings → Accounts delete-cascade and related-counts touch `mortgages`, `property_valuations`, `property_value_histories` (`accounts.py`). Database page can edit all three tables.

---

## 4. Assets (`/assets`, `frontend/src/views/AssetsView.vue`, `backend/app/api/assets.py`)

### 1. Purpose
"What are my vehicles worth today, how much have they depreciated since I bought them, and where is their value heading?"

### 2. Sections (page order)

| # | Section | What it shows | Endpoint |
|---|---------|---------------|----------|
| H | Header (`AssetsView.vue:528-548`) | "Assets — Fixed capital assets — vehicles, equipment, and valuables"; `Data` → DataExplorer(`assets`); **Add Vehicle** button (hidden while form open). No Import. | – |
| 0 | Load (`109-154`) | summary, then aggregate history, then one request **per vehicle sequentially**. | `GET /assets/summary`, `GET /assets/value-history/aggregate`, `GET /assets/vehicles/{id}/value-history` ×N |
| A | Add Vehicle form (`556-619`) | Year* (default current year), Make*, Model*, Trim, Mileage, Condition select (excellent/very_good/good/fair/poor, default good), Purchase Price, Notes; Save → `POST /assets/vehicles` (fields only sent if truthy; **no purchase_date or VIN field**), then reload all. | `POST /api/v1/assets/vehicles` |
| B | Vehicle Value Over Time (`622-628`) | Stacked area per vehicle (solid = historical, dashed = projected from first `is_projected` date), x-axis = year of each history date, tooltip with per-vehicle and total. Rendered **only if** aggregate `dates.length > 0`. | `/assets/value-history/aggregate` |
| C | Three cards (`631-673`) | Total Asset Value (`total_value`, "N vehicles"); Total Purchase Price (`total_purchase_price` or "--", "Original cost basis"); Total Depreciation (red "-$" if lost, green "+$" if gained, or "Add purchase prices to track"). Shown only if ≥1 vehicle. | `/assets/summary` |
| D | Vehicles grid (`676-840`) | Card per vehicle, view mode: "YYYY Make Model" + trim, green `estimated_value` "Estimated value"; per-vehicle mini chart (only if that vehicle has history, `707-709`); collapsible "AI Analysis" with `valuation_notes` + "Updated date" (only if notes exist); Mileage / Condition pill / Purchase Price with ±depreciation; free-text `notes`; footer "Last valued: date" + **Refresh Value** (`POST /assets/vehicles/{id}/refresh-value`, then reload all), **Edit**, **Delete** → Confirm/Cancel (`DELETE /assets/vehicles/{id}`). Edit mode: Mileage, Condition, Purchase Price, Notes → Save (`PUT /assets/vehicles/{id}` sends all four, nulling blanks) / Cancel. Year/make/model/trim are not editable. | as listed |
| E | Empty (`843-849`) | "No assets tracked yet" + Add Vehicle. | – |
| – | `<DataExplorer />` | `vehicles`, `asset_value_histories`. | – |

### 3. Data flow

Tables: `vehicles` (`backend/app/models/asset.py:12-30`: `estimated_value`, `value_last_updated`, `valuation_notes`, `purchase_price`, `purchase_date`, `vin`), `asset_value_histories` (`models/asset_value_history.py:12-21`: `vehicle_id`, `date`, `value`, `source` ∈ `ai_estimate | purchase | manual`, `is_projected`).

Endpoints (`assets.py`):
- `GET /assets/summary` (`271-287`): `total_value` = Σ `estimated_value` over **all** vehicles; `total_purchase_price` = Σ over vehicles with a purchase price; `total_depreciation = total_purchase − total_value` (mixes the two populations, see §5); `vehicles[]` serialized (`292-309`, per-vehicle `depreciation` only when both present). Also consumed by Dashboard (`DashboardView.vue:36, 286-292`).
- `GET /assets/vehicles` (`49-56`): list, no UI caller (summary carries the list).
- `POST /assets/vehicles` (`59-85`): insert, then **synchronously calls Claude** `_estimate_value_simple` (`312-341`, `claude-sonnet-4-20250514`, 100 tokens, "return only a number") and stores `estimated_value` + `value_last_updated` if a number came back. Without key the helper returns `None` (`314-315`) and the vehicle is created with `estimated_value = null` — the request still succeeds (201-ish 200). Does not write history.
- `PUT /assets/vehicles/{id}` (`88-103`): sets mileage/condition/notes/purchase_price; no re-valuation.
- `DELETE /assets/vehicles/{id}` (`106-116`): deletes history rows then the vehicle.
- `POST /assets/vehicles/{id}/refresh-value` (`119-189`): `_estimate_value_with_history` (`344-409`, `claude-sonnet-4-20250514`, 1024 tokens) asks for `{current_value, history:[{year,value}] for max(purchase_year, now−5)..now, projections:[now+1..now+5], reasoning}`. On success: sets `estimated_value`, `value_last_updated`, `valuation_notes = reasoning`; **deletes this vehicle's history rows with source in (`ai_estimate`, `purchase`)**; inserts a `purchase` row (only if both `purchase_price` **and** `purchase_date` are set — the UI never sets `purchase_date`, so UI-added vehicles never get this point); inserts one `ai_estimate` row per history year (`is_projected=False`, dated Jan 1) and per projection year (`is_projected=True`); commits; returns `{estimated_value, updated: true, reasoning}`. If the rich call fails, falls back to the simple estimate (value only, no history). If both fail: **200 `{"estimated_value": null, "updated": false, "error": "Could not estimate value"}`**, nothing written. All Claude/JSON errors are `except Exception: pass` (`338-339, 406-407`).
- `GET /assets/vehicles/{id}/value-history` (`192-216`): rows ascending.
- `GET /assets/value-history/aggregate` (`219-268`): union of all history dates; per-vehicle value or `null` for dates it lacks (`250`, a literal 0 also becomes null); `is_projected[date]` true if any vehicle's row on that date is projected.

How tables get populated:
- Seed (`seed_test_data.py:368-384`): 2019 Toyota RAV4 XLE 45,000 mi good, bought 28,500 on 2019-08-15, est 22,000; 2015 Honda Civic LX 98,000 mi fair, bought 18,200 on 2015-03-20, est 8,500; `value_last_updated = now`; **no history rows, no valuation_notes**. **Real, exercised.**
- UI Add / Edit / Delete: real, exercised in code (not mutated during this probe).
- AI valuation (create + refresh): **theoretical here** — no key, so Add produces a vehicle with no value and Refresh is a no-op returning 200 with an `error` field that the view ignores (it only checks `res.ok`, `AssetsView.vue:300-303`, so the user sees nothing happen).
- `source='manual'` history rows: no code path writes them (dead enum value).
- Import: none for vehicles.

### 4. Verified against seed

| Call | Status | Result |
|------|--------|--------|
| `GET /api/v1/assets/summary` | 200 | `total_value 30500, total_purchase_price 46700, total_depreciation 16200, vehicle_count 2`, both vehicles with `depreciation 6500 / 9700`, `valuation_notes null`. |
| `GET /api/v1/assets/value-history/aggregate` | 200 | `{"dates":[],"total":[],"vehicles":{"2015 Honda Civic":[],"2019 Toyota RAV4":[]},"is_projected":[]}` → "Vehicle Value Over Time" section is **not rendered**. |
| `GET /api/v1/assets/vehicles/1/value-history`, `/2/value-history` | 200 | `history: []` → no per-vehicle mini charts. |
| `GET /api/v1/assets/vehicles` | 200 | 2 vehicles (not used by UI). |
| `POST /api/v1/assets/vehicles/1/refresh-value` | **200** | `{"estimated_value":null,"updated":false,"error":"Could not estimate value"}`; vehicle row unchanged (22,000, same timestamp), 0 history rows. In the UI the button flips "Refreshing…" → back, nothing changes, no message. |

Page renders: three cards ($30,500 / $46,700 / −$16,200 "Lost since purchase"), two vehicle cards with mileage/condition/purchase and "Last valued: Oct 29, 2026", no charts, no AI Analysis.

### 5. Broken or suspicious

1. **Refresh Value failure is invisible**: backend returns 200 with `updated:false` and the view only checks `res.ok` (`AssetsView.vue:300-303`); same for Add Vehicle, which silently yields a vehicle with "--" value when AI is unavailable (`assets.py:77-81`).
2. **`total_depreciation` mixes populations** (`assets.py:276-284`): `total_value` includes vehicles without a purchase price, `total_purchase_price` excludes them, so adding a priceless vehicle *reduces* reported depreciation.
3. **Purchase point can never appear for UI-added vehicles**: Add form has no `purchase_date` (`AssetsView.vue:79-88, 219-228`) and `refresh-value` requires it (`assets.py:143`); seed vehicles do have dates, so only they would ever get a `purchase` point.
4. Refresh **deletes and rewrites** AI history each time (`133-139`): history is not an audit trail, it is the latest LLM's opinion of the past, stored as fact (AI-3 / DEC-3 in the review). LLM failures swallowed (`338-339, 406-407`).
5. Aggregate chart: `val if val else None` turns a $0 value into a gap (`assets.py:250`); vehicles valued on different year grids leave `null`s that break the stack; `showInLegend` (`AssetsView.vue:386`) is not an ECharts option (dead key); dates collapse to year labels so two points in one year produce duplicate x categories.
6. Sequential per-vehicle history fetches (`AssetsView.vue:136-138`) — N+1 round trips on load.
7. `source='manual'` history (`models/asset_value_history.py:19`) and `vin`/`purchase_date` create fields (`assets.py:32, 36`) are unreachable from the UI. `GET /assets/vehicles` has no caller.
8. Vehicle identity fields (year/make/model/trim) cannot be corrected after creation except via the Database page.
9. Tooltip claims "AI-generated estimates using KBB, Edmunds, and NADA reference data" (`AssetsView.vue:625`) — the model is only *asked* to imitate those sources (`assets.py:360`); there is no data lookup.
10. "Last valued" shows the seed timestamp (today) even though no valuation ever ran; `value_last_updated` is set by the seed (`seed_test_data.py:374, 381`).

### 6. Must never do

- Never block or fail vehicle creation on the AI estimate; the vehicle row must persist with `estimated_value = null` (current behaviour, keep it, but surface it).
- Depreciation = `purchase_price − estimated_value`, only for vehicles with both; the summary must not subtract values of vehicles that have no purchase price.
- Projected history rows must be `is_projected=True` and must not feed `total_value` or the Dashboard "Vehicles" tile.
- Deleting a vehicle deletes its history (FK is a bare Integer with `ForeignKey` but no cascade; the endpoint does it manually, `assets.py:113`).
- Refresh must not touch other vehicles' rows and must preserve any non-AI history (today only `manual`, which nothing writes).
- Dashboard reads `/assets/summary.total_value` (`DashboardView.vue:286-292`); keep that field.

### 7. Interactions with other pages

- Depends on: nothing — vehicles are entered only on this page.
- Feeds: Dashboard "Vehicles" tile (`total_value`). Vehicles are **not** in net worth (no `accounts` row, no balance snapshots) and not in Planning. Guide text (`GuideView.vue:126, 188-189`) describes AI valuation and "manual entry" of vehicle details.

---

## Cross-cutting notes for the spec

- Four different "value" stores for the same household: `balance_snapshots` (net worth, Planning), `property_valuations` + `property_value_histories` (Property), `retirement_accounts` (401k), `stock_prices` × grants (RSU), `vehicles.estimated_value` (Assets). Only the first drives the Dashboard net-worth and the Planning engine.
- Every external dependency and its failure mode, as verified: Yahoo (RSU price, fund price, price history) — live, works, uncached except the daily `stock_prices` row; RapidAPI Realtor.com — not configured, `refresh-history` 502, `estimate` 200-with-error; Anthropic — not configured, `import/upload` 500, `retirement/upload-statement` 500, vehicle refresh 200-with-error, vehicle create succeeds without a value, property AI projections silently skipped.
- Hard-coded tenant residue to remove in a refactor: `PTC` (RSU view + Dashboard tooltips), `T. Rowe Price` and `$253K/$137K/$116K` (401k view), escrow `842` and origination `2022-03-31` (Property), MA state tax 5 % (RSU backend), "83 Roberts Road" vs "456 Oak Street" (seed vs CLAUDE.md).
- Probe side effects on the seed DB: none persisted, except that the first `/rsu/summary` call (which the app itself makes on any Dashboard/RSU/Income load) replaced the seed `stock_prices` row with the live Yahoo quote.
