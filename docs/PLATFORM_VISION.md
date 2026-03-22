# Platform Vision: Personal Finance as a Data Platform

## Status: Planning — Not yet implemented

*Created: March 22, 2026*
*This document captures the long-term vision for evolving the personal finance app from a single-user dashboard into a multi-tenant data platform with direct database access, public APIs, and extensibility.*

---

## 1. Multi-Tenancy & User Management

### Goal
Support multiple users who can access shared or isolated financial data. Users may belong to multiple tenants (e.g., personal finances + shared household).

### Design Decisions
- **Deployment model**: Single server, database per tenant
- **Database engine**: PostgreSQL (migrate from SQLite)
- **Product intent**: Personal + shared to start, path toward commercialization later. Don't over-optimize early.

### Architecture

#### User Model
```
User
├── id, email, password_hash, name
├── created_at, last_login
└── memberships[] → TenantMembership

TenantMembership
├── user_id, tenant_id
├── role (owner | admin | member | viewer)
└── created_at

Tenant
├── id, name, slug
├── database_name (e.g., "tenant_abc123")
├── plan (free | pro | enterprise)
├── created_at
└── settings (JSON)
```

#### Database Isolation Strategy
- **Schema-per-tenant within a shared PostgreSQL instance** (recommended starting point)
  - Each tenant gets a dedicated Postgres schema (e.g., `tenant_abc123`)
  - Application sets `search_path` per request based on authenticated tenant
  - Simpler than DB-per-tenant, scales to hundreds of tenants on one instance
  - Can graduate to separate databases if needed for enterprise tenants
- **Shared "platform" schema** for cross-tenant data: users, tenants, memberships, billing, API keys
- **Tenant schemas** contain all financial data: accounts, transactions, balances, W2s, RSU grants, etc.

#### Authentication
- JWT-based auth with refresh tokens
- Session management via httpOnly cookies
- OAuth2 support (Google, Apple) for convenience
- Tenant context embedded in JWT claims
- API key auth for programmatic access (separate from user auth)

#### Migration from SQLite
1. Set up PostgreSQL instance (local Docker for dev, managed RDS/Supabase for prod)
2. Create migration script: SQLite → Postgres (SQLAlchemy models already work with both)
3. Update `database.py` to use Postgres connection with schema routing
4. Add middleware that sets `search_path` from authenticated tenant
5. Seed initial tenant from existing SQLite data

### Technical Changes Required
- [ ] Add `users`, `tenants`, `tenant_memberships` tables in platform schema
- [ ] Add authentication middleware (JWT + API key)
- [ ] Add tenant context middleware (resolve tenant from auth, set schema)
- [ ] Migrate SQLAlchemy models to support schema-per-tenant
- [ ] Build login/registration UI
- [ ] Build tenant management (create, invite users, manage roles)
- [ ] Migrate from SQLite to PostgreSQL

---

## 2. Direct Database Access

### Goal
Users can connect to their data using standard database tools (psql, DBeaver, Excel ODBC, Tableau, custom scripts). This is a major differentiator — "your financial data, your database."

### Design

#### Credential Management
- **Postgres roles mapped to tenant schemas** (simple, scalable)
- Each tenant can create database credentials through the UI
- Two access levels:
  - **Read-only**: `SELECT` on all tables in tenant schema
  - **Read-write**: `SELECT, INSERT, UPDATE, DELETE` on all tables
- Credentials are actual Postgres roles with `GRANT` on the tenant's schema
- Connection string provided: `postgres://user:pass@host:5432/finance?options=-csearch_path=tenant_xxx`

#### Excel / ODBC Support
- Postgres has native ODBC driver support
- Users install the PostgreSQL ODBC driver and connect using their credentials
- Excel PivotTable / Power Query can connect directly
- Provide step-by-step instructions in the UI

#### Connection Proxy (future)
- For production: PgBouncer connection pooling in front of Postgres
- Rate limiting per credential
- Query timeout enforcement (prevent runaway queries)
- Audit logging of all queries executed

### UI: Credentials Page
```
/settings/database
├── "Your Database" section
│   ├── Connection details (host, port, database, schema)
│   ├── Create credential (name, access level: read-only/read-write)
│   ├── List credentials (name, created, last used, revoke button)
│   └── Connection examples (psql, Python, Excel, Tableau)
└── "Quick Connect" one-click copy buttons
```

### Technical Changes Required
- [ ] Postgres role management service (create/revoke roles, manage grants)
- [ ] Credential CRUD API endpoints
- [ ] UI for credential management
- [ ] Connection proxy setup (PgBouncer)
- [ ] Documentation generator for connection examples

