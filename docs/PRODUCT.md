# Tallied — Product Definition

This is the source of truth for what Tallied is. It supersedes `docs/archive/` (the March 2026 vision, import-workflow, security-audit and deployment documents), which remain useful background but are not binding. The per-requirement list lives in `docs/requirements/ledger.yaml`; how the code is organised lives in `docs/ARCHITECTURE.md`.

Drafted 2026-10-29 from the code as it runs today (the as-built briefs in `docs/research/as-built-2026-10/`) and the October review (`docs/REVIEW-2026-10-29.md`). Decisions taken while drafting are listed at the end for the owner (Mark Cheli) to confirm or change.

## What it is

Tallied is the finance dashboard for one household: Mark's. It holds the household's accounts, transactions, income, company stock, 401(k), house and vehicles in one PostgreSQL database that the owner can also open with psql or a spreadsheet, shows what that adds up to, and projects it forward to retirement.

It is not a product. There is no second customer, no pricing, no onboarding funnel. The multi-tenant structure, admin portal and API keys exist because they were built in March and because tenant-per-schema is a clean way to keep data isolated; they must keep working, but they are not where effort goes. Anything that only makes sense for a general audience is out of scope.

That cuts both ways. Choices can be specific to this household where it helps (Massachusetts tax rates, one employer's RSU conventions, the brokerages actually in use), as long as they are explicit and data-driven rather than hard-coded into views. The Claudius Banks persona remains the fixture for every test and screenshot so that nothing real is ever committed.

## Five jobs, in priority order

### 1. Look: what am I worth, and what changed

- The Dashboard answers it in one screen: net worth, liquid net worth, the liquidity layers (cash, investments, home equity, retirement, liabilities), compensation split, net worth over time, the next RSU vests, and recent spending.
- Every number on it comes from one source of truth per concept (see "One source of truth" below), so two tiles never disagree about the same thing.
- Every balance shows how fresh it is. Stale data is visible, not hidden.

### 2. Feed: get data in with the least typing

- **SimpleFIN** syncs bank and card accounts, balances and transactions on a schedule and on demand. It is the only live bank connection and the reference for any future provider.
- **Document import** uses Claude to read W-2s, pay stubs, mortgage statements, 401(k) statements and E-Trade RSU exports, proposes changes, and writes nothing until the owner confirms them in the review step.
- **Email receipts** forwarded to the household's receipt address become transactions, attributed to a sender address the owner registered.
- **Manual entry** covers everything else: accounts, W-2 fields, vehicles, property valuations, plan assumptions, and a row editor on the Database page for corrections.
- Removed in October 2026: Monarch (no API, reverse-engineered client behind bot protection, see `docs/research/monarch-postmortem.md`) and Plaid (never configured; its transactions were filtered out of every view). Either can return later as a provider behind the provider interface.

### 3. Understand: where the money is and where it goes

Seven pages, each answering one question:

- **Spending**: where did money go in a period, what recurs, how does the monthly total trend. All four sections obey the same date range and account filter.
- **Income**: for a tax year, how gross pay splits into salary and RSU, where it goes (tax, 401(k), benefits, take-home), and how that changed year over year. One definition of take-home used by every tile and chart.
- **Cash**: checking and savings balances, their trend, months of runway, and the notable transactions behind the movements.
- **RSU**: what the company stock is worth, what selling the vested shares today would net after tax, when the rest vests, and every grant's history.
- **401(k)**: balance and its Roth/pre-tax/match split, contribution rates, holdings with live prices, balance history from statements.
- **Property**: value, mortgage balance, equity, the amortization schedule and the payment split, with a value history the owner controls.
- **Assets**: vehicles with a labelled estimated value, depreciation since purchase, and value history.

### 4. Plan: will this work out

- **Planning** projects the household year by year to a target retirement age from the current balances, income and a set of editable assumptions, compares scenarios, and shows which assumptions matter most (sensitivity). Projection maths is deterministic and tested; the page explains every column.

### 5. Platform: keep it running and open

- **Database** page: the schema as an ERD, a read-only SQL runner restricted to the household's schema, table previews, column documentation, and direct-connection credentials for psql or Excel.
- **API** page: API keys with enforced read/write scopes, the OpenAPI reference, usage, and outbound webhooks only if delivery actually fires.
- **Settings**: accounts, income records, connections, email receipt addresses, import history.
- **Admin Portal**: user approval and tenant management. Admin only. Exists; not invested in.
- **Guide**: the in-app tour of every page, kept in step with this document.

## Pages: what each shows, what feeds it, what it must never do

**Dashboard.** Shows net worth and liquid net worth (latest balance per active account, honouring `include_in_nw`), the liquidity waterfall, compensation split from the latest W-2, net worth over time by layer, the next four vests, last-30-day spending by category, and account details per layer. Fed by balance snapshots, W-2 records, RSU grants and the live stock price. Must never show a layer total that disagrees with the net worth tile, show "30 days" while summing all time, or hide the date of the balances it shows. Performs no writes.

**Spending.** Shows spending by category, recurring merchants, the transaction table and the monthly trend for one date range and one account-type filter. Fed by transactions from SimpleFIN, email receipts, manual entry and (for tests) the seed. Spending is negative-amount transactions excluding transfers and loan payments (see decision D1). Must never apply the range to some sections and not others, count income as spending, or show an empty chart without saying the period is empty.

**Income.** Shows the selected tax year's gross, tax, 401(k), benefits and take-home, the gross-to-take-home waterfall, and all-year history. Fed by W-2 records from import or the Settings form (which must expose every W-2 field the page uses). Must never let the five tiles, the waterfall and the stacked bar use different take-home definitions; one row per tax year, upserted.

**Cash.** Shows the Cash layer's total, average monthly spend, runway, the per-account breakdown, the balance line with notable transactions marked, and per-account transaction lists. Fed by balance snapshots and transactions. The time range scopes every section. The Sync button syncs the live provider (SimpleFIN) or is absent. Must never fall back to "all time" while the control says "3M", or count income in average spend.

**RSU.** Shows holdings value, sellable and unvested value, unrealized gain, the stock price history for the grants' symbol, the sell-today tax estimate, upcoming vests, vest value by year, and every grant with its vest events. Fed by grants and vest events from import, and Yahoo Finance for prices (cached per day). Must never plot a different symbol than the grants carry, silently drop sellable shares it cannot allocate to lots, or value shares the owner cannot sell as if they were held.

**401(k).** Shows total balance, return, Roth and pre-tax balances, estimated retirement income, the balance breakdown, contribution rates (editable), holdings with live prices, balance history and lifetime contributions. Fed by statement import; rates by the page. Must never let an older statement overwrite a newer one, or let lifetime totals decrease. One account per household.

**Property.** Shows value, mortgage balance, equity, rate, payment, value over time, equity composition, the amortization schedule and the payment split. Fed by mortgage statement import, manual valuations, optional Realtor.com lookups, and AI projections stored as labelled estimates. Must never delete a valuation the owner typed, label the down payment as appreciation, or let a projected value feed equity or net worth.

**Assets.** Shows each vehicle with its estimated value, depreciation and value history, plus totals. Fed by the Add Vehicle form and AI valuation on request. Every AI value is labelled as an estimate with its date and reasoning; a failed valuation is shown as failed, never as success. Must never subtract values of vehicles without a purchase price from "depreciation", or block adding a vehicle on the AI call.

**Planning.** Shows one or more plans, each with assumptions (growth, returns, contributions, spending, retirement age), a year-by-year projection table and chart, milestones, sensitivity and scenario comparison. Fed by the household's current balances, latest W-2, mortgage and RSU vest schedule, plus the plan's own assumptions. Must never silently skip projection on an engine error, and must say which real figures seed the plan.

**Database.** Shows the ERD, table previews, column descriptions, the SQL runner and direct-access credentials. Desktop only; on a phone it says so instead of rendering a broken canvas. The runner must never reach another schema, platform tables or superuser functions.

**API.** Shows keys, usage, the reference, webhooks. A read key must never be able to write.

**Settings.** Accounts (name, type, group, active, in net worth), income records (all fields), SimpleFIN connection and per-account sync options, email forwarding addresses and receipt log, import history. Must never show a connection tab for a provider that does not work.

## One source of truth

Today the same quantity lives in several tables and pages disagree. The rule going forward:

| Concept | Source of truth | Everything else |
|---|---|---|
| Account balances, net worth, layers, Planning starting balances | latest `balance_snapshots` row per active account | Property value and 401(k) statement balance write a snapshot for their account when they change (decision D2) |
| Property value | latest `property_valuations` row | `property_value_histories` is the chart's history, fed from valuations and lookups; never the other way |
| 401(k) balance | `retirement_accounts` from the newest statement | writes a snapshot to the 401(k) account |
| Stock price | one `stock_prices` row per symbol per day, source Yahoo | seed rows are not overwritten in tests |
| Compensation | latest W-2 record | Planning reads the same row |
| Spending | transactions with negative amounts, excluding transfer and loan-payment categories | Dashboard, Spending, Cash all use one query helper |

## Data sources and their status

| Source | Status 2026-10-29 | Notes |
|---|---|---|
| SimpleFIN | live, verified against real accounts | credentials encrypted at rest; account type chosen at connect |
| Document import (W-2, pay stub, mortgage, 401(k), E-Trade) | live, needs `FINANCE_ANTHROPIC_API_KEY` | structured outputs; review before write |
| Email receipts | wired end to end, unverified in production | attribution by registered sender; auto-insert kept (decision D4) |
| Manual entry | live | Settings, page forms, Database row editor |
| Yahoo Finance prices | live | cached once per day per symbol |
| Realtor.com (RapidAPI) | optional, not configured | failure is reported, never silent |
| AI valuations (vehicles, property projections) | kept as labelled estimates | async, never written as fact |
| Monarch | removed | post-mortem in `docs/research/` |
| Plaid | removed | re-add as a provider if ever needed |
| Seed (`make seed-test`) | live | the Claudius fixture; dates relative to today so default periods have data |

## Rules that are never broken

1. No success message for something that did not happen. A failed valuation, sync or import says so. An unimplemented action is not shown.
2. AI output is never saved without review or without a label. Imports stage changes for confirmation; valuations are stored with source, date and reasoning.
3. Every number on a page can be explained: an InfoTooltip says what it is and what feeds it, and the explanation is true.
4. One definition per concept (table above). A refactor that touches one reader updates all readers.
5. Financial routes use the tenant session; nothing from a request is interpolated into SQL; the SQL runner cannot leave the household's schema.
6. Secrets and provider credentials live only in environment variables or encrypted columns. Nothing personal is committed; Claudius is the only persona in fixtures, tests and screenshots.
7. Every schema change ships a migration that iterates all tenant schemas, and the chain builds an empty database.
8. A requirement is done only with evidence: an automated test on the real code path, and a screenshot from the tour for anything visible. The ledger is updated in the same commit.
9. The app works on a phone: no page scrolls sideways; anything that cannot work on a phone says so.

## Explicitly later or never

- **Never** (unless the owner changes this document): billing, invitations, public sign-up, per-tenant plans, a public API programme, multi-currency.
- **Later**: a second bank provider through the provider interface; a review queue for email receipts; categorisation rules for SimpleFIN transactions; investment accounts beyond RSU and 401(k); a native mobile app (responsive web first).

## Decisions taken while drafting (confirm or change)

- **D1 Spending excludes transfers and loan payments.** Today the mortgage payment is 58 to 65 percent of "spending" on every chart. The category `Transfer` and any category in a small exclusion list stop counting as spending everywhere.
- **D2 Property and 401(k) write balance snapshots.** The Property and 401(k) pages' figures become the figures net worth and Planning use, by writing a snapshot for their account whenever they change. Until then the Dashboard shows two different home-equity numbers.
- **D3 Seed dates are relative to today.** The seed's transactions and snapshots end in February 2026, so every "last 3 months" default is empty. The seed shifts its calendar so the latest month is the current one.
- **D4 Email receipts stay auto-insert** (per the October triage), but attribution comes from a registered sender address matched against the SMTP envelope, not a forgeable `From:` line in the body.
- **D5 Hard-coded household residue is removed, not re-labelled.** `PTC`, `T. Rowe Price`, escrow `842`, origination `2022-03-31`, the previous owner's figures in tooltips. Where a value is genuinely household-specific (state tax rate), it becomes a setting with a default.
- **D7 Planning takes its ages from the plan, not from `config.yaml`.** `current_age` and `retirement_age` become plan assumptions seeded from a household profile setting; the engine and the table's year range read the same values, and `config.yaml` goes away. One assumption vocabulary replaces the two that exist today.
- **D8 The multi-tenant and platform code is frozen, not removed.** Admin portal, API keys, direct DB credentials and the tenant switcher stay as they are, get the security fixes, and get no new features.
- **D6 Dead write paths are deleted rather than given UI.** Routes nothing calls (legacy ingest, legacy import, E-Trade loader, transaction POSTs, plan actuals and forecasts, property estimate endpoints) go away. If a need appears, it comes back through the spec.
