# Money pages — as-built brief (Dashboard, Spending, Income, Cash)

Date: 2026-10-29. Branch `punchlist/2026-10`. Verified against the running backend
(http://localhost:8000/api/v1) logged in as `claudius@tallied.dev` (tenant schema
`tenant_claudius`). Read-only investigation; no repo files changed.

All file paths below are relative to `/Users/mcheli-mini/repos/tallied/`.

## Seed-data facts that shape every "verified" result

The seed (`scripts/seed_test_data.py`) is **calendar-fixed, not relative to today**:

| Table | Rows | Date span | Notes |
|---|---|---|---|
| `accounts` | 8 | — | ids `cb-*`; all `is_active`, all `include_in_nw=true`; display_groups: Cash x3, Credit Cards, Investments, Home Equity x2, Retirement |
| `balance_snapshots` | 120 | 2025-01-01 .. **2026-03-01**, monthly on the 1st | source=`seed`; latest balance is 8 months stale vs today |
| `transactions` | 428 | 2025-01-01 .. **2026-02-23** | source=`seed`; **all on `cb-checking`**; categories incl. `Paychecks` (+), `Transfer` (mortgage payment −2,450/mo) |
| `w2_records` | 3 | tax years 2023, 2024, 2025 | all 14 numeric fields populated |
| `rsu_grants` / `vest_events` / `stock_prices` | 8 grants | — | MSFT; `stock_prices` was seeded at $95.50 but the API reports $531.01, i.e. the Yahoo price fetch ran |
| `mortgages` | 1 | — | `current_balance` 362,450.75 (independent of the `cb-mortgage` snapshot −368,100) |
| `property_valuations` | 1 | `date.today()` | 520,000 (independent of the `cb-property` snapshot 530,292.78) |

Consequence: any control whose default window is "last 30/90/180 days from today"
returns **empty** against the seed. This is a seed-freshness problem, not a code
bug, but it means the default views of Spending and Cash look broken today.

Shared UI conventions on all four pages: every tile has an `InfoTooltip`, and every
tile/chart has a hover "View SQL" button opening `SqlViewerModal`. The SQL strings
are **static documentation strings in the Vue files** (not what the backend runs),
written in **SQLite dialect** (`strftime`, `date('now', ...)`, `is_active = 1`)
although the DB is Postgres. The modal can preview the named tables via
`GET /admin/tables/{table}/preview` and hand the SQL to the Database page runner via
`sessionStorage['sql-runner-query']` (`SqlViewerModal.vue:34`), where the SQLite
dialect would fail.

Auth/tenancy: every endpoint on these pages uses `get_tenant_db`
(`backend/app/dependencies.py:110-130`, `SET search_path TO "<schema>", public`
on every transaction begin). `GET /snapshot` without the cookie returns 401 (verified).

---

## 1. Dashboard (`/`, `frontend/src/views/DashboardView.vue`)

### 1.1 Purpose
"What am I worth right now, how is that split by liquidity, and what is about to
change (vests, spending)?"

### 1.2 Sections (page order)

Data loading (`DashboardView.vue:25-51`): the Pinia `snapshot` store fetches
`/snapshot` and `/income/current`; then six fetches run in one `Promise.all` inside
a single `try/catch` that swallows everything.

| # | Section | Shows | Endpoint + params |
|---|---|---|---|
| 1 | Loading spinner / error text | `store.loading` / `store.error` | — |
| 2 | MetricCard **Net Worth** | `snapshot.net_worth` via `compact()` | `GET /snapshot` |
| 3 | MetricCard **Liquid Net Worth** | `snapshot.liquid_net_worth` | `GET /snapshot` |
| 4 | MetricCard **RSU Holdings** | `rsu.held_value`; subtitle `sellable + unvested` shares | `GET /rsu/summary` |
| 5 | MetricCard **Total Comp** | `snapshot.total_comp_annual`, subtitle "annual (W2)" | `GET /snapshot` |
| 6 | MetricCard **12mo Change** | `snapshot.net_worth_12mo_change` + % badge computed client-side (`:62-67`) | `GET /snapshot` |
| 7 | MetricCard **Property Equity** (only if property summary loaded) | `property.equity` | `GET /property/summary` |
| 8 | MetricCard **Vehicles** (only if assets summary loaded) | `assets.total_value` | `GET /assets/summary` |
| 9 | ChartContainer **Liquidity Layers** (`LiquidityWaterfall`) | waterfall of `snapshot.layers[].total` + a final "Net Worth" bar = running sum | `GET /snapshot` |
| 10 | ChartContainer **Compensation Split** (`CompDonut`) | donut salary vs RSU, center = sum | `GET /income/current` |
| 11 | **Net Worth Over Time** (`NetWorthChart`) | stacked area by `display_group` | `GET /trends/net-worth` (no date params → all history) |
| 12 | **Next Vests** (only if any) | first 4 of `rsu.upcoming_vests` (date, shares, est value) | `GET /rsu/summary` |
| 13 | **Last 30 Days Spending** (only if any categories) | top 5 of returned categories + Total | `GET /spending/by-category?start_date=<today-30>&end_date=<today>` (**wrong param names**, see 1.5) |
| 14 | Plaid status line (only if links) | count + institution names | `GET /plaid/links` |
| 15 | **Account Details** (`LayerCard` x N) | one collapsible card per layer: name, account count, total; expands to per-account balances | `GET /snapshot` |

Controls: none (no date range, no filters). The only interactions are expanding
layer cards and opening SQL modals.

### 1.3 Data flow

`GET /snapshot` → `backend/app/services/snapshot_service.py:build_current_snapshot`
- Reads `accounts` (is_active, include_in_nw, display_group) joined to the
  **latest `balance_snapshots` row per account** (max `snapshot_date`), plus the
  latest `w2_records` row (by `tax_year`) for `total_comp_annual = base_salary + rsu_income`.
