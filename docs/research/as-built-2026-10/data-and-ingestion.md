# Tallied — Data model and ingestion paths (as of 2026-10-29)

Read-only investigation of `/Users/mcheli-mini/repos/tallied` at commit `fe1b3e1` on branch `punchlist/2026-10`, plus live queries against the local Postgres (`postgresql://tallied:tallied_dev@localhost/tallied`). No repo files were changed by this investigation. Note: while this brief was being written, other work in the same checkout left uncommitted edits (`.github/workflows/ci.yml`, `Makefile`, `frontend/package*.json`) and new untracked files (`backend/tests/test_ledger_check.py`, `scripts/ledger_check.py`, `scripts/screenshot_tour.mjs`, `artifacts/`). Everything below is against the committed tree unless stated.

Paths are relative to the repo root unless absolute.

---

## 0. One-screen summary

- **Two schemas exist**: `public` (10 tables, 9 models + `alembic_version`) and `tenant_claudius` (30 tables, 30 models). Every model has a table and every table has a model. 39 model classes map to 39 tables; `MonarchSyncJob` is an alias of `SyncJob`, not a table.
- **All tenant data today is seed data**: 428 transactions and 120 balance snapshots, every one with `source='seed'`. Zero rows in every provider, import, sync, email, forecast, and history table.
- **Live ingestion paths (reachable from the UI and working)**: (1) Unified AI import for the four typed contexts; (2) SimpleFIN connect + sync (manual button, 12h scheduler, NOTIFY); (3) manual CRUD (accounts, W2s, vehicles, property valuations, plans, retirement rates, generic row editor on the Database page); (4) AI valuation refreshes (vehicles, property history); (5) the seed script.
- **Reachable from the UI but broken or hollow**: Plaid (buttons exist; needs credentials; transactions it inserts are filtered out of every list by `source != 'plaid'`), Monarch sync-balances on the Cash page (tab hidden, routes still live), `GET /import/log` (404s on every Settings load), unified import `general` context (parses but can never write anything).
- **Email receipts**: backend and Cloudflare worker are complete and wired, but the worker config targets `money.markcheli.com`; whether it is deployed cannot be determined from the repo. No rows in `email_receipts` or `email_forwarding_addresses` locally.
- **Dead (no caller anywhere)**: `api/ingest.py` (708 lines, Chrome-extension era), `api/import_data.py` + `services/import_service.py` + `parsers/{etrade,mortgage,student_loan,generic}.py` (legacy JSON import), `loaders/etrade_rsu.py` + `POST /rsu/reload` (also 500s: pandas not installed), `POST /retirement/upload-statement`, `POST /plans/actuals`, `POST /plans/forecasts/generate`, `api/mock.py`, `backend/load_monarch_data.py`, `backend/mcp_server.py`, `scripts/migrate_sqlite_to_postgres.py`, `services/webhook_service.deliver_webhook`, `engine/{cash_flow,net_worth,sensitivity,spending,variance}.py`, `PUT /property/mortgage`, `PUT /retirement/account`, `POST /transactions/` and `/bulk`, `POST /property/estimate` and `/zillow-estimate`, the whole legacy `/api` mount.
- **Scheduler**: runs in-process in the web container (no `APP_ROLE` set anywhere in docker/compose/docs), one 12h loop gated by an advisory lock plus a LISTEN loop on channel `tallied_sync`. `ALL_PROVIDERS = ("simplefin",)`. Monarch remains registered in the dispatch table.
- **Alembic**: linear chain of 9 revisions, head `f6a7b8c9d0e1` (live DB is stamped there). A fresh `alembic upgrade head` on an empty DB fails at revision 4 (`a1b2c3d4e5f6`) because no migration ever creates `users`/`tenants` or the other platform tables, and revisions 1–3 create the financial tables in `public`, not in tenant schemas.
- **Tests**: 41 unit tests pass (smoke GETs, Monarch route boundary, rate limiter); 101 e2e tests are deselected by `addopts = -m "not e2e"`; running them errors immediately because the e2e conftest inserts a `users` row without the NOT NULL `status` column.

---

## A. Data model

### A.1 Where tables live

`backend/app/services/tenant_service.py:7` is the only thing that decides schema placement:

```python
PLATFORM_TABLES = {"users", "tenants", "tenant_memberships", "api_keys", "api_usage_logs",
                   "db_credentials", "webhook_subscriptions", "audit_logs", "alembic_version",
                   "email_forwarding_addresses"}
```

Everything not in that set is a tenant table. No model carries a `schema=` argument. Platform tables are created by `Base.metadata.create_all(tables=platform_tables)` in the FastAPI lifespan (`backend/app/main.py:80-84`); tenant tables by `create_tenant_schema()` (`tenant_service.py:10-18`), which does `CREATE SCHEMA`, `SET search_path`, then `create_all` of the non-platform tables. `backend/app/database.py` resets `search_path` to `public` on every pool checkout.

### A.2 Live inventory (psql, 2026-10-29)

**public** (10 tables)

| table | rows | model |
|---|---|---|
| alembic_version | 1 (`f6a7b8c9d0e1`) | — |
| api_keys | 0 | ApiKey |
| api_usage_logs | 19 | ApiUsageLog |
| audit_logs | 4 (all `login`/`user`) | AuditLog |
| db_credentials | 0 | DbCredential |
| email_forwarding_addresses | 0 | EmailForwardingAddress |
| tenant_memberships | 1 | TenantMembership |
| tenants | 1 (`tenant_claudius`, active) | Tenant |
| users | 1 | User |
| webhook_subscriptions | 0 | WebhookSubscription |

**tenant_claudius** (30 tables)

| table | rows | notes |
|---|---|---|
| accounts | 8 | ids `cb-*`; 3 cash, 1 credit_card, 1 investment_stock, 1 investment_401k, 1 loan_mortgage, 1 real_estate |
| balance_snapshots | 120 | all `source='seed'`, 2025-01-01 .. 2026-03-01 (monthly × 8 accounts) |
| transactions | 428 | all `source='seed'` |
| w2_records | 3 | tax years 2023–2025 |
| rsu_grants | 8 | |
| vest_events | 24 | |
| stock_prices | 1 | |
| mortgages | 1 | |
| property_valuations | 1 | |
| retirement_accounts / retirement_holdings / retirement_snapshots | 1 / 1 / 1 | |
| vehicles | 2 | |
| plan_versions / plan_assumptions / plan_projections | 1 / 15 / 58 | "Retire at 60", base |
| actual_snapshots, forecasts, contribution_configs | 0 | |
| asset_value_histories, property_value_histories | 0 | |
| import_logs, import_sessions | 0 | |
| email_receipts | 0 | |
| monarch_links, monarch_account_configs | 0 | |
| plaid_links | 0 | |
| simplefin_links, simplefin_account_configs | 0 | |
| sync_jobs | 0 | |

Model ↔ table comparison: exact match in both schemas. `backend/app/models/__init__.py` registers all 39 classes. `MonarchSyncJob = SyncJob` (`backend/app/models/sync_job.py:50`) is a back-compat alias; there is no `monarch_sync_jobs` table any more (renamed by migration `f6a7b8c9d0e1`).

### A.3 Per-model brief and reader/writer matrix