---

## 3. SQL Transparency on Dashboard KPIs

### Goal
Every dashboard widget shows a "View SQL" button that reveals the exact query behind the number. Educational — helps users understand the data model and build their own queries.

### Design

#### Implementation Approach
- Each API endpoint that powers a dashboard widget stores its SQL query as metadata
- Frontend adds a small `</>` icon button to every data tile
- Clicking opens a modal showing:
  - The SQL query (syntax highlighted, copyable)
  - Which tables are involved
  - A simplified join diagram showing the relevant tables
  - "Run in SQL Runner" button (links to admin page)

#### Example
```
Net Worth KPI:
┌──────────────────────────────────────────┐
│ SELECT SUM(bs.balance) AS net_worth      │
│ FROM balance_snapshots bs                │
│ JOIN accounts a ON bs.account_id = a.id  │
│ WHERE a.is_active = true                 │
│   AND a.include_in_nw = true             │
│   AND bs.snapshot_date = (               │
│     SELECT MAX(snapshot_date)            │
│     FROM balance_snapshots               │
│     WHERE account_id = bs.account_id     │
│   )                                      │
│                                          │
│ Tables: accounts ─── balance_snapshots   │
└──────────────────────────────────────────┘
```

### Technical Changes Required
- [ ] Create a registry of KPI definitions with their SQL
- [ ] Add `SqlViewerModal` component with syntax highlighting (use Prism.js or Shiki)
- [ ] Add join diagram renderer (simple SVG showing table relationships)
- [ ] Add "View SQL" button to InfoTooltip or as a separate icon
- [ ] Each backend endpoint annotates its query for the frontend

---

## 4. Interactive Schema Canvas (Admin Page Evolution)

### Goal
Replace the current basic table browser with an interactive entity-relationship diagram that serves as both documentation and a data exploration tool.

### Design

#### Schema Canvas Features
- **ERD Visualization**: Interactive canvas showing all tables as nodes, foreign keys as edges
- **Click-to-explore**: Click a table to see:
  - Column names, types, nullable, primary/foreign keys
  - Row count and last-updated timestamp
  - Quick data preview (first 10 rows)
  - Related tables (what joins to this table)
- **Zoom & pan**: Canvas supports zoom, pan, and auto-layout
- **Search**: Type a table or column name to highlight it on the canvas
- **Filter**: Toggle table groups (financial, planning, system, etc.)

#### SQL Runner Panel
- Split-pane: canvas on left, SQL runner on right (or bottom)
- Query editor with:
  - Syntax highlighting
  - Table/column autocomplete from schema metadata
  - Run button → results grid below
  - Export results as CSV
  - Query history (last 20 queries)
- Safety: read-only by default, write access opt-in