- Layers: `display_group` lower-cased and `_`-joined, ordered by `LAYER_ORDER`
  (cash, investments/company_stock, home_equity, retirement, other); anything else
  (e.g. `credit_cards`, `other_loans`) sorts last and is re-titled with `.title()`.
- `net_worth` = sum of latest balances where `include_in_nw`;
  `liquid_net_worth` = same restricted to groups `{cash, investments, company_stock}`
  (`:33`). Layer totals ignore `include_in_nw` (`:96-97`).
- `net_worth_12mo_change` (`:134-175`): finds, per account, the latest snapshot
  inside a **±7-day window around today−365**, sums those where `include_in_nw`,
  returns `current − past`; `None` if no snapshot falls in the window.

`GET /income/current` → `backend/app/api/income.py:81-103`: latest `w2_records`
row (NOT the current calendar year; `current_year` at `:84` is unused).

`GET /trends/net-worth` → `backend/app/api/trends.py:15-65`: all
`balance_snapshots` joined to active, `include_in_nw` accounts, grouped by
`snapshot_date` x raw `display_group` string.

`GET /rsu/summary` (`rsu.py`) reads `rsu_grants`, `vest_events`, `stock_prices`
(and triggers/uses the Yahoo price service). `GET /property/summary` reads
`property_valuations` + `mortgages`. `GET /assets/summary` reads `vehicles`.
`GET /plaid/links` reads `plaid_links`. `GET /spending/by-category` reads
`transactions` (see Spending).

How those tables get populated today:

| Table | Real & exercised | Wired but not exercised / theoretical |
|---|---|---|
| `accounts` | seed; Settings → Accounts create/edit/delete (`PUT/POST/DELETE /accounts`); SimpleFIN scheduler auto-creates (`sync_scheduler.py:451-457`) | Plaid exchange creates (`plaid_routes.py:310-337`); Monarch (`monarch_routes.py:437-448`, hidden in UI and removed from `ALL_PROVIDERS`, `sync_scheduler.py:34`); unified import creates Home Equity accounts for mortgage docs (`import_unified.py:920`) |
| `balance_snapshots` | seed (`source='seed'`); SimpleFIN scheduler every 12h (`source='simplefin'`, `:483`) | Plaid `/plaid/sync-balances` (`source='plaid'`); Monarch sync-balances/scheduler (`source='monarch'`); `POST /accounts/{id}/balances` (API only, **no UI calls it**); DataExplorer generic row editor (`/admin/tables/balance_snapshots/rows`); legacy `import_service.py` CSV/JSON |
| `w2_records` | seed; Settings → Income form (`POST /income/w2`, **only 8 fields**, `SettingsView.vue:190-199`); AI import with context `income` (`import_unified.py:364-366, 892-894`, upsert by `tax_year`) | legacy `ingest.py` w2/paystub upload (no frontend caller found) |
| `rsu_grants`/`vest_events`/`stock_prices` | seed; RSU page import; Yahoo price fetch | — |
| `property_valuations`/`mortgages` | seed; Property page import (mortgage context) | — |
| `vehicles` | seed; Assets page (AI valuation) | — |

### 1.4 Verified against seed

| Call (as the view sends it) | Status | Result |
|---|---|---|
| `GET /snapshot` | 200 | layers: Cash 29,718.15 (3 accts), Investments 50,179.96, Home Equity 162,192.78 (property 530,292.78 + mortgage −368,100), Retirement 182,400, **Credit Cards −775.31**; `net_worth` 423,715.58; `liquid_net_worth` 79,898.11; `total_comp_annual` 210,000; `net_worth_12mo_change` 30,652.8 |
| `GET /income/current` | 200 | salary 145,000; rsu 65,000; total 210,000; rsu_pct 31.0 |
| `GET /rsu/summary` | 200 | held_value 722,173.6 @ $531.01 MSFT; 693 sellable + 667 unvested; 8 upcoming vests (first 4 shown, all Nov 2026) |
| `GET /plaid/links` | 200 | `[]` → status line hidden |
| `GET /property/summary` | 200 | equity **157,549.25** (520,000 − 362,450.75) |
| `GET /assets/summary` | 200 | total_value 30,500 (2 vehicles) |
| `GET /trends/net-worth` | 200 | 15 monthly points 2025-01-01..2026-03-01, groups Cash/Credit Cards/Home Equity/Investments/Retirement |
| `GET /spending/by-category?start_date=2026-09-29&end_date=2026-10-29` | 200 | **12 categories, all-time** (Transfer −34,300 / 65.3 %, Groceries −3,839.77, ...) because the params are ignored |
| same with the correct `from_date`/`to_date` | 200 | `[]` (seed has no transactions in the last 30 days) |

Mismatch: the view sends `start_date`/`end_date` (`DashboardView.vue:34`); the
endpoint declares `from_date`/`to_date` (`spending.py:39-40`). FastAPI ignores
unknown query params, so the tile is silently unfiltered.

### 1.5 Broken or suspicious

1. **"Last 30 Days Spending" is all-time spending.** `DashboardView.vue:34` vs
   `backend/app/api/spending.py:39-40`. Verified above. The tooltip and SQL string
   (`:209-217`) also claim a 30-day window.
2. **Liquid Net Worth tooltip/SQL disagree with code.** `DashboardView.vue:243` and
   the SQL at `:86-96` say liquid NW = cash + investments + credit cards + other
   loans; `snapshot_service.py:33` only counts `cash`, `investments`,
   `company_stock`. Verified: 79,898.11 = 29,718.15 + 50,179.96; the −775.31 credit
   card is excluded.