Conventions: paths under `backend/app/` unless noted; `seed` = `scripts/seed_test_data.py`; `repro` = `scripts/repro_monarch_500.py`. Two generic access paths apply to **every tenant table** and are omitted from the per-table lists: `api/schema.py` (`/admin/tables/{t}/rows` POST/PUT/DELETE, `/admin/tables/{t}/preview`, `/admin/query` read-only; the Database page's DataExplorer) and `api/admin.py` (`/admin/tables` counts, `/admin/tables/{t}` listing). Platform tables are not reachable through those.

#### Public (platform) schema

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `User` → `users` | one login identity | `id`, `email` (unique), `password_hash`, `display_name`, `auth_provider` (local/google), `is_admin`, `is_active`, `status` (active/pending_approval/suspended; Python default only, NOT NULL in PG), `last_login` | `dependencies.py`, `api/auth.py`, `api/platform_admin.py` | `api/auth.py` (Google/dev login create, `/seed-users` :466, `last_login`), `api/platform_admin.py` (status/is_active), seed |
| `Tenant` → `tenants` | one household/workspace owning a `tenant_*` schema | `id`, `slug` (unique), `display_name`, `schema_name` (unique), `is_active`; `validate_schema_name()` | `dependencies.py`, `api/auth.py`, `api/tenants.py`, `api/platform_admin.py`, `api/email_import.py` | `api/auth.py:126` (auto-create on first login), `api/tenants.py:51`, `api/platform_admin.py:140,273`, seed |
| `TenantMembership` → `tenant_memberships` | a user's role in a tenant | `user_id` FK, `tenant_id` FK, `role` (owner/viewer), `is_default` | `api/auth.py`, `api/tenants.py`, `api/platform_admin.py` | `api/auth.py:136`, `api/tenants.py:61`, `api/platform_admin.py:150,397` (delete :420), seed |
| `ApiKey` → `api_keys` | a hashed programmatic key scoped to user+tenant | `user_id`, `tenant_id`, `name`, `key_prefix`, `key_hash` (unique, HMAC-SHA256 + pepper), `permissions`, `is_active`, `last_used` | `dependencies.py`, `middleware/usage_logger.py`, `api/api_keys.py`, `api/platform_admin.py` | `api/api_keys.py` (create/revoke), `dependencies.py:84` (`last_used`) |
| `ApiUsageLog` → `api_usage_logs` | one logged v1 API request | `api_key_id` FK?, `user_id`, `tenant_id`, `method`, `path`, `status_code`, `latency_ms`, `timestamp` | `api/api_keys.py` (usage stats) | `middleware/usage_logger.py:86` only |
| `DbCredential` → `db_credentials` | a direct-Postgres role granted on a tenant schema | `user_id`, `tenant_id`, `pg_username` (unique), `access_level`, `name`, `is_active`, `expires_at` | `api/db_credentials.py`, `api/platform_admin.py` | `api/db_credentials.py:115` (+ `CREATE ROLE`/`GRANT`/`DROP ROLE` via `services/db_credentials.py`) |
| `WebhookSubscription` → `webhook_subscriptions` | a delivery URL + event filter for a tenant | `user_id`, `tenant_id`, `url` (unvalidated str), `events` (comma string), `secret`, `is_active`, `last_delivery`, `failure_count` | `api/webhooks.py`, `services/webhook_service.py` | `api/webhooks.py` CRUD; `webhook_service.py:61-69` only from `send_test_event`. **`deliver_webhook` has no caller** — no real event is ever delivered; CRUD-only table |
| `AuditLog` → `audit_logs` | one security event | `user_id` (no FK), `action`, `resource_type`, `resource_id`, `details`, `ip_address`, `timestamp` | **none** (no SELECT anywhere; not reachable via the tenant-scoped admin endpoints) | `services/audit_service.log_event` ← `api/auth.py`, `api/platform_admin.py`, `api/import_unified.py:409` |
| `EmailForwardingAddress` → `email_forwarding_addresses` | a personal email mapped to user+tenant for receipt forwarding | `user_id`, `tenant_id`, `email` (unique, indexed), `is_active` | `api/email_forwarding.py`, `services/email_receipt_service.py:40` (← `api/email_import.py`) | `api/email_forwarding.py` (create/delete) |

#### Tenant schema — core ledger

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `Account` → `accounts` | one financial account | `id` String PK (provider prefix encodes source: `monarch-`/`simplefin-`/`plaid-`, seed uses `cb-`; **no provider column**), `name`, `institution`, `account_type`, `display_group`, `include_in_nw`, `is_active`, `opened_date`/`closed_date` | api: `accounts`, `transactions`, `spending`, `trends`, `planning`, `ingest`, `property`, `import_unified`, `admin`; services: `snapshot_service`, `planning_service`, `sync_scheduler`, `import_service` | `api/accounts.py:120` (create; delete :234), `api/property.py:50,240,367,500` (auto real_estate), `api/import_unified.py:916` (mortgage acct), `api/plaid_routes.py:332`, `api/monarch_routes.py:443`, `sync_scheduler.py:153,286,455`, `import_service.py:165,362`, seed, `load_monarch_data.py:86` |
| `BalanceSnapshot` → `balance_snapshots` | one account's balance on one date from one source | `account_id` FK, `snapshot_date`, `balance` Numeric(19,4), `source`; unique (account_id, snapshot_date, source); `ix_balance_account_date` | api: `accounts`, `trends`, `planning`, `ingest`, `admin`; services: `snapshot_service`, `planning_service`, `sync_scheduler` (raw SQL :190), `import_service` | `sync_scheduler.py:172,209,481`, `monarch_routes.py:468,504`, `plaid_routes.py:355`, `accounts.py:258` (manual POST; cascade delete :217), `import_service.py:179,376,451`, seed, `load_monarch_data`, repro (raw DELETE) |
| `Transaction` → `transactions` | one ledger transaction | `id` String PK (provider-prefixed; `email-*`), `account_id` FK **nullable**, `date`, `amount` Numeric(19,4), `merchant`, `category`, `category_group`, `is_recurring`, `notes`, `source`; idx date, (category,date) | api: `transactions`, `spending`, `accounts` (count), `admin`, `plaid_routes`; services: `sync_scheduler`, `import_service` | `api/transactions.py:74,100` (create/bulk; update; delete :196), `sync_scheduler.py:325,541`, `plaid_routes.py:205` (update/delete :217-236), `email_receipt_service.py:100`, `import_service.py:187,384`, `accounts.py:218` (cascade), seed, `load_monarch_data` |

#### Tenant schema — income and RSU

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `W2Record` → `w2_records` | one tax year's W-2 figures | `tax_year` (unique), `gross_pay`, `w2_wages`, federal/state tax, `social_security`, `medicare`, `pretax_401k`, `roth_401k`, `base_salary`, `rsu_income`, `employer_health`, `transit`, `cafeteria_125` | `api/income`, `api/ingest`, `api/planning:565`, `api/import_unified`, `planning_service:67`, `snapshot_service:112` | `api/income.py:141` (upsert; delete :185), `api/ingest.py:654`, `api/import_unified.py:894`, seed |
| `RSUGrant` → `rsu_grants` | one RSU grant | `id` String PK (grant number), `company`, `symbol`, `grant_date`, total/vested/unvested/sellable shares, `share_price` | `api/rsu`, `api/income:42`, `api/planning:587`, `api/import_unified`, `loaders/etrade_rsu` (`planning_service` imports but never uses) | `api/rsu.py:153` CRUD, `import_unified.py:1116`, `loaders/etrade_rsu.py:132`, seed |
| `VestEvent` → `vest_events` | one vest tranche | `grant_id` FK, `vest_date`, `vest_period`, `shares`, `fmv_at_vest`, `shares_withheld`, `shares_released`, `total_taxes_paid`, `is_actual`, legacy `vest_price` | `api/rsu` (+ relationship), `api/planning:584`, `api/import_unified`, `loaders/etrade_rsu` | `import_unified.py:1169`, `etrade_rsu.py:198`, `rsu.py:211` (delete), seed |
| `StockPrice` → `stock_prices` | one symbol's close on a date | `symbol`, `price_date`, `close_price`, `source` (yahoo/etrade/seed); unique (symbol, price_date) | `services/stock_price.py` (`get_or_fetch_price` ← `api/rsu`, `api/planning:583`), `loaders/etrade_rsu` (`api/rsu` imports, unused) | `stock_price.py:70` (delete :66; Yahoo fetch), `etrade_rsu.py:234`, seed |

#### Tenant schema — property and assets

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `Mortgage` → `mortgages` | the mortgage loan (code always takes the latest row) | `account_id` FK, `rate`, `monthly_payment`, `origination_date`, `original_amount`, `original_payoff_date`, `current_balance`, `escrow`, `property_address` | `api/property`, `api/ingest`, `api/import_unified`, `api/planning:577`, `api/accounts` (count), `planning_service:75` | `ingest.py:686`, `import_unified.py:925`, `property.py:296-302` (PUT fields), `accounts.py:219` (delete), seed |
| `PropertyValuation` → `property_valuations` | a point-in-time home value | `account_id` FK, `valuation_date`, `value`, `source` | `api/property`, `api/accounts` (count) | `property.py:254,394,594` (delete :321), `accounts.py:220`, seed. Overlaps `property_value_histories`; `property.py:262` writes both |
| `PropertyValueHistory` → `property_value_histories` | a historical or projected property value point | `account_id` FK, `date`, `value`, `source` (tax_assessment/realtor_estimate/sale/ai_projection/manual), `is_projected`, `details` JSON text | `api/property`, `api/accounts` (count) | `property.py:271,551,573,584,613` (delete :529), `accounts.py:221`. Not seeded |
| `Vehicle` → `vehicles` | one owned vehicle | `year`, `make`, `model`, `trim`, `vin`, `mileage`, `condition`, `purchase_price/date`, `estimated_value`, `value_last_updated`, `valuation_notes` | `api/assets` | `assets.py:62` CRUD, seed |
| `AssetValueHistory` → `asset_value_histories` | a historical/projected vehicle value point | `vehicle_id` FK, `date`, `value`, `source` (ai_estimate/purchase/manual), `is_projected` | `api/assets:200,226` | `assets.py:144,154,164` (deletes :113,135). Not seeded |

#### Tenant schema — retirement

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `RetirementAccount` → `retirement_accounts` | one 401(k) plan summary | `plan_name`, `provider`, `account_id` (soft link, no FK), total/vested/roth/pretax/employer_match balances, deferral rates, lifetime contributions, `roth_basis`, `account_return`, statement dates, `estimated_monthly_income` | `api/retirement`, `api/import_unified` | `retirement.py:303` (+ PUT `/account`, `/rates`), `import_unified.py:967`, seed |
| `RetirementHolding` → `retirement_holdings` | one fund in a retirement account | `retirement_account_id` Integer (**no FK**), `fund_name`, `ticker`, `balance`, `allocation_pct`, `gain_loss` | `api/retirement`, `api/import_unified` | `retirement.py:387`, `import_unified.py:1064` (delete+reinsert :1060), seed |
| `RetirementSnapshot` → `retirement_snapshots` | retirement balance at a statement date | `retirement_account_id` (**no FK**), `snapshot_date`, `balance`, roth/pretax/employer balances, `source` | `api/retirement`, `api/import_unified` | `retirement.py:413`, `import_unified.py:1030`, seed |

#### Tenant schema — planning

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `PlanVersion` → `plan_versions` | one named plan/scenario | `name`, `description`, `scenario_type`, `is_active`; cascades to assumptions/projections | `api/planning`, `planning_service` | `planning_service.py:143` (`create_plan`/`update_plan` ← `api/planning`, seed :408), `planning.py:295` (delete) |
| `PlanAssumption` → `plan_assumptions` | one assumption key/value for a plan | `plan_id` FK cascade, `key`, `display_name`, `category`, `value`, `sensitivity`; unique (plan_id, key) | `api/planning`, `planning_service` | `planning_service.py:154,220` (delete :212) |
| `PlanProjection` → `plan_projections` | a plan's projected numbers for one year | `plan_id` FK, `year`, `age`, `phase`, salary/rsu/total_comp, cash/investments/company_stock/home_equity/retirement_bal/net_worth, `withdrawal`; unique (plan_id, year) | `api/planning:377,570`, seed (count) | `planning_service.py:175,241` (delete :214) |
| `ActualSnapshot` → `actual_snapshots` | a manually recorded actual net-worth breakdown on a date | `snapshot_date`, NW buckets, YTD salary/rsu/comp, `notes` | `api/planning:370` (`/plans/{id}/variance`) | `planning.py:426` (`POST /plans/actuals`) — **no caller anywhere**; only DataExplorer could write it |
| `Forecast` → `forecasts` | one year of a generated forecast run | `generated_at`, `method`, `year`, NW buckets; unique (generated_at, year) | `api/planning:160-169` (`/forecasts/latest`, no caller), `:381` (variance) | `planning.py:229` (`POST /forecasts/generate` via `engine/forecast.py`) — `api.generateForecast` exists in `client.ts:163` but **nothing calls it** |
| `ContributionConfig` → `contribution_configs` | a 401k contribution-rate config effective from a date | `effective_date`, `employee_rate`, `annual_irs_limit`, `employer_match` | `planning_service.py:84` only (always None → falls back to `config.yaml`) | **nothing** — not even the seed |

#### Tenant schema — import pipeline

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `ImportLog` → `import_logs` | one audit record of an import attempt | `source`, `capture_mode`, `status`, `records_created`, `raw_data` JSON text, `parsed_summary`, `error_message` | `api/import_data.py:96` (`GET /import-legacy/log`, hidden, no caller), `import_service` | `ingest.py:382,452,522,606,698`, `import_unified.py:394`, `retirement.py:423`, `import_data.py:136`, `import_service.py:26,240`. **Effectively write-only**: the UI calls `/import/log`, which `import_unified`'s `GET /import/{session_id}` catches → 404; `backend/mcp_server.py:217` calls `/api/import/log` on the legacy mount |
| `ImportSession` → `import_sessions` | one AI-assisted upload moving upload → review → confirmed | `id` String PK, `status`, `context`, `filename`, `file_type`, JSON text: `raw_ai_response`, `parsed_findings`, `missing_fields`, `proposed_changes`, `accepted_change_ids`, `chat_messages`; `changes_applied`, `confirmed_at` | `api/import_unified` only | `import_unified.py:198` only (← `ImportModal.vue`) |
| `EmailReceipt` → `email_receipts` | one forwarded receipt email plus its AI parse | `from_email`, `forwarded_by`, `subject`, `body_text`/`body_html`, `status` (received/parsed/failed), `parsed_data` JSON text, `error_message`, `transaction_id` (soft link, no FK) | `api/email_import.py:146` (`/email-import/receipts` ← Settings) | `email_import.py:74,91-114` (← Cloudflare worker) |

#### Tenant schema — provider links and sync

| model → table | one row is | key columns | readers | writers |
|---|---|---|---|---|
| `PlaidLink` → `plaid_links` | one Plaid item | `id` String PK, `item_id` (unique), `access_token` (plaintext), `institution_name`, `institution_id`, `cursor` | `api/plaid_routes` only | `api/plaid_routes` only |
| `MonarchLink` → `monarch_links` | the stored Monarch session token for a tenant | `email`, `token` (plaintext), `last_synced_at` | `api/monarch_routes`, `sync_scheduler.py:103,736` | `monarch_routes.py:186` (delete :612), repro |
| `MonarchAccountConfig` → `monarch_account_configs` | per-Monarch-account sync settings | `monarch_link_id` FK, `monarch_account_id`, `account_name`, `account_type`, `institution`, `sync_balances`, `sync_transactions`, `local_account_id` (soft link) | `api/monarch_routes`, `sync_scheduler.py:113` | `monarch_routes.py:221` (+ toggles), `accounts.py:224` (null `local_account_id` on delete), repro |
| `SimpleFinLink` → `simplefin_links` | the claimed SimpleFIN access URL | `access_url` (plaintext, embeds basic-auth), `last_synced_at` | `api/simplefin_routes`, `sync_scheduler.py:413,738` | `simplefin_routes.py:130` (delete :334) |
| `SimpleFinAccountConfig` → `simplefin_account_configs` | per-SimpleFIN-account sync settings | `simplefin_link_id` FK, `simplefin_account_id`, `account_name`, `account_type`, `institution`, `sync_balances`, `sync_transactions`, `local_account_id` (soft link) | `api/simplefin_routes`, `sync_scheduler.py:428` | `simplefin_routes.py:154`, `accounts.py:229` |
| `SyncJob` (alias `MonarchSyncJob`) → `sync_jobs` | one provider sync run | `provider`, `status`, `trigger`, `started_at`, `finished_at`, `balances_synced`, `txn_added`, `txn_updated`, `error`; unique partial idx `uq_sync_jobs_one_running_per_provider` | `sync_scheduler`, `monarch_routes.py:582`, `simplefin_routes.py:306` | `sync_scheduler.py:641` (`create_job_row`), status updates :602-613, :705, :798 (← routes, `_scheduler_loop`, `scheduler/__main__.py`), repro. The alias name is used only by `repro_monarch_500.py` and `models/__init__.py:19` |

#### A.4 Flags

- **Nothing reads**: `audit_logs`. Effectively unread: `import_logs` (sole reader is a hidden legacy route with no caller; the UI's `/import/log` call is mis-routed and 404s).
- **Nothing writes (in code)**: `contribution_configs`. Effectively unwritten in normal use: `forecasts`, `actual_snapshots` (their only writers are routes with no caller), `property_value_histories` and `asset_value_histories` until the AI/Realtor refresh buttons are pressed with keys configured.
- **Seed-only writers**: none strictly — every seeded table also has at least one API writer. But today's local rows in `stock_prices`, `retirement_*`, `rsu_grants`/`vest_events`, `vehicles`, `mortgages`, `property_valuations`, `plan_*`, `w2_records`, `accounts`, `balance_snapshots`, `transactions` all came from the seed (every `source` column reads `seed`).
- **Written only by dead modules**: `import_logs` rows from `ingest.py`/`import_data.py`/`import_service.py`/`retirement.py:423`; `accounts`/`balance_snapshots`/`transactions` rows from `import_service.confirm_import`; `rsu_grants`/`vest_events`/`stock_prices` rows from `loaders/etrade_rsu.py`.
- **Soft links / missing FKs**: `retirement_holdings.retirement_account_id`, `retirement_snapshots.retirement_account_id`, `retirement_accounts.account_id`, `email_receipts.transaction_id`, `*_account_configs.local_account_id`, `audit_logs.user_id`, and `transactions.account_id` is nullable (Plaid and email rows leave it NULL).
- **Unused engine modules**: `engine/cash_flow.py`, `net_worth.py`, `sensitivity.py`, `spending.py`, `variance.py` are imported by nothing (`engine/forecast.py` and `engine/projection.py` are used by `api/planning.py` and `planning_service.py`). `tests/test_engine/` is empty.
- **Other stale files touching the model**: `backend/mcp_server.py` (FastMCP wrapper calling the legacy `/api/*` mount on localhost:8000 without any auth cookie — would 401 against today's auth; referenced by nothing), `backend/load_monarch_data.py` (uses `SessionLocal` without a tenant search_path, so it targets `public` where the tables do not exist), `scripts/migrate_sqlite_to_postgres.py` (SQLite era), unused imports `RSUGrant` in `planning_service.py` and `StockPrice` in `api/rsu.py`.

---

## B. Ingestion paths

Legend for "verdict": **live** = reachable from the UI and works against the current code; **live-broken** = reachable but fails or is a no-op; **unreachable-from-UI** = route exists, nothing in `frontend/src` calls it; **dead** = no caller anywhere (UI, scheduler, scripts, tests).

Frontend call surface was derived by grepping `frontend/src` for every `/api/v1/...` literal and every `api.*`/`planningApi.*`/`adminApi.*` client method with a caller. The complete list of backend paths the UI calls is in Appendix 1.

### B.1 Unified AI import — `backend/app/api/import_unified.py` (1,184 lines)

| | |
|---|---|
| Routes | `POST /import/upload` (:177), `GET /import/{session_id}` (:304), `PUT /import/{session_id}/accept` (:328), `POST /import/{session_id}/confirm` (:339), `POST /import/{session_id}/chat` (:422), `POST /import/{session_id}/apply-action` (:527), `GET /import/config/{context}` (:612) |
| Frontend | `frontend/src/components/import/ImportModal.vue` (mounted once in `App.vue:279`) calls all seven. Opened via `useImportModal().openImport({context})` from `IncomeView.vue:573` (`income`), `RSUView.vue:244` (`rsu`), `RetirementView.vue:441` (`retirement`), `PropertyView.vue:663` (`property`). **Nothing opens it with `general`**; `general` is only the default when `context` is omitted. |
| AI | `anthropic.Anthropic` direct; `claude-sonnet-4-20250514` for both parse (:233) and chat (:493). Fails with 500 if `FINANCE_ANTHROPIC_API_KEY` is unset (:184). |
| Writes | `/upload`: inserts `import_sessions` (status `processing` → `review`). `/accept`: updates `import_sessions.accepted_change_ids`. `/confirm` (:340-416): per proposed change, by `table`: `w2_records` → `_apply_w2_changes` (:889, upsert by tax_year); `mortgages` → `_apply_mortgage_changes` (:908, creates `accounts` row + `mortgages`); `retirement_accounts` → `_apply_retirement_changes` (:942, upsert single account, inserts `retirement_snapshots`) and `_apply_retirement_holdings` (:1048, delete+reinsert `retirement_holdings`); `rsu_grants` → `_apply_rsu_changes` (:1077, inserts `rsu_grants` + `vest_events`). Then inserts one `import_logs` row (`source='unified_import'`) and writes `audit_logs` via `log_event` (:409, public schema). `/chat` and `/apply-action` only mutate `import_sessions.chat_messages` / `proposed_changes`. |
| Contexts | `CONTEXT_CONFIG` (:34) has `income`, `retirement`, `property`, `rsu`, `general`. `_build_proposed_changes` (:658) only ever emits `table` ∈ {`retirement_accounts`, `rsu_grants`, `w2_records`, `mortgages`} based on `db_field` prefixes; `general` findings with `db_field=null` produce no proposed change, so **`general` can parse but never write**. |
| Tests | `GET /import/config/{context}` only (`tests/test_api/test_core.py::test_import_config`). The 45 document tests in `tests/test_e2e/test_import_documents.py` are e2e-marked and skip without an API key. |
| Verdict | **live** for `income`, `retirement`, `property`, `rsu`. **unreachable/hollow** for `general`. |

### B.2 Legacy ingest and legacy JSON import

**`backend/app/api/ingest.py`** (708 lines; router prefix `/ingest`, `include_in_schema=False`)

- Routes: `POST /ingest/screenshot` (:338, `claude-opus-4-6` vision on a base64 PNG), `POST /ingest/w2-upload` (:395), `POST /ingest/paystub-upload` (:469), `POST /ingest/mortgage-upload` (:539) (all `claude-haiku-4-5-20251001` on PDF), `POST /ingest/confirm` (:619).
- Writes: each parse route inserts an `import_logs` row; `/confirm` upserts `w2_records` (:654), `balance_snapshots`, `accounts` and `mortgages` (:686), plus another `import_logs` row (:698).
- Frontend: **no caller**. `grep -rn "ingest" frontend/src` finds nothing. The Chrome extension this served was removed (`docs/IMPORT_WORKFLOW.md:14-21`, `docs/CLEANUP_AND_DEPLOYMENT_PLAN.md:21`).
- Tests: none.
- Verdict: **dead**. (Also listed as AI-4 in `docs/REVIEW-2026-10-29.md:87`.)

**`backend/app/api/import_data.py`** (222 lines; prefix `/import-legacy`, hidden from schema) + **`backend/app/services/import_service.py`** (487 lines)

- Routes: `POST /import-legacy/` (:23 → `process_import`), `POST /import-legacy/preview` (:47), `POST /import-legacy/{id}/confirm` (:63), `POST /import-legacy/{id}/reject` (:76), `GET /import-legacy/log` (:89), `POST /import-legacy/parse-screenshot` (:127, inline anthropic call).
- `import_service.py`: `preview_import`/`process_import` insert `import_logs`; `confirm_import` (:143) replays `parsed_summary` records into `accounts`, `balance_snapshots`, `transactions`; `_parse_monarch` (:339) uses `parsers/monarch.py::MonarchParser` on a Monarch GraphQL/REST export; `_parse_etrade`, `_parse_manual`, `_parse_generic` are the other dispatch targets (:289-300).
- Frontend: `api.importData` (`frontend/src/api/client.ts:137`) posts to `/import/` (not `/import-legacy/`) and has **no caller**. `api.getImportLog` (:139) hits `GET /import/log`, which is served by `import_unified`'s `GET /import/{session_id}` and returns 404 "Session not found"; `SettingsView.vue:259` calls it on every load (BUG-8 in the review).
- Tests: none.
- Verdict: **dead** (both files). The only live import of `parsers/monarch.py` is for its two dicts `ACCOUNT_TYPE_MAP`/`DISPLAY_GROUP_MAP`, used by `monarch_routes.py:24` and `sync_scheduler.py:23`.

**`backend/app/loaders/etrade_rsu.py`** (248 lines)

- Entry: `POST /rsu/reload` (`backend/app/api/rsu.py:419-444`) accepts two E-Trade `.xlsx` uploads, writes `rsu_grants`, `vest_events`, `stock_prices`.
- `import pandas` at :15; pandas is not in `backend/requirements.txt`, so the route 500s (BUG-7).
- Frontend: no caller (RSUView only GETs `/rsu/grants`, `/rsu/summary`, `/rsu/price-history`).
- Tests: none.
- Verdict: **dead**.

**`backend/app/parsers/*.py`**

| file | used by | verdict |
|---|---|---|
| `base.py` | the four parsers | dead with them |
| `monarch.py` | `import_service._parse_monarch` (dead); `ACCOUNT_TYPE_MAP`/`DISPLAY_GROUP_MAP` imported by `monarch_routes.py:24`, `sync_scheduler.py:23` (live import for the Monarch sync function only) | dead once Monarch goes; the two dicts would need to move if Monarch's `_sync_tenant_monarch` were kept |
| `etrade.py`, `mortgage.py`, `student_loan.py`, `generic.py` | `parsers/__init__.py::PARSERS` → `import_service._get_parser` only | **dead** |

`tests/test_parsers/` contains only `__init__.py`.

### B.3 SimpleFIN — `backend/app/api/simplefin_routes.py` (336 lines) + `backend/app/services/sync_scheduler.py:356-565`

| | |
|---|---|
| Routes | `POST /simplefin/connect` (:106), `POST /simplefin/refresh-credentials` (:180), `GET /simplefin/status` (:207), `GET /simplefin/accounts` (:222), `PUT /simplefin/accounts/{config_id}` (:248), `POST /simplefin/sync` (:266, 202), `GET /simplefin/sync/status` (:299), `DELETE /simplefin/disconnect` (:326) |
| Frontend | `SettingsView.vue` SimpleFIN tab (:647-776) calls all eight; `/sync` then polls `/sync/status`. |
| Writes (connect) | Claims the setup token (`_claim_setup_token` :44, aiohttp POST), upserts one `simplefin_links` row (plaintext `access_url` with embedded basic-auth), and one `simplefin_account_configs` row per remote account (:154-162). `disconnect` deletes the link (cascade to configs). |
| Writes (sync) | `POST /sync` → `create_job_row(schema, "simplefin", "manual")` inserts `sync_jobs` (status `running`); if `APP_ROLE=web` it calls `notify_sync_request` (Postgres `NOTIFY tallied_sync, 'schema|simplefin'`), otherwise `asyncio.create_task(run_sync_with_job(...))` in-process (:286-294). `_sync_tenant_simplefin` (`sync_scheduler.py:403`) does one `GET {access_url}/accounts`, then per configured account: creates `accounts` row `simplefin-{id}` if missing (:455), inserts a `balance_snapshots` row per day if `sync_balances` (:481), upserts `transactions` with id `simplefin-{txn_id}` and `source='simplefin'` if `sync_transactions` (:513-548). `_finalize_job` (:599) updates the `sync_jobs` row with counts/error. |
| Scheduler | `sync_all_tenants` (:747) iterates every `tenant_*` schema × `ALL_PROVIDERS`, inserts `sync_jobs` with `trigger='scheduled'` when a `simplefin_links` row exists, runs the sync inline. |
| Tests | None of the route. `tests/test_monarch_sync_repro.py::test_sync_all_tenants_passes_int_not_tuple_to_run_sync` exercises `sync_all_tenants` with `ALL_PROVIDERS[0]` (= simplefin) fully mocked. |
| Verdict | **live** (the review notes it is the only connection verified against real accounts; BUG-6: `account_type` is re-guessed from the name on every sync). |

### B.4 Plaid — `backend/app/api/plaid_routes.py` (374 lines)

| | |
|---|---|
| Routes | `GET /plaid/link-token` (:88), `POST /plaid/exchange` (:123), `POST /plaid/sync` (:155), `GET /plaid/links` (:264), `POST /plaid/sync-balances` (:280) |
| Frontend | `SettingsView.vue` Plaid tab (visible, :19, :1145-1195): `link-token`, `exchange`, `links`, `sync`. `PlaidOAuthCallbackView.vue` (route `/plaid-oauth-callback`, `router/index.ts:104`) re-runs `exchange`. `DashboardView.vue:33` fetches `/plaid/links` on every dashboard load. `CashView.vue:127` posts `/plaid/sync-balances` (alongside `/monarch/sync-balances`) from a "sync" button. |
| Writes | `exchange`: inserts `plaid_links` (plaintext `access_token`). `sync`: inserts `transactions` with `source='plaid'`, **no `account_id`** (:205-211, BUG-5), deletes removed ones (:236), updates `plaid_links.cursor`. `sync-balances`: creates `accounts` `plaid-*` rows (:332) and `balance_snapshots` with `source='plaid'` (:355). |
| Filters | `transactions.py:30,133` and `spending.py:53,102,144` all apply `Transaction.source != "plaid"`, and the SQL-transparency strings in `CashView.vue`/`SpendingView.vue` repeat it. So anything Plaid imports is invisible in the UI. |
| Config | `FINANCE_PLAID_CLIENT_ID`, `_SECRET_SANDBOX`, `_SECRET_PRODUCTION`, `_ENV` (`config.py:11-14`); none set locally. `link-token` refuses production outside dev mode without them (:97). |
| Tests | `tests/test_api/test_empty_state.py::test_plaid_links_empty` (GET only). |
| Verdict | **live-broken**: reachable from three pages, no credentials configured anywhere visible, and its transaction output is filtered out of every consumer. Candidate for removal per DEC-2. |

### B.5 Monarch — `backend/app/api/monarch_routes.py` (614 lines), `parsers/monarch.py`, `scripts/repro_monarch_500.py`, `backend/load_monarch_data.py`

| | |
|---|---|
| Routes | `POST /monarch/connect` (:121), `POST /monarch/refresh-credentials` (:249), `GET /monarch/status` (:322), `GET /monarch/accounts` (:339), `PUT /monarch/accounts/{id}` (:368), `POST /monarch/sync-balances` (:389), `POST /monarch/sync` (:529, 202 + job row + NOTIFY/task like SimpleFIN), `GET /monarch/sync/status` (:575), `DELETE /monarch/disconnect` (:602) |
| Frontend | The Monarch tab is removed from `SettingsView.vue`'s `tabs` array (:16-22) but the tab markup (:1197-1375), ~45 refs/functions (:393-625) and the `Tab` union (:14) remain; loaders are skipped (:788). **`CashView.vue:128` still POSTs `/monarch/sync-balances`** on the Cash page sync button (returns `{"synced":0,"detail":"No Monarch connection"}` when there is no link). |
| Client | `_get_monarch_client` (`monarch_routes.py:47`, duplicated at `sync_scheduler.py:86`) monkey-patches the unofficial `monarchmoney` package's endpoints and spoofs a Chrome UA. |
| Writes | `connect`: `monarch_links` (plaintext session token) + `monarch_account_configs`. `sync-balances` (web tier, synchronous): `accounts` `monarch-*` + `balance_snapshots` `source='monarch'`. `sync` → `_sync_tenant_monarch` (`sync_scheduler.py:99-354`): same tables plus `transactions` `monarch-*`, `source='monarch'`. |
| Scheduler | Still registered in `_PROVIDER_SYNC_FN` (:575) but excluded from `ALL_PROVIDERS` (:34), so only manual `POST /monarch/sync` or an orphan/NOTIFY replay can run it. |
| Scripts | `scripts/repro_monarch_500.py` (443 lines): standalone PG-backed check of the job flow, mocks the Monarch client, writes/deletes rows in `tenant_claudius`. `backend/load_monarch_data.py` (227 lines): loads Monarch JSON exports from a `../data` dir that does not exist; calls `Base.metadata.create_all` on the default schema. Neither is referenced by Makefile, CI, Docker or tests. |
| Tests | `tests/test_monarch_sync_repro.py` (6 tests, mocked): 202/race/status behaviour of `/monarch/sync` and `/monarch/sync/status`, and the `sync_all_tenants` regression. |
| Verdict | **unreachable-from-UI** except for the Cash page's `sync-balances` call; scheduler-disabled; slated for removal (DEC-1, CON-1). |

### B.6 Email receipts — `backend/app/api/email_import.py`, `email_forwarding.py`, `services/email_receipt_service.py`, `workers/email-receipt/`

| | |
|---|---|
| Entry | `POST /email-import/inbound` (`email_import.py:37`), called by the Cloudflare Email Worker `workers/email-receipt/src/index.ts:39` with header `X-Email-Webhook-Secret`; validated against `FINANCE_EMAIL_WEBHOOK_SECRET` (`config.py:15`). `wrangler.toml` pins `TALLIED_API_URL = "https://money.markcheli.com"`. Whether the worker is deployed and the secret set cannot be determined from the repo. |
| Flow | Worker extracts `forwarded_by` from `X-Forwarded-For`/`X-Original-From` headers or a `From:` line in the body (SEC-2 spoofing risk). Backend resolves it via `email_forwarding_addresses` (public, `resolve_forwarding_email` :40), opens a hand-rolled tenant session (`email_import.py:64-71`, a third copy of the search_path logic), inserts `email_receipts` (status `received`), calls `parse_receipt_with_ai` (`claude-sonnet-4-20250514`, `email_receipt_service.py:50`), then `create_transaction_from_receipt` (:75) inserts `transactions` with id `email-{hex}`, `source='email_receipt'`, **no `account_id`**, and sets `email_receipts.status='parsed'`/`transaction_id`. Failures are stored as `status='failed'` with `error_message`. |
| UI | Settings → Email tab (`SettingsView.vue:1491-1570`): `GET/POST/DELETE /email-forwarding` (public-schema CRUD, `email_forwarding.py`) and `GET /email-import/receipts?limit=20` (`email_import.py:138`). The Spending table shows "—" for account on `email-*` rows. |
| Tests | none. |
| Verdict | **live** (code path complete, UI present), **unverified** (no deployment evidence in repo, 0 rows locally, AI call unguarded per AI-7). |

### B.7 Manual CRUD from the UI

| Target table | Route | Caller | Verdict |
|---|---|---|---|
| accounts | `POST /accounts/` (:116), `PUT /accounts/{id}` (:135), `DELETE /accounts/{id}` (:184, `?cascade=true` deletes balances/transactions and nulls `monarch_account_configs`/`simplefin_account_configs.local_account_id` :224) | Settings → Accounts tab via `api.createAccount/updateAccount/deleteAccount` (`SettingsView.vue:93,119,175`) | live |
| balance_snapshots | `POST /accounts/{id}/balances` (:245) | **no frontend caller** (`GET` is used by charts) | unreachable-from-UI |
| w2_records | `POST /income/w2` (:126, upsert by tax_year) | Settings → Income tab `api.createW2` (:233, :243, used for both edit and add) | live |
| w2_records | `PUT /income/w2/{year}`, `DELETE /income/w2/{year}` (:160, :177) | none | unreachable-from-UI |
| transactions | `POST /transactions/` (:71), `POST /transactions/bulk` (:92), `PUT`/`DELETE /transactions/{id}` (:170, :190) | none (Spending table is read-only) | unreachable-from-UI |
| vehicles (+asset_value_histories) | `POST/PUT/DELETE /assets/vehicles[...]` (`assets.py:59,88,106`), `POST /assets/vehicles/{id}/refresh-value` (:119, `claude-sonnet-4-20250514` valuation, rewrites `asset_value_histories` rows with `source in ('ai_estimate','purchase')`) | `AssetsView.vue:231,277,299,316` | live |
| property_valuations | `POST /property/valuation` (`property.py:226`), `DELETE /property/valuation/{id}` (:315) | `PropertyView.vue:176` (POST only) | live / delete unreachable |
| property_value_histories (+accounts real_estate auto-create) | `POST /property/refresh-history` (:486; Realtor.com via RapidAPI `services/property_valuation.py`, then AI) | `PropertyView.vue:224` | live (needs `FINANCE_RAPIDAPI_KEY`) |
| mortgages | `PUT /property/mortgage` (:285) | none | unreachable-from-UI |
| property estimate | `POST /property/estimate`, `/zillow-estimate` (:425, :431) | none | unreachable-from-UI |
| retirement_accounts | `PUT /retirement/rates` (:225) | `RetirementView.vue:180` | live |
| retirement_accounts | `PUT /retirement/account` (:181), `POST /retirement/upload-statement` (:248, haiku PDF parse, superseded by unified import) | none | unreachable-from-UI / dead |
| rsu_grants | `POST/PUT/DELETE /rsu/grants[...]` (`rsu.py:148,178,203`) | none (RSUView GETs only; grants arrive via unified import `rsu` context or seed) | unreachable-from-UI |
| plan_versions, plan_assumptions, plan_projections | `POST /plans/` (:104), `PUT /plans/{id}` (:270), `DELETE /plans/{id}` (:290) via `services/planning_service.create_plan/update_plan` | `PlanningView` via `api.createPlan/updatePlan/deletePlan` | live |
| actual_snapshots | `POST /plans/actuals` (:424) | none | unreachable-from-UI (table always empty) |
| forecasts | `POST /plans/forecasts/generate` (:189) | `api.generateForecast` exists in `client.ts:163` but has no caller | unreachable-from-UI (table always empty) |
| any tenant table | `POST/PUT/DELETE /admin/tables/{table}/rows[/{id}]` (`schema.py:155,189,233`, raw parameterised INSERT/UPDATE/DELETE with column whitelist from the inspector) | Database page `DataExplorer.vue:189-216` | live (generic row editor; this is the only UI path that can write `transactions`, `balance_snapshots`, `mortgages`, `rsu_grants`, etc. by hand) |
| any (read) | `POST /admin/query` (`schema.py:268`, SELECT-only, `SET TRANSACTION READ ONLY`) | Database page SQL runner | live, read-only |
| api_keys, db_credentials, webhook_subscriptions (public) | `api_keys.py`, `db_credentials.py` (also runs `CREATE ROLE`/`GRANT` on the tenant schema), `webhooks.py` | API page / Database page | live |
| users, tenants, tenant_memberships (public) | `auth.py` (Google callback, dev login, `/seed-users`), `tenants.py`, `platform_admin.py` | Login, Admin portal | live |
| audit_logs (public) | `services/audit_service.log_event` from `auth.py`, `platform_admin.py`, `import_unified.py:409` | — | live (only `login` rows locally) |
| api_usage_logs (public) | `middleware/usage_logger.py:86` on every v1 request | — | live |

### B.8 Seed and fixtures

- `scripts/seed_test_data.py` (454 lines; `make seed-test` runs it with `--reset`). `--reset` drops `tenant_claudius`, `Base.metadata.drop_all`, recreates platform tables with `create_all`. Then inserts `users`, `tenants`, `tenant_memberships` (public), calls `create_tenant_schema("tenant_claudius")`, `SET search_path`, and inserts: 8 `accounts` (:100-119), 120 `balance_snapshots` `source='seed'` (:146), 428 `transactions` `source='seed'` (:171-198), 3 `w2_records` (:224), 1 `mortgages` (:245), 1 `property_valuations` (:260, `source='Zillow Estimate'`), 8 `rsu_grants` + 24 `vest_events` (:282-297), 1 `stock_prices` `source='seed'` (:309), 1 each `retirement_accounts/holdings/snapshots` (:326-356), 2 `vehicles` (:369-376), then one plan through `planning_service.create_plan` (:408-420) producing 15 `plan_assumptions` + 58 `plan_projections`, and finally `scripts/seed_schema_descriptions.py::seed_descriptions` (COMMENT ON tables/columns). It does **not** stamp Alembic; the memory note says `alembic stamp head` was run by hand.
- Tables only the seed writes (given the current UI): `stock_prices` (also `services/stock_price.py:70` on price fetch, if Yahoo works), `retirement_holdings` (also unified import), `vest_events` (also unified import), `plan_projections` (also planning CRUD). Strictly seed-only today: none; but `import_logs`, `actual_snapshots`, `forecasts`, `contribution_configs`, `property_value_histories`, `asset_value_histories` are written by nothing the seed touches and nothing the UI reliably triggers (see A.3 flags).
- `scripts/generate_test_documents.py` (2,171 lines; `make generate-docs`): reportlab/openpyxl generator for 18 fake documents under `fixtures/test_documents/{income,retirement,property,rsu}/`, described in `fixtures/test_documents/MANIFEST.md`. The 6 root-level files (`2023 W2.pdf`, `2024 W2.pdf`, `2025 W2.pdf`, `Pay Date 2025-12-19.pdf`, `mortgage-statement.pdf`, `retirement-statement.pdf`) are from the initial commit and are not produced by the current generator. Only consumer: `tests/test_e2e/test_import_documents.py:26` (skips if the dir or API key is missing). `generate_test_documents.py` is a Docker `COPY` target too (`Dockerfile:63`) but nothing in the image runs it.

### B.9 Snapshots — `backend/app/api/snapshot.py`, `services/snapshot_service.py`

- There is no snapshot *writer*. `GET /snapshot` (`snapshot.py:11`) → `build_current_snapshot(db)` (`snapshot_service.py:36`) is a pure read: latest `balance_snapshots` row per active account joined to `accounts`, grouped by `display_group` into liquidity layers, net worth / liquid net worth totals, `total_comp_annual` from the latest `w2_records`, and a 12-month delta from snapshots in a ±7-day window a year ago (:134).
- Nothing triggers a balance snapshot write except the ingestion paths above (`SimpleFIN`/`Monarch`/`Plaid` syncs, legacy `import_service`, `ingest.confirm`, `POST /accounts/{id}/balances`, seed). "Snapshot" in the UI (Dashboard `api.getSnapshot`, also `DashboardView`/`CashView` raw fetches) is purely derived.
- Readers of `balance_snapshots` beyond this: `trends.py` (net-worth/balances/cash-flow), `accounts.py` (latest balance subquery, `/balances`), `planning.py:460-520` (year-end and latest balances for the plan table), `engine/*` via `planning_service.build_projection_input`.
- Tests: `test_core.py::test_snapshot_empty/test_snapshot_with_data`, `test_empty_state.py::test_snapshot_empty`.
- Verdict: **live** (read-only aggregate).

---

## C. The sync scheduler — `backend/app/services/sync_scheduler.py` (1,024 lines)

**How it starts**

- Production image: `Dockerfile:88` → `backend/entrypoint.sh` → `alembic upgrade head` then `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2`. Each worker runs the FastAPI lifespan (`main.py:48-121`).
- `main.py:94-105`: `role = APP_ROLE`; if it is neither `web` nor `scheduler` (i.e. unset — the case everywhere: `docker-compose.yml`, `docs/DEPLOYMENT_INSTRUCTIONS.md`, Makefile, CI never set it), the web process calls `reap_stuck_jobs()` then `start_scheduler()`, which creates two asyncio tasks: `_scheduler_loop()` and `notify_listener_loop()`. On shutdown, `mark_running_jobs_failed("worker shutdown")` and `stop_scheduler()`.
- `backend/app/scheduler/__main__.py` (`python -m app.scheduler`) is a standalone entrypoint for an `APP_ROLE=scheduler` container: reap → `claim_orphan_jobs()` → the same two tasks, with SIGTERM handling. No Dockerfile/compose service launches it.
- With `-w 2` and no APP_ROLE both gunicorn workers try; `_scheduler_loop` takes `pg_try_advisory_lock(0x6D6F6E6172636873)` (:45, :832) on a dedicated connection and the loser returns. The listener runs in **both** workers (no lock), so a NOTIFY is processed by both; `_process_notify` is idempotent-ish because it looks up the single `running` row, but two concurrent `run_sync_with_job` calls on the same job are possible.

**Loop**: immediate `sync_all_tenants()` at boot, then every `SYNC_INTERVAL_SECONDS = 12h` (:37, :847). `sync_all_tenants` (:747): `_get_tenant_schemas()` (`information_schema.schemata LIKE 'tenant_%'`), for each × `ALL_PROVIDERS`, skip unless `_tenant_has_provider_connection` (:724, checks `monarch_links`/`simplefin_links` has a row), `create_job_row(trigger='scheduled')`, `await run_sync_with_job(...)`.

**Job table**: `sync_jobs` per tenant schema (`models/sync_job.py`): `id, provider, status(running|succeeded|failed), trigger(manual|scheduled), started_at, finished_at, balances_synced, txn_added, txn_updated, error`; unique partial index `uq_sync_jobs_one_running_per_provider` on `(provider) WHERE status='running'`. `create_job_row` (:622) catches the IntegrityError race and returns the existing running id. `reap_stuck_jobs` (:682) fails rows running > `WATCHDOG_STUCK_MINUTES = 15` at boot. `_finalize_job` (:599) writes counts/error.

**NOTIFY/LISTEN**: channel `NOTIFY_CHANNEL = "tallied_sync"` (:50), payload `"{schema}|{provider}"` (old single-field payload defaults to monarch, :961). `notify_sync_request` (:894) is called by the `/sync` routes only when `APP_ROLE=web`. `notify_listener_loop` (:914) detaches a raw psycopg2 connection, `LISTEN`, uses `loop.add_reader` on the socket, drains notifies into a set, and `_process_notify` (:974) finds the running job and runs it.

**Providers**: `PROVIDER_MONARCH="monarch"`, `PROVIDER_SIMPLEFIN="simplefin"`; `ALL_PROVIDERS = (PROVIDER_SIMPLEFIN,)` (:34); dispatch table `_PROVIDER_SYNC_FN` registers both (:575-576). `_sync_tenant_monarch` (:99-354) and `_sync_tenant_simplefin` (:403-565) are near-duplicate fetch→normalise→upsert loops (CON-6). Both share `_get_tenant_session` (:79), which does a single `SET search_path` that the pool-checkout hook undoes after any commit (CODE-4).

**What breaks if monarch_* and plaid_* code is deleted** — every reference, by file (line numbers from `grep -niE "monarch|plaid"`, comments included):

*Backend, would fail to import or need edits*
- `backend/app/main.py:162-163,257-258,330` — router imports and `include_router` for `plaid_routes`, `monarch_routes` (v1 and legacy mounts); comments :21,:87,:118.
- `backend/app/models/__init__.py:16-17,19` — `PlaidLink`, `MonarchLink`, `MonarchAccountConfig`, `MonarchSyncJob` import.
- `backend/app/models/sync_job.py:11,19-20,36,49-50` — docstring, provider comment, `MonarchSyncJob = SyncJob` alias.
- `backend/app/services/sync_scheduler.py` — `:19` imports `MonarchAccountConfig, MonarchLink`; `:23` imports `ACCOUNT_TYPE_MAP, DISPLAY_GROUP_MAP` from `parsers/monarch`; `:28` `PROVIDER_MONARCH`; `:45` lock key; `:53-67` `_classify_account_type`/`_extract_category` (Monarch helpers); `:86-97` `_get_monarch_client`; `:99-354` `_sync_tenant_monarch`; `:575` registration; `:735-736` connection check; `:961` payload fallback; log strings :815-846, :915-936, :1013, :1024.
- `backend/app/api/accounts.py:14` imports `MonarchAccountConfig`; `:224-225` nulls its `local_account_id` on cascade delete; `_account_source` :33-38 maps `monarch-`/`plaid-` prefixes.
- `backend/app/api/admin.py:30` — `"plaid_links": "created_at"` in a table→sort-column map.
- `backend/app/api/spending.py:53,102,144` and `backend/app/api/transactions.py:30,133` — `Transaction.source != "plaid"` filters (data-level; safe to drop with Plaid, but note they also hide any historical plaid rows).
- `backend/app/api/simplefin_routes.py:3,272` — docstring comparisons only.
- `backend/app/services/import_service.py:175,280-281,291,307,339-372` — `_parse_monarch`, `MonarchParser` import (dead module anyway).
- `backend/app/parsers/__init__.py:1,8` and `backend/app/parsers/monarch.py` (whole file; the two dict constants are the only live import).
- `backend/app/config.py:11-14` — `plaid_client_id`, `plaid_secret_sandbox`, `plaid_secret_production`, `plaid_env`.
- `backend/app/scheduler/__main__.py:8,12` — docstring only.
- `backend/requirements.txt:12-13` — `plaid-python>=14.0.0`, `monarchmoney>=0.1.15`.
- `backend/.env.example:21-22` — `FINANCE_PLAID_CLIENT_ID/SECRET`.
- `backend/load_monarch_data.py` — whole file (dead script).
- `backend/tests/test_monarch_sync_repro.py` — whole file (6 tests; would need rewriting against SimpleFIN or deleting).
- `backend/tests/test_api/test_empty_state.py:131-132` — `test_plaid_links_empty`.

*Alembic (historical; must stay or be squashed, not deleted)*
- `2665375ffb1a_add_valuation_notes_to_vehicles.py:53,189` creates/drops `plaid_links`.
- `c3d4e5f6a7b8_add_monarch_link_tables.py`, `d4e5f6a7b8c9_add_monarch_sync_jobs_table.py`, `e5f6a7b8c9d0_monarch_sync_jobs_unique_running.py`, `f6a7b8c9d0e1_simplefin_and_generalize_sync_jobs.py:32-53,111-115` (renames `monarch_sync_jobs` → `sync_jobs`; downgrade reverses).
- A new migration would be needed to drop `monarch_links`, `monarch_account_configs`, `plaid_links` from each tenant schema.

*Frontend*
- `frontend/src/views/SettingsView.vue` — Plaid tab (:19 tab entry, :266-331 state/functions, :1144-1195 markup) and hidden Monarch tab (:10-14 comment and `Tab` union, :36-47 types, :389-625 state/functions, :787-788, :1196-1375 markup). ~230 lines.
- `frontend/src/views/CashView.vue:125-136` — parallel `plaid/sync-balances` + `monarch/sync-balances` POST; :262,:297,:304 SQL-display strings with `source != 'plaid'`.
- `frontend/src/views/DashboardView.vue:19,29-40,375,400-403` — `plaidLinks` fetch and "N Plaid accounts connected" footer.
- `frontend/src/views/PlaidOAuthCallbackView.vue` (whole file) and `frontend/src/router/index.ts:104-106` route.
- `frontend/src/views/SpendingView.vue:59,73,82,97,234` — SQL-display strings.
- `frontend/src/views/DatabaseView.vue:261` — `plaid_links` in the "system" table category.
- `frontend/src/views/GuideView.vue:146,162,247,383` — prose/feature list naming Plaid.
- `frontend/src/components/spending/TransactionTable.vue:42` — tooltip text.
- `frontend/src/config/tableFormConfigs.ts:507,529` — source-column descriptions.
- `frontend/src/types/index.ts:11` — `source` union comment.
- `frontend/index.html` should be checked for the Plaid Link `<script>` tag (`window.Plaid.create` is used at `SettingsView.vue:287`).

*Scripts, docker, docs*
- `scripts/repro_monarch_500.py` (whole file), `scripts/seed_schema_descriptions.py:22,35,46,177-182` (column descriptions incl. a `plaid_links` block).
- `Dockerfile:16-17` env-var comments. `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `workers/`: **no references**.
- `CLAUDE.md`, `README.md`, `docs/{CLEANUP_AND_DEPLOYMENT_PLAN,IMPORT_WORKFLOW,PLATFORM_VISION,REVIEW-2026-10-29,SECURITY_AUDIT}.md` — prose.

Net: deleting the two route modules, two model modules, `parsers/monarch.py`, the Monarch half of `sync_scheduler.py`, and the frontend tabs is mechanical; the only *shared* pieces that need relocating are `ACCOUNT_TYPE_MAP`/`DISPLAY_GROUP_MAP` (only if a future provider wants them), the `_account_source` prefix helper, and the `MonarchSyncJob` alias (grep shows no importer other than `models/__init__.py`).

---

## D. Alembic

Config: `backend/alembic.ini` (`script_location = %(here)s/alembic`), `backend/alembic/env.py` sets the URL from `settings.database_url`, `target_metadata = Base.metadata`, `render_as_batch=True`, and **never sets `search_path` or `version_table_schema`** — so any migration that does not loop tenant schemas itself runs against `public`.

### D.1 Chain (root → head; linear, single head)

| # | revision | file | does | schema |
|---|---|---|---|---|
| 1 | `cdec83975af0` | `cdec83975af0_initial_schema_16_tables.py` | creates accounts, balance_snapshots, transactions, w2_records, rsu_grants, vest_events, stock_prices, mortgages, property_valuations, plan_versions, plan_assumptions, plan_projections, actual_snapshots, forecasts, contribution_configs, import_logs + indexes | public (pre-tenancy) |
| 2 | `2665375ffb1a` | `2665375ffb1a_add_valuation_notes_to_vehicles.py` | misnamed: creates audit_logs, import_sessions, plaid_links, retirement_accounts, retirement_holdings, retirement_snapshots, vehicles, asset_value_histories; adds `mortgages.escrow/property_address`, `rsu_grants.symbol`, 5 `vest_events` columns; skips a `users.status` ALTER (:151-153) | public |
| 3 | `877cad9a2d80` | `877cad9a2d80_add_property_value_histories_table.py` | creates property_value_histories (FK accounts) | public |
| 4 | `a1b2c3d4e5f6` | `a1b2c3d4e5f6_add_email_receipt_tables.py` | creates `public.email_forwarding_addresses` (FK users, tenants); then `SELECT schema_name FROM tenants` and creates `email_receipts` in each | public + tenant loop (driven by the `tenants` table) |
| 5 | `b2c3d4e5f6a7` | `b2c3d4e5f6a7_add_expires_at_to_db_credentials.py` | `ALTER TABLE db_credentials ADD expires_at` | public |
| 6 | `c3d4e5f6a7b8` | `c3d4e5f6a7b8_add_monarch_link_tables.py` | creates monarch_links, monarch_account_configs (IF NOT EXISTS) | `tenant_%` loop via information_schema |
| 7 | `d4e5f6a7b8c9` | `d4e5f6a7b8c9_add_monarch_sync_jobs_table.py` | creates monarch_sync_jobs + status/started index | tenant loop |
| 8 | `e5f6a7b8c9d0` | `e5f6a7b8c9d0_monarch_sync_jobs_unique_running.py` | fails duplicate running rows, adds unique partial index | tenant loop |
| 9 | `f6a7b8c9d0e1` **head** | `f6a7b8c9d0e1_simplefin_and_generalize_sync_jobs.py` | renames monarch_sync_jobs→sync_jobs (+`provider`), new partial index per provider; creates simplefin_links, simplefin_account_configs | tenant loop |

### D.2 Which migration creates which table

- Revisions 1–3 create 25 of the 30 tenant tables **in `public` only** (there is no tenant loop there; they predate tenancy).
- `email_receipts`: rev 4 (per tenant, from `tenants` rows). `email_forwarding_addresses`: rev 4 (public).
- `monarch_links`, `monarch_account_configs`: rev 6. `sync_jobs`: rev 7 as `monarch_sync_jobs`, renamed in rev 9. `simplefin_links`, `simplefin_account_configs`: rev 9.
- **No migration creates** `users`, `tenants`, `tenant_memberships`, `api_keys`, `api_usage_logs`, `db_credentials`, `webhook_subscriptions` (7 of the 9 platform tables). They exist only via `create_all` in `main.py:84`, `seed_test_data.py:54-57`, `migrate_sqlite_to_postgres.py:68-69`, `load_monarch_data.py:205`.
- No migration creates the 25 core tables *inside* a tenant schema; tenants get them from `create_tenant_schema()` → `create_all`. Existing tenants therefore only receive new columns on those tables if a future migration loops schemas (the CLAUDE.md pattern), which revisions 1–3 did not.

### D.3 Fresh `alembic upgrade head` on an empty database

1. rev 1 — OK: 16 financial tables land in `public`.
2. rev 2 — OK: 8 more tables in `public`; ALTERs hit tables rev 1 made.
3. rev 3 — OK.
4. rev 4 — **fails** at `op.create_table("email_forwarding_addresses", ... ForeignKey("users.id") ...)` (:26): `relation "users" does not exist`. Postgres DDL is transactional, so the whole upgrade rolls back; the DB is left empty with no `alembic_version` row.
5. Had rev 4 passed, `SELECT schema_name FROM tenants` (:42) would fail next, then rev 5's `ALTER TABLE db_credentials` (table never created).
6. Revisions 6–9 would be no-ops on an empty DB (no `tenant_%` schemas), which is harmless.

Consequence in deployment: `entrypoint.sh` has `set -e`, so on an empty volume the container exits before gunicorn — the lifespan `create_all` that would have made the platform tables never runs. The SessionStart hook `scripts/setup-runner.sh:104` runs `alembic upgrade head 2>/dev/null` and prints "Migrations skipped" on failure, hiding this locally. The memory note (`local-env-homebrew-postgres.md`) is correct about rev 4 being the first failure, and the live DB got to `f6a7b8c9d0e1` via `alembic stamp head` after `seed_test_data.py --reset`. Recorded as BUG-1 in `docs/REVIEW-2026-10-29.md:35`.

A side effect on any DB that *did* run revisions 1–3: stray copies of the financial tables in `public` next to the real per-tenant ones. The local DB does not have them (it was built by the seed, not by alembic), which is why `\dt public.*` shows only 10 tables.

### D.4 Where migrations run

`Dockerfile:66-67,88` + `backend/entrypoint.sh:5` (`alembic upgrade head` before gunicorn). Not in `docker-compose.yml`, `Makefile` (`db-migrate` is the SQLite→Postgres data copy), or `.github/workflows/ci.yml` (no migrate-from-empty job).

---

## E. Tests

**Config**: `backend/pytest.ini` — `markers = e2e: ...`, `addopts = -m "not e2e"`. No `pyproject.toml`/`setup.cfg`. No collection hooks; deselection is purely the `addopts` marker expression. pytest 9.2.0 / pytest-asyncio 1.4.1.

**Layout** (`backend/tests/`):
- `conftest.py` — `sqlite:///:memory:`; session-scoped `Base.metadata.create_all` of *all* tables in one schema (no Alembic); per-test connection-level transaction rolled back; overrides `get_db`, `get_tenant_db`, `get_tenant_context` on `app`, `v1`, `legacy`; `MOCK_TENANT_CTX` has `tenant_schema="public"` so tenancy is not exercised; patches `year_month` in `spending`/`trends` to SQLite `strftime`.
- `test_api/test_core.py` (10): health, snapshot empty/with data, income history/current, accounts list, transactions list, spending by category, large transactions, `GET /import/config`.
- `test_api/test_empty_state.py` (19): `*_empty` GETs for snapshot, accounts, transactions, spending ×3, income ×2, rsu ×2, retirement, property, assets, trends ×3, plans, plaid links, transactions/large.
- `test_monarch_sync_repro.py` (6): `/monarch/sync` 202, no-connection skip, race returns same job, `/sync/status` none/latest, `sync_all_tenants` passes an int job id (mocked; uses `ALL_PROVIDERS[0]`).
- `test_rate_limit.py` (6): the in-memory `RateLimiter`.
- `test_engine/`, `test_parsers/`: `__init__.py` only — **no tests**.
- `test_e2e/conftest.py` (397 lines): real Postgres via `E2E_DATABASE_URL` (default local), raw-SQL insert of user/tenant/membership, `create_tenant_schema`, JWT cookie. `test_e2e/test_user_journeys.py` (56 tests in 8 classes), `test_e2e/test_import_documents.py` (45 tests, skip without `FINANCE_ANTHROPIC_API_KEY` + fixtures).
- Untracked, appeared during this session: `test_ledger_check.py` (11 tests) — not part of the committed suite.

**Runs** (from `backend/` with the venv):
- `pytest tests -q` → `41 passed, 101 deselected` (at HEAD; with the untracked file present it becomes 51 passed, 1 skipped).
- `pytest tests/test_e2e -x -q` → `101 deselected` (addopts still applies).
- `pytest tests/test_e2e -x -q -m e2e` → `45 skipped, 1 error`:
  ```
  ERROR tests/test_e2e/test_user_journeys.py::TestNewUserFlow::test_auth_me_returns_user
  sqlalchemy.exc.IntegrityError: (psycopg2.errors.NotNullViolation) null value in column "status"
  of relation "users" violates not-null constraint
  [SQL: INSERT INTO users (email, password_hash, display_name, auth_provider, is_admin, is_active) VALUES (...)]
  ```
  Cause: the `e2e_setup` fixture's raw INSERT (`test_e2e/conftest.py` ~:112-118) predates `users.status` (`models/user.py:21`, Python-side default only, NOT NULL in Postgres). Every e2e test depending on the fixture errors the same way; it also hashes with SHA-256 while the app expects argon2 (CODE-5).
- `make test` = `pytest tests/ -v`; `make test-e2e` = `pytest tests/test_e2e/ -v -m e2e`; CI runs the former on Python 3.12.

**Coverage of ingestion paths**: unified import — config GET only; ingest / import_data / import_service / loaders / parsers — none; SimpleFIN — none directly; Plaid — empty `GET /plaid/links`; Monarch — route boundary only, client mocked; email — none; snapshot — GET empty/seeded; scheduler — one mocked `sync_all_tenants` test.

---

## Appendix 1 — Backend paths the frontend actually calls

From `frontend/src` (raw `fetch` literals plus `api.*` methods with at least one caller). Prefix `/api/v1` unless noted.

`/accounts/` GET POST, `/accounts/{id}` PUT DELETE, `/accounts/{id}/related-counts`, `/accounts/{id}/balances` GET, `/admin/query` POST, `/admin/schema`, `/admin/tables/{t}` GET, `/admin/tables/{t}/rows` POST, `/admin/tables/{t}/rows/{id}` PUT DELETE, `/api-keys/` GET POST, `/api-keys/{id}` DELETE, `/api-keys/usage/summary`, `/assets/summary`, `/assets/value-history/aggregate`, `/assets/vehicles` GET POST, `/assets/vehicles/{id}` PUT DELETE, `/assets/vehicles/{id}/refresh-value` POST, `/assets/vehicles/{id}/value-history`, `/auth/config`, `/auth/google/login`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/refresh`, `/auth/select-tenant`, `/db-credentials/` GET POST, `/db-credentials/{id}` DELETE, `/email-forwarding` GET POST, `/email-forwarding/{id}` DELETE, `/email-import/receipts`, `/health`, `/import/upload` POST, `/import/{id}` GET, `/import/{id}/accept` PUT, `/import/{id}/chat` POST, `/import/{id}/apply-action` POST, `/import/{id}/confirm` POST, `/import/config/{ctx}`, `/import/log` (404), `/income/current`, `/income/history`, `/income/w2` POST, `/monarch/sync-balances` POST (CashView), `/plaid/exchange` POST, `/plaid/link-token`, `/plaid/links`, `/plaid/sync` POST, `/plaid/sync-balances` POST, `/plans/` GET POST, `/plans/{id}` GET PUT DELETE, `/plans/{id}/sensitivity`, `/plans/{id}/variance`, `/plans/{id}/table`, `/plans/compare`, `/property/amortization`, `/property/refresh-history` POST, `/property/summary`, `/property/valuation` POST, `/property/value-history`, `/retirement/rates` PUT, `/retirement/summary`, `/rsu/grants` GET, `/rsu/price-history`, `/rsu/summary`, `/scalar`, `/openapi.json`, `/simplefin/*` (all 8), `/snapshot`, `/spending/by-category`, `/spending/monthly-trend`, `/spending/recurring`, `/transactions/` GET, `/transactions/large`, `/trends/net-worth`, `/trends/cash-flow`, `/webhooks/` GET POST, `/webhooks/{id}` PUT DELETE, `/webhooks/{id}/test` POST. Legacy `/api` (no v1): `/api/admin/tables...` via `api/admin.ts`, `/api/plans/...` via `api/planning.ts`.

Backend routes with **no** frontend caller: everything under `/ingest`, `/import-legacy`, `/mock-api`; `POST /accounts/{id}/balances`; `PUT|DELETE /income/w2/{year}`; `POST|PUT|DELETE /transactions*`; `PUT /property/mortgage`, `DELETE /property/valuation/{id}`, `POST /property/estimate`, `POST /property/zillow-estimate`; `PUT /retirement/account`, `POST /retirement/upload-statement`; `POST|PUT|DELETE /rsu/grants*`, `POST /rsu/reload`; `POST /plans/actuals`, `POST /plans/forecasts/generate`, `GET /plans/forecasts/latest`; `/monarch/*` except `sync-balances`; `/admin/tables/{t}/preview`; `/trends/balances`; `/platform/*` (admin portal — verify in `AdminView` separately, not in scope here); `/auth/seed-users`.