#### Technology Options
- **Canvas rendering**: React Flow, D3.js, or ECharts graph chart
- **SQL editor**: Monaco Editor (VS Code's editor) or CodeMirror 6
- **Schema metadata**: API endpoint that returns full schema as JSON (tables, columns, FKs, row counts)

### Technical Changes Required
- [ ] Backend: `/api/admin/schema` endpoint returning full schema metadata with FK relationships
- [ ] Frontend: Canvas component using React Flow or D3 for ERD
- [ ] Frontend: Monaco/CodeMirror SQL editor component
- [ ] Frontend: Query execution via `/api/admin/query` endpoint (read-only)
- [ ] Frontend: Results grid with sorting, filtering, CSV export

---

## 5. Public API Platform

### Goal
Expose all financial data and operations as a documented REST API. Users can build integrations, automations, and custom tools on top of their data.

### Design

#### API Access Model
- **Full CRUD + webhooks**: Users can read, write, update, delete all their data
- API keys scoped to tenant, with configurable permissions
- Rate limiting per key (default: 1000 requests/hour)
- Webhook subscriptions for data change events

#### API Key Management
```
API Key
├── id, tenant_id, name, key_hash
├── permissions (read | write | admin)
├── rate_limit (requests/hour)
├── last_used, request_count
├── created_at, expires_at (optional)
└── is_active
```

#### Public Endpoints (organized by resource)
```
Accounts:     GET/POST/PUT/DELETE /api/v1/accounts
Transactions: GET/POST /api/v1/transactions (with filtering, pagination)
Balances:     GET/POST /api/v1/balances (balance snapshots)
Income:       GET/POST /api/v1/income/w2
RSU:          GET /api/v1/rsu/grants, /api/v1/rsu/summary
Retirement:   GET /api/v1/retirement/summary
Property:     GET /api/v1/property/summary
Assets:       GET/POST/PUT/DELETE /api/v1/assets/vehicles
Planning:     GET/PUT /api/v1/plans (with projections)
Import:       POST /api/v1/import/upload (CSV, PDF, spreadsheet)
Webhooks:     POST /api/v1/webhooks (subscribe to events)
```

#### Webhook Events
- `transaction.created`, `transaction.updated`
- `balance.updated`
- `plan.recalculated`
- `import.completed`
- `account.created`

#### API Documentation Page
- Auto-generated from FastAPI OpenAPI schema (already built-in)
- Interactive "Try It" console (like Swagger UI but styled to match the app)
- Code examples in Python, JavaScript, curl
- API key management (create, revoke, view usage)
- Request/response logging (last 100 requests per key)

### Technical Changes Required
- [ ] API versioning (`/api/v1/` prefix)
- [ ] API key authentication middleware
- [ ] Rate limiting middleware (Redis-based or in-memory)
- [ ] Webhook subscription model + delivery system (queue-based)
- [ ] API usage logging (request count, latency, errors per key)
- [ ] API documentation page (extend FastAPI's built-in OpenAPI)
- [ ] API key management UI

---

## 6. Migration Roadmap

### Phase 1: Foundation (Current → Multi-user ready)
1. Migrate SQLite → PostgreSQL
2. Add user authentication (JWT)
3. Add basic tenant isolation (schema-per-tenant)
4. Versioned API (`/api/v1/`)
5. API key auth for programmatic access

### Phase 2: Data Platform
6. Direct database access (Postgres roles + credential management)
7. Interactive schema canvas (replace admin page)
8. SQL transparency on dashboard KPIs
9. SQL runner in admin page

### Phase 3: API Platform
10. Full CRUD public API
11. API documentation page
12. Webhook system
13. API usage tracking and logs
14. Rate limiting

### Phase 4: Commercialization Readiness
15. Billing integration (Stripe)
16. Tenant onboarding flow
17. Data import wizards for new users
18. ODBC/Excel connection guide
19. Mobile-responsive UI
20. Backup and export (full tenant data dump)

---

## 7. Technical Architecture (Target State)

```
                    ┌─────────────┐
                    │   Nginx     │
                    │  (reverse   │
                    │   proxy)    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
      ┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────────┐
      │  Frontend    │ │ FastAPI │ │  PgBouncer   │
      │  (Vue SPA)   │ │  API    │ │  (connection │
      │  Static CDN  │ │ Server  │ │   pooling)   │
      └──────────────┘ └────┬────┘ └──────┬───────┘
                            │             │
                       ┌────▼─────────────▼────┐
                       │     PostgreSQL         │
                       │  ┌─────────────────┐   │
                       │  │ platform schema │   │
                       │  │ (users, tenants,│   │
                       │  │  API keys, etc.)│   │
                       │  └─────────────────┘   │
                       │  ┌─────────────────┐   │
                       │  │ tenant_abc      │   │
                       │  │ (accounts, txns,│   │
                       │  │  balances, etc.)│   │
                       │  └─────────────────┘   │
                       │  ┌─────────────────┐   │
                       │  │ tenant_xyz      │   │
                       │  │ (accounts, txns,│   │
                       │  │  balances, etc.)│   │
                       │  └─────────────────┘   │
                       └────────────────────────┘
```

### Key Technology Choices
- **Database**: PostgreSQL 16+ (from SQLite)
- **Auth**: JWT + API keys (python-jose, passlib)
- **Connection pooling**: PgBouncer
- **Rate limiting**: Redis or in-memory (fastapi-limiter)
- **Webhooks**: Background task queue (Celery + Redis or arq)
- **Schema canvas**: React Flow or D3.js
- **SQL editor**: Monaco Editor
- **API docs**: FastAPI OpenAPI + custom styled docs page
- **Deployment**: Docker Compose (dev), single VPS or AWS (prod)

---

## 8. Open Questions

1. **Pricing model**: Free tier limits? Per-tenant or per-user pricing?
2. **Data retention**: How long to keep transaction history? Balance snapshots?
3. **Shared tenants**: When a user is in multiple tenants, how does the UI switch between them? Dropdown? Separate login?
4. **Import compatibility**: Should the platform support importing from other PFM tools (Mint, YNAB, Monarch)?
5. **Mobile**: Native app eventually, or responsive web only?
6. **Notifications**: Email/push notifications for balance thresholds, large transactions, vest events?