3. **Two different home-equity numbers on one page.** Property Equity card =
   157,549.25 from `property_valuations`+`mortgages`; Home Equity layer (waterfall,
   Account Details, net worth) = 162,192.78 from `balance_snapshots`. Nothing
   reconciles them; the seed itself writes different values to each table.
4. **Total Comp tooltip wrong.** `:259` says it includes "any other compensation";
   `snapshot_service.py:117-119` uses `base_salary + rsu_income`, not `gross_pay`.
   Equal for the seed only because the seed sets gross = base + rsu.
5. **Hard-coded "PTC"** in RSU Holdings and Next Vests tooltips (`:251`, `:350`);
   the persona's symbol is MSFT (`rsu.symbol`).
6. **Tooltip claims Plaid transactions are included** (`:375`); every spending
   query excludes `source = 'plaid'` (`spending.py:53`).
7. **12mo Change is calendar-fragile.** `snapshot_service.py:139-141` looks in a
   ±7-day window around today−365. With monthly snapshots on the 1st it works on
   2026-10-29 (window 10-22..11-05 catches 2025-11-01) but on, say, the 15th of a
   month it returns `None` → "—". Also compares against only the accounts that
   existed a year ago, so adding an account inflates "change".
8. **Waterfall "Net Worth" bar ≠ Net Worth metric when any account has
   `include_in_nw=false`.** `LiquidityWaterfall.vue:31-43` sums every layer total;
   `snapshot_service.py:98-99` honours `include_in_nw`. Identical for the seed only.
9. **One failed fetch blanks five tiles.** `DashboardView.vue:31-50`: a single
   `Promise.all` in a bare `try/catch` → if any of the six requests throws, none of
   the six results are assigned and nothing is shown or logged.
10. **Compensation Split / Total Comp use "latest W2 year", not the current year.**
    `income.py:84` computes `current_year` and never uses it.
11. **`nwChange` percent badge hides a zero change** (`:62-67` returns `undefined`
    when `net_worth_12mo_change` is 0/null).
12. **Net Worth Over Time stacks a negative series** ("Credit Cards") into a
    stacked-area chart (`NetWorthChart.vue`), which renders misleadingly; colours
    are only defined for 4 groups.
13. **`trends/net-worth` groups by raw `display_group` string**, while
    `/snapshot` normalises (lower/underscore) and re-titles. A manually created
    account with `display_group='cash'` appears inside the "Cash" layer on
    `/snapshot` but as a separate `cash` series on the trend chart.
14. **Latent double count.** `balance_snapshots` is unique on
    `(account_id, snapshot_date, source)`. The "latest per account" join in
    `snapshot_service.py:43-69` (and `accounts.py:42-74`, `trends.py`) joins on
    date only, so two sources writing the same account on the same day
    (e.g. `simplefin` + `manual`) produce two rows → the balance is summed twice.
15. SQL-viewer strings are SQLite dialect (see header); e.g. `:133` uses
    `date('now', '-372 days')`.

### 1.6 Must never do (invariants)

- Never show numbers from another tenant: all reads via `get_tenant_db`; no
  module-level caches of snapshot data. If the SPA tenant switcher is used, the
  Pinia `snapshot` store must be refetched (it is not cleared on switch today —
  worth checking in a refactor).
- Net worth is always **latest snapshot per account**, never a sum over snapshot
  history; only `is_active` accounts; `include_in_nw` must be honoured by net
  worth, liquid net worth, the 12-month comparison and the trend chart.
- Layer order is fixed (Cash → Investments → Home Equity → Retirement → other);
  the Cash layer must be exactly the accounts whose `display_group` normalises to
  `cash` (the Cash page depends on `layers[].name === 'Cash'`).
- Money: `Decimal` in DB, `float` in JSON; `compact()` formatting ($K/$M) on tiles.
- Negative balances (liabilities) are legitimate layer members and must subtract.
- Dashboard performs no writes (the only writes reachable from this page are the
  SQL modal's table preview, which is read-only).
- Every tile keeps an `InfoTooltip` and a View-SQL affordance (product convention
  from CLAUDE.md).

### 1.7 Interactions with other pages

- Settings → Accounts: `display_group`, `include_in_nw`, `is_active`, names.
- Settings → Income form or Income page → Import: `w2_records` (Total Comp,
  Compensation Split).
- RSU page: grants/vests + live stock price (RSU Holdings, Next Vests).
- Property page: valuation + mortgage (Property Equity card only).
- Assets page: vehicles.
- Settings → Connections (SimpleFIN; Plaid/Monarch): balance snapshots that feed
  everything else; "N Plaid accounts connected" line.
- Spending data (transactions) from sync/email/API feeds the "30 days" tile.

---

## 2. Spending (`/spending`, `frontend/src/views/SpendingView.vue`)

### 2.1 Purpose
"Where did my money go in a chosen period, what recurs, and how does monthly spend
trend?"

### 2.2 Sections (page order)

State lives in the Pinia `transactions` store (`frontend/src/stores/transactions.ts`).
`loadData()` (`SpendingView.vue:134-144`) sets `from/to` from the preset, copies the
selected account types into `store.filters`, resets `page=1`, then fires four
requests. It runs on mount, on preset change and on every chip toggle (`:146-147`).

| # | Section | Shows | Endpoint + params |
|---|---|---|---|
| 1 | Header: **Data** button | opens `DataExplorer` for tables `transactions`, `accounts` | `GET /admin/schema`, `GET /admin/tables/{t}/preview?limit&offset`, row edit `PUT/POST /admin/tables/{t}/rows[/{id}]` |
| 2 | Header: date presets **This Month / Last 3 Months (default) / YTD / Last 12 Months** | sets `from_date`,`to_date` (`:104-132`) | scopes #4 and #6 only |
| 3 | **Account types** chips (All + one per distinct `account_type`, with counts) | built from `GET /accounts/` on mount (`:151`); multi-select; "All" clears | scopes #4, #5, #6, #7 via `account_types=a,b` |
| 4 | ChartContainer **Spending by Category** (`CategoryChart`) | horizontal bars, top 15 by `abs(total)`, truncated labels | `GET /spending/by-category?from_date&to_date[&account_types]` |
| 5 | **Recurring Expenses** (`RecurringList`) | merchant, category, `avg_monthly`/mo, sorted desc; "No recurring expenses detected" | `GET /spending/recurring[?account_types]` (default `months=6`; **no date params**) |
| 6 | **Transactions** (`TransactionTable`) | columns Date, Merchant, Account (name via map from #3, `—` when `account_id` null), Category, Amount (red/green); "N total"; search box; Prev/Next (25/page) | `GET /transactions/?from_date&to_date&offset&limit=25[&account_types][&search][&category][&category_group][&account_id][&merchant]` (also sends `page`,`page_size`, ignored by FastAPI) |
| 7 | ChartContainer **Monthly Spending Trend** (`MonthlyTrend`) | bar per `YYYY-MM`, abs(total) | `GET /spending/monthly-trend[?account_types]` (**no date params → all time**) |
| 8 | `DataExplorer` modal | — | see #1 |

Search (`TransactionTable.vue:46-50` → `SpendingView.vue:161-165`) refetches #6 on
every keystroke, resetting to page 1. Paging refetches #6 only.

### 2.3 Data flow

All four endpoints read **only `transactions`** (plus a sub-select on `accounts`
for the `account_types` filter, `spending.py:24-34`, `transactions.py:42-49`).

- `/spending/by-category` (`spending.py:37-77`): `amount < 0`, `source != 'plaid'`,
  date range inclusive, group by `category, category_group`, ordered most negative
  first; `pct_of_total` of the returned set (unused by the UI).
- `/spending/recurring` (`:80-126`): `amount < 0`, `source != 'plaid'`,
  `date >= today − months*30`, `merchant IS NOT NULL`, grouped by merchant+category,
  `HAVING count(distinct YYYY-MM) >= max(2, months//3)`; `avg_monthly` is
  `abs(AVG(amount))` **per transaction**, not per month.
- `/spending/monthly-trend` (`:129-164`): `amount < 0`, `source != 'plaid'`,
  grouped by `to_char(date,'YYYY-MM')`.
- `/transactions/` (`transactions.py:16-68`): `source != 'plaid'`, filters as listed,
  `ilike` search over merchant/category/notes, `count(*)` over the same filtered
  subquery, ordered `date desc`.

When an `account_types` filter is active, rows with `account_id IS NULL`
(email receipts, Plaid) are excluded by construction (`spending.py:26-27`).

How `transactions` get populated:

| Path | Status | What it writes |
|---|---|---|
| seed | real | 428 rows on `cb-checking`, `source='seed'`, categorised |
| SimpleFIN scheduler (`sync_scheduler.py:541-547`) | real, scheduled every 12h, the only provider in `ALL_PROVIDERS` | `account_id` set, `source='simplefin'`, **`category=''`** (renders as "Uncategorized") |
| Email receipts (`email_receipt_service.py:100-108`) | wired (webhook/forwarding routes); not in seed | `source='email_receipt'`, **no `account_id`**, AI-parsed merchant/category, notes carry `email_receipt_id` |
| Monarch scheduler/sync (`sync_scheduler.py:325-331`) | code present, provider disabled | `source='monarch'`, categorised |
| Plaid `/plaid/sync` (`plaid_routes.py:205-212`) | code present, no links | `source='plaid'`, **no `account_id`**, and **excluded by every read on these pages** |
| `POST /transactions/`, `POST /transactions/bulk` | API-key users only; no UI | arbitrary |
| DataExplorer row editor | real (power-user) | arbitrary edits, incl. re-categorising |
| legacy `import_service.py` | no frontend caller found | — |

There is **no categorisation pipeline**: category is whatever the writer supplied.

### 2.4 Verified against seed

Today's presets resolve to: This Month `2026-10-01..2026-10-29`; Last 3 Months
`2026-07-29..2026-10-29`; YTD `2026-01-01..2026-10-29`; Last 12 Months
`2025-10-29..2026-10-29`.

| Call | Status | Result |
|---|---|---|
| `GET /accounts/` | 200 | 8 accounts; `account_type` chips would be `cash (3)`, `credit_card (1)`, `investment_401k (1)`, `investment_stock (1)`, `loan_mortgage (1)`, `real_estate (1)` |
| `GET /spending/by-category?from_date=2026-07-29&to_date=2026-10-29` (default) | 200 | `[]` → blank chart |
| `GET /transactions/?from_date=2026-07-29&to_date=2026-10-29&offset=0&limit=25` (default) | 200 | `total: 0` → "No transactions found" |
| `GET /spending/recurring` (default, cutoff 2026-05-02) | 200 | `[]` → "No recurring expenses detected" |
| `GET /spending/recurring?months=24` | 200 | 15 rows incl. `First National Bank / Transfer 2,450/mo (12 months)` and `Whole Foods / Groceries 84.78` |
| `GET /spending/monthly-trend` | 200 | 14 months 2025-01..2026-02 (e.g. 2025-01 −6,175.44 / 29 txns) |
| 12-month preset: `/spending/by-category?from_date=2025-10-29&to_date=2026-10-29` | 200 | 12 categories; Transfer −7,350 (58 %), Groceries −1,274.26, ... |
| 12-month preset: `/transactions/?...` | 200 | `total: 124`, 25 items, newest 2026-02-23 Uber −19.33 |
| `...&account_types=cash` | 200 | identical to unfiltered (all seed txns are on a cash account) |
| `...&account_types=credit_card` | 200 | `[]` |
| `GET /transactions/?search=Uber&limit=5&offset=0` | 200 | matches |

So with the default preset the seeded Spending page shows **only the Monthly
Spending Trend chart**; the other three sections are empty. No param-name
mismatches on this page.

### 2.5 Broken or suspicious

1. **Date presets do not scope Recurring or Monthly Trend.** `SpendingView.vue:142-143`
   call `fetchRecurring()`/`fetchMonthlyTrend()` with no dates and
   `client.ts:101-108` accept none; recurring is always "last 6 months from today",
   the trend is always all-time. The preset buttons sit in the page header as if
   global.
2. **Transfers and loan payments count as spending.** No category exclusion
   anywhere; the seed's mortgage payment (`Transfer`) is 58-65 % of "spending" and
   tops the category chart and the recurring list. Credit-card payments from a
   SimpleFIN checking feed would be double-counted against the card's own txns.
3. **`avg_monthly` is a per-transaction average** (`spending.py:95,121`) displayed
   as "/mo" (`RecurringList.vue:31`). Whole Foods shows 84.78/mo while the seed
   generates 1-3 Whole Foods txns a month.
4. **Plaid transactions are excluded from every query** (`spending.py:53,102,144`;
   `transactions.py:30,133`) since the initial commit with no recorded rationale,
   while three tooltips say Plaid is included (`SpendingView.vue:234`,
   `TransactionTable.vue:42`, Dashboard `:375`). Plaid rows also have no
   `account_id` (`plaid_routes.py:205-212`).
5. **Search fires a request per keystroke** (`TransactionTable.vue:48`), no
   debounce; chip toggles fire four requests each (`:147`, deep watch).
6. **Chart "loading" state is tied to the wrong request.** `:234` and `:267` use
   `store.loading`, which only tracks `fetchTransactions`; category/trend fetch
   errors are swallowed to `[]` (`transactions.ts:50-72`) and render as blank
   charts with no empty-state message.
7. **Timezone drift in presets.** `getDateRange` builds local dates then
   `toISOString().slice(0,10)` (`:106-129`), which is UTC; in UTC-negative zones
   the "This Month" start can be the previous day for early-morning loads and
   `to` can be tomorrow late evening.
8. **No way to edit or categorise a transaction from this page** even though
   `PUT /transactions/{id}` exists; the only UI path is the generic DataExplorer
   row editor.
9. SQL-viewer strings (`:52-99`) are SQLite dialect and omit the `account_types`
   sub-select, so they do not describe the filtered query.
10. `pct_of_total` returned by `/spending/by-category` is computed on the full
    result but the chart slices to 15; the value is unused.

### 2.6 Must never do (invariants)

- Spending = `amount < 0` only; income rows (positive) never appear in category,
  recurring, or trend aggregates. Sign convention: negative = money out.
- The account-type filter must apply identically to **all four** queries, and
  "All" must mean no filter (not "all listed types"), so that rows with null
  `account_id` (email receipts) reappear.
- Date range is inclusive at both ends; `total` in the transactions response must
  be counted over the same filters as the rows.
- Page size 25; paging never changes the other three sections.
- Account names come from `GET /accounts/` on the same tenant; fall back to the
  raw id, and `—` for null.
- The `source != 'plaid'` exclusion is applied uniformly today; a refactor must
  either keep it everywhere or remove it everywhere (never half).
- Tenant scoping via `get_tenant_db` on all five endpoints.

### 2.7 Interactions with other pages

- Accounts (Settings / sync) supply the chips and the Account column.
- Transactions arrive from Settings → Connections (SimpleFIN today), email
  forwarding, or the API; nothing on the Money pages creates them.
- Category vocabulary is provider-defined; SimpleFIN rows are uncategorised until
  edited in the Database/DataExplorer editor.
- The Dashboard "Last 30 Days" tile and the Cash page's Avg Monthly Spend /
  Notable Transactions read the same table with the same `plaid` exclusion.

---

## 3. Income (`/income`, `frontend/src/views/IncomeView.vue`)

### 3.1 Purpose
"For a given tax year, how did gross pay split into salary/RSU, and where did it go
(taxes, 401(k), benefits, take-home) — and how has that changed year over year?"

### 3.2 Sections (page order)

On mount (`IncomeView.vue:117-131`) the page fetches `GET /income/history` and
`GET /rsu/summary` in parallel; `w2_records` sorted desc; `selectedYear` = newest.
Everything else is computed client-side from the selected `W2Record`.

| # | Section | Shows | Endpoint |
|---|---|---|---|
| 1 | Header + **year selector** buttons (one per W2 `tax_year`) | sets `selectedYear` | `GET /income/history` |
| 2 | **Data** button | DataExplorer on `w2_records` | admin schema/preview |
| 3 | **Import** button | opens unified ImportModal with `context: 'income'`; on close calls `refreshData()` (re-fetches both endpoints) | `POST /import/upload` → review → `POST /import/{session}/confirm` |
| 4 | Loading / error / empty state ("No W2 records found. Add a W2 record in Settings") | — | — |
| 5 | Card **Gross Pay** | `gross_pay`; subtitle `base + RSU [+ other]` (other shown only if > $100) | — |
| 6 | Card **Total Tax** | fed+state+SS+medicare; effective rate = tax/gross | — |
| 7 | Card **401(k)** | pretax+roth; subtitle split | — |
| 8 | Card **Benefits** | cafeteria_125 + transit + employer_health | — |
| 9 | Card **Take-Home** | gross − tax − (pretax_401k+roth_401k+cafeteria_125+transit); % of gross | — |
| 10 | **Compensation Breakdown (year)** (hidden when base and RSU both 0) | CSS stacked bar salary vs RSU as % of gross + legend | — |
| 11 | **Gross to Take-Home (year)** ECharts waterfall | Gross → each non-zero deduction (Federal, State, Soc. Security, Medicare, 401(k) Pretax, 401(k) Roth, Health Ins., Cafeteria/FSA, Transit) → Take-Home | — |
| 12 | **Where Your Gross Pay Goes** stacked bar, all years | Take-Home + 401(k) + Tax + Benefits per year; tooltip adds gross/base/RSU | — |
| 13 | **Comp Split** 100 % stacked bar, all years | Salary / RSU / Other % of gross | — |
| 14 | **Year-over-Year** table | Year, Gross, Tax, Rate, 401(k), Benefits, Take-Home; selected year highlighted | — |
| 15 | `DataExplorer` modal | — | — |

Each card/chart has a View-SQL modal with a `w2_records` query parameterised by
`:selected_year`.

### 3.3 Data flow

`GET /income/history` (`income.py:34-78`) reads all `w2_records` (desc by
`tax_year`) and all `rsu_grants`. The page uses only `w2_records`; `rsu_grants` in
the response and `vesting_income_by_year` from `/rsu/summary` are **fetched and
never read** (`IncomeView.vue:27,122,145`).

How `w2_records` get populated (one row per `tax_year`, unique):

| Path | Status | Fields |
|---|---|---|
| seed | real | all 14 fields for 2023-2025 |
| Settings → Income form (`SettingsView.vue:190-245` → `POST /income/w2`) | real | **only** gross_pay, base_salary, rsu_income, federal_tax, state_tax, pretax_401k, roth_401k (+tax_year). SS, Medicare, cafeteria, transit, employer_health, w2_wages cannot be entered |
| Import modal, context `income` (`import_unified.py:36-60`, confirm → `_apply_w2_changes` `:892-894`) | real (needs `FINANCE_ANTHROPIC_API_KEY`) | any of the 12 `W2_FIELDS` (`:157-162`); upsert by tax_year; pay stubs use YTD lines |
| `PUT /income/w2/{year}`, `DELETE` | API only | — |
| DataExplorer row editor | real | any column |
| legacy `ingest.py` w2/paystub upload | no frontend caller found | — |

### 3.4 Verified against seed

| Call | Status | Result |
|---|---|---|
| `GET /income/history` | 200 | 3 W2 rows (2025, 2024, 2023), 8 grants |
| `GET /rsu/summary` | 200 | has `vesting_income_by_year` 2023..2028 (unused) |

Client-side numbers for the default year 2025 (checked by hand from the response):
Gross 210,000 = 145,000 salary + 65,000 RSU; Total Tax 62,863.20 (29.9 %);
401(k) 15,000; Benefits 11,800; Take-Home 128,936.80 (61.4 %). All sections
populate. No param mismatches (the page sends none).

### 3.5 Broken or suspicious

1. **"Where Your Gross Pay Goes" does not sum to gross.** The stack is
   Take-Home + 401(k) + Tax + Benefits (`IncomeView.vue:330-440`); Take-Home does
   not subtract `employer_health` but Benefits includes it, so the 2025 bar totals
   218,600 vs gross 210,000 (over by exactly employer_health 8,600). The subtitle
   "... = gross pay" is wrong.
2. **Waterfall does not land on its own Take-Home bar.** The running total
   subtracts "Health Ins." (`employer_health`) (`:252-262, 268-282`) reaching
   120,336.80, but the final bar is `takeHome` = 128,936.80. Visually the last
   step jumps up by 8,600.
3. **Benefits tile mixes employer-paid and employee pre-tax items**
   (employer_health is Box 12 DD, not a deduction); the Take-Home tooltip even
   says employer health is not subtracted — the three visuals disagree with each
   other on this one field.
4. **Settings can only enter 8 of 14 fields** (`SettingsView.vue:190-199`), so a
   manually entered year shows Total Tax without FICA, Benefits $0, and an
   overstated take-home. The empty state points users to Settings.
5. **Dead fetch:** `/rsu/summary` is requested on mount and on every import
   completion purely to fill `rsuByYear`, which nothing reads (`:27,122,145`).
   `rsu_grants` in `/income/history` is likewise unused here.
6. `w2_wages` is stored but never displayed anywhere.
7. "Other" compensation (gross − base − RSU) is shown in the Gross Pay subtitle and
   Comp Split but is absent from the Compensation Breakdown stacked bar, which
   then does not fill its width.
8. `years` uses the default `Array.sort()` (lexicographic) on numbers (`:135`);
   fine for 4-digit years, fragile otherwise.
9. All "View SQL" strings on this page use `:selected_year`, which the Database
   runner cannot bind.

### 3.6 Must never do (invariants)

- One row per `tax_year`; creating via the form or import **upserts** by year
  (`income.py:126-146`), never duplicates.
- Null fields are treated as 0 in every computation (`v()`), and a field sent as
  `null` by the Settings form overwrites the stored value (`exclude_unset` only
  skips absent keys) — a refactor must not turn "blank" into "unchanged" silently
  or vice-versa without deciding.
- Take-home formula (today): `gross − (fed+state+SS+medicare) − (pretax_401k+roth_401k+cafeteria_125+transit)`; employer_health is not subtracted. Whatever the spec decides, the five cards, the waterfall, the stacked bar and the YoY table must use **one** definition.
- Year selector scopes cards, breakdown and waterfall only; the two history charts
  and the YoY table always show all years, highlighting the selected one.
- Dashboard Total Comp and Compensation Split read the same table (latest year);
  any change to how base/RSU are stored propagates there.
- Tenant scoping via `get_tenant_db`.

### 3.7 Interactions with other pages

- Settings → Income form (partial fields) and the Import modal are the only UI
  writers.
- Dashboard reuses the latest W2 (Total Comp, Compensation Split).
- Planning engine reads W2 income assumptions (outside this brief) — confirm before
  changing field semantics.
- RSU page owns vest/grant data; the Income page currently ignores it despite
  fetching it.

---

## 4. Cash (`/cash`, `frontend/src/views/CashView.vue`)

### 4.1 Purpose
"How much cash do I have across checking/savings, how is it trending, how many
months of runway is that, and what big transactions moved it?"

### 4.2 Sections (page order)

`loadData()` (`CashView.vue:52-69`) fires four requests in `Promise.all`; changing
the time range re-fetches **only** large transactions (`:71-75`).

| # | Section | Shows | Endpoint + params |
|---|---|---|---|
| 1 | Header: time range **1M / 3M (default) / 6M / 1Y / All** | `days` = 30/90/180/365/9999 | affects #5 (server) and #2/#6 filtering (client) |
| 2 | Header: **Data** button | DataExplorer on `accounts`, `balance_snapshots` | admin schema/preview |
| 3 | Header: **Sync** button | `POST /plaid/sync-balances` and `POST /monarch/sync-balances` in parallel, sums counts, re-fetches `/snapshot`, shows "Synced N accounts." | as listed |
| 4 | Loading / error / "No cash accounts found." (when no layer named `Cash`) | — | `GET /snapshot` |
| 5 | Card **Total Cash** | `layers[name=='Cash'].total`; badge = change over the filtered history (first → last point) | `GET /snapshot`, `GET /trends/net-worth` (no params) |
| 6 | Card **Avg Monthly Spend** | mean of `abs(total)` over the **last N entries** of the monthly trend, N = round(days/30) clamped to [1, len] (`:103-108`) | `GET /spending/monthly-trend` (no params) |
| 7 | Card **Runway** | `round(totalCash / avgMonthlySpend)` months; green ≥6, amber ≥3, red otherwise | derived |
| 8 | Card **Accounts** | count of accounts in the Cash layer | `GET /snapshot` |
| 9 | **Account Breakdown** | donut (positive balances only) + proportional bars with %; colours shared by index | `GET /snapshot` |
| 10 | **Cash Balance & Activity** line chart | `trends.groups['Cash']` filtered client-side to the time range; markPoints for each large txn (pin = out, triangle = in), dashed average line; clicking a marker highlights the table row | `GET /trends/net-worth`, `GET /transactions/large?threshold=500&days={days}&limit=100` |
| 11 | **Notable Transactions (>$500)** table (only if any) | Date, Account, Merchant, Amount, Category; sticky header, 100 max | same `/transactions/large` |
| 12 | **All Accounts** expandable list | per account: colour dot, name, (institution), balance, % of cash; expand → paged table of its transactions, 25/page, Prev/Next | `GET /transactions/?account_id={id}&limit=25&offset={page*25}` |
| 13 | `DataExplorer` modal | — | — |

### 4.3 Data flow

- `/snapshot` — see Dashboard. The Cash page uses the layer whose **display name
  is exactly `Cash`** (`:78`).
- `/trends/net-worth` (`trends.py:15-65`) — all `balance_snapshots` for active,
  `include_in_nw` accounts, keyed by raw `display_group`; the page reads
  `groups['Cash']` (`:114`).
- `/spending/monthly-trend` — `transactions`, `amount<0`, `source!='plaid'`, all
  time.
- `/transactions/large` (`transactions.py:118-158`) — `transactions` with
  `date >= today−days`, `abs(amount) >= threshold`, `source!='plaid'`, newest
  first, `limit`; `account_name` looked up from `accounts`, falling back to the
  `source` string for null `account_id` (email receipts show "email_receipt").
- `/transactions/?account_id=` — see Spending.
- Sync: `POST /plaid/sync-balances` (`plaid_routes.py:280`) writes
  `balance_snapshots(source='plaid')` for linked Plaid items;
  `POST /monarch/sync-balances` (`monarch_routes.py:389`) writes
  `source='monarch'` for configured Monarch accounts. **SimpleFIN — the only
  provider the scheduler runs (`sync_scheduler.py:34`) — is not triggered by this
  button**; it syncs from Settings or on the 12-hour schedule.

Population of `balance_snapshots`, `transactions`, `accounts`: see tables in 1.3
and 2.3.

### 4.4 Verified against seed

| Call (as sent, default 3M) | Status | Result |
|---|---|---|
| `GET /snapshot` | 200 | Cash layer: Savings 14,954.56, Checking 9,681.88, HYSA 5,081.71 → Total Cash 29,718.15, Accounts 3 (balance date 2026-03-01, not displayed) |
| `GET /transactions/large?threshold=500&days=90&limit=100` | 200 | `[]` → no markers, no Notable table |
| `...days=365` (1Y) | 200 | 9 rows: paychecks +5,576.92 and mortgage −2,450 (2025-11..2026-01) |
| `...days=9999` (All) | 200 | 42 rows |
| `GET /trends/net-worth` | 200 | 15 points; `groups.Cash` 30,000 → 29,718.15 |
| `GET /spending/monthly-trend` | 200 | 14 months |
| `GET /transactions/?account_id=cb-checking&limit=25&offset=0` | 200 | total 428, 25 items |
| `...account_id=cb-savings` / `cb-hysa` | 200 | total 0 → "No transactions found." |
| `POST /plaid/sync-balances` | 200 | `{"accounts": [], "detail": "No Plaid links found"}` |
| `POST /monarch/sync-balances` | 200 | `{"synced": 0, "detail": "No Monarch connection"}` → banner "Synced 0 accounts." |

Client-side at 3M today: the cutoff 2026-07-31 is later than the last snapshot
(2026-03-01), so `filteredHistory` falls back to the **entire** 15-point series
(`:120-121`); the Total Cash badge shows the all-time change (−281.85, −0.9 %);
Avg Monthly Spend averages the last 3 months with data (2025-12..2026-02, the last
being a partial month). No param-name mismatches on this page.

### 4.5 Broken or suspicious

1. **Time range silently falls back to "All" when data is stale.**
   `CashView.vue:112-123`: if no snapshot date ≥ cutoff, `startIdx < 0` and the
   full history is used, while the label still says "3M". Same for the change
   badge.
2. **Avg Monthly Spend ignores the selected dates.** It takes the last N entries
   of the all-time monthly series (`:103-108`), i.e. "the N most recent months
   that have any data", including partial months and `Transfer`/mortgage rows,
   and excluding nothing. Tooltip says "over the selected period". Runway inherits
   this.
3. **Sync button covers the wrong providers.** It calls Plaid + Monarch
   (`:125-129`); Monarch is hidden/disabled and SimpleFIN (the live provider) is
   not called. With no links it reports success ("Synced 0 accounts.").
4. **`account.institution` is never shown** (`:~447`): `LayerAccount` only has
   `id/name/balance` (`schemas/snapshot.py:6-9`).
5. **Total Cash vs chart can disagree.** Layer totals include every active account
   regardless of `include_in_nw` (`snapshot_service.py:96-97`) but the trend
   series excludes `include_in_nw=false` accounts (`trends.py:29`).
6. **Depends on the literal strings `'Cash'`** in two differently-normalised
   endpoints (`:78`, `:114`); see Dashboard item 13.
7. **Marker→row highlight index bug (latent).** `:~170` maps over the
   date-filtered list, so `_txnIdx` is the index in the filtered array while rows
   are keyed by index in the unfiltered `largeTransactions`; wrong row highlighted
   whenever a notable txn falls outside the chart's date span.
8. **"Notable" includes paychecks**; with the seed, 2/3 of markers are income.
   Threshold 500 is hard-coded in the URL and the heading.
9. **Expanded account transactions ignore the time range** and the Spending
   page's `plaid` exclusion applies.
10. **No "as of" date anywhere** although `GET /accounts/` exposes
    `balance_date` (2026-03-01 here); a user cannot tell the balances are stale.
11. **Variable `cashFlow` holds monthly spending**, not `/trends/cash-flow`;
    `GET /trends/cash-flow`, `api.getCashFlow` and `stores/trends.ts` are unused
    by any view (dead from these pages' perspective).
12. **Runway rounds to whole months** and divides by a possibly-partial-month
    average; colour thresholds (3/6) are hard-coded.
13. Monthly snapshots mean markPoints for many transactions collapse onto the
    same x (nearest snapshot), stacking pins.
14. Error handling: `trends`/`monthly-trend` failures are swallowed to
    `null`/`[]` (`:59-60`); snapshot/large failures set `error` and hide the page.

### 4.6 Must never do (invariants)

- "Cash" is exactly the `Cash` liquidity layer (checking/savings/HYSA);
  credit cards, brokerage, retirement never contribute to Total Cash, the donut,
  or runway.
- Balances are latest-snapshot-per-account; the breakdown percentages and the
  Accounts count are over the same list as Total Cash.
- Runway = Total Cash ÷ average monthly *expenses* (negative amounts only); never
  net of income.
- The time-range control must apply to the balance chart, the change badge, the
  notable transactions and (per its tooltip) the average spend — today it only
  truly scopes notable transactions.
- Sync is the only mutating action on the page and must only write
  `balance_snapshots` for the current tenant; it must never create transactions
  or change account metadata.
- Expanded account lists are scoped by `account_id` of a Cash-layer account on the
  same tenant; paging is 25 with a correct `total`.
- Tenant scoping via `get_tenant_db` on all six endpoints.

### 4.7 Interactions with other pages

- Settings → Accounts decides which accounts are `display_group='Cash'`,
  `is_active`, `include_in_nw`.
- Settings → Connections (SimpleFIN today) is the real source of fresh
  balances and transactions; the Cash page's own Sync button does not reach it.
- Spending page shares `transactions` semantics (negative = spend, `plaid`
  excluded, Transfers included) → Avg Monthly Spend equals the last bars of the
  Spending page's Monthly Trend chart.
- Dashboard's Cash layer, Liquid Net Worth and Net Worth Over Time use the same
  two endpoints; any normalisation change must be made in both
  `snapshot_service.py` and `trends.py`.

---

## Cross-page summary for the spec author

- Three distinct "sources of truth" are mixed on the Money pages: latest
  `balance_snapshots` (net worth, cash), `property_valuations`+`mortgages`
  (Property Equity card), and `w2_records` (comp). Decide which wins where.
- Every spending aggregate on all pages: `amount < 0`, `source != 'plaid'`,
  Transfers included, no category exclusion, categories provider-defined
  (SimpleFIN = blank).
- Date-range controls are partial on Spending (2 of 4 sections) and Cash (1 of 4
  sections), and absent on Dashboard; the Dashboard's only "window" is mis-wired.
- Manual entry today: accounts and a partial W2 in Settings; everything else is
  seed, SimpleFIN, AI import, API, or the generic DataExplorer row editor.
- Freshness is invisible: no page shows the balance/transaction "as of" date even
  though the API returns it.
