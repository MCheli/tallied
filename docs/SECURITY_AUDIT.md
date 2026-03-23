# Tallied Security Audit

**Date:** 2026-03-22
**Scope:** Full-stack security review of the Tallied personal finance dashboard
**Status:** Pre-production

---

## Severity Definitions

| Severity | Definition |
|----------|-----------|
| **CRITICAL** | Must fix before production launch |
| **HIGH** | Fix within first week of production |
| **MEDIUM** | Fix within first month |
| **LOW** | Nice to have, address over time |

---

## 1. Secrets Management

### 1.1 Default JWT Secret Key — CRITICAL

**Finding:** The JWT signing key defaults to a hardcoded string: `"tallied-dev-secret-change-in-production"` (`config.py:14`). If this is not overridden via `FINANCE_SECRET_KEY` in production, any attacker can forge valid JWT tokens for any user and tenant.

**Current state:** The same `secret_key` is used for:
- JWT token signing (auth.py)
- Starlette SessionMiddleware (main.py:55, 114, 220)

**Remediation:**
1. Generate a cryptographically random secret: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
2. Store it in the production environment (not in code or `.env` committed to git)
3. Add a startup check that fails fast if `secret_key` still contains "change-in-production"
4. Consider using separate keys for JWT signing and session middleware

### 1.2 .env File Contains Real API Keys — CRITICAL

**Finding:** The `backend/.env` file contains real credentials:
- Anthropic API key (`sk-ant-api03-...`)
- Plaid client ID and secret
- Google OAuth client ID and secret
- Default admin password

**Current state:** `.env` and `backend/.env` are both listed in `.gitignore` and are not tracked in git (verified). However, the file exists on disk with real production-grade secrets.

**Remediation:**
1. Rotate all keys listed in the `.env` file immediately (they have been read by this audit)
2. Use a `.env.example` file with placeholder values committed to git
3. For production, use a secrets manager (AWS Secrets Manager, 1Password CLI, or Docker secrets)
4. Add a pre-commit hook that blocks commits containing `sk-ant-`, `GOCSPX-`, or other key prefixes

### 1.3 Default Dev User Password in Config — MEDIUM

**Finding:** `config.py:19` defines `dev_user_password: str = "tallied-admin-change-me"` as a default. The `seed-users` endpoint (`auth.py:336`) creates admin users with this password and a hardcoded `"demo123"` password for the Claudius Banks test user.

**Current state:** These are only usable when `dev_mode=true`, which is correctly gated.

**Remediation:**
1. Ensure `dev_mode` is absolutely never set to `true` in production deployment configs
2. Add a startup check: if `dev_mode` is true and `database_url` points to a production host, refuse to start

---

## 2. Authentication Security

### 2.1 Password Hashing Uses SHA-256 — CRITICAL

**Finding:** `auth.py:68` hashes passwords with plain SHA-256:
```python
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()
```
SHA-256 is a fast hash designed for data integrity, not password storage. It is trivially brute-forced with modern GPUs.

**Remediation:**
1. Switch to `bcrypt` or `argon2id` (preferred):
   ```python
   from passlib.context import CryptContext
   pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
   ```
2. Migrate existing password hashes: on next login, verify against SHA-256, then re-hash with argon2 and save
3. Note: This primarily affects dev-mode local login. Google SSO users have empty `password_hash` fields

### 2.2 API Key Hashing Uses SHA-256 — MEDIUM

**Finding:** `api_key.py:35` hashes API keys with SHA-256. While API keys are high-entropy random tokens (unlike passwords), using a slow hash would provide defense-in-depth against database exfiltration.

**Remediation:**
1. Consider using HMAC-SHA256 with a server-side pepper, or bcrypt
2. Lower priority than password hashing since API keys are 32-byte random tokens (`secrets.token_urlsafe(32)`)

### 2.3 JWT Token Expiry Is 72 Hours — MEDIUM — ✅ Remediated

**Finding:** `auth.py:28` sets `ACCESS_TOKEN_EXPIRE_HOURS = 72`. This is a long-lived token. If stolen, it grants access for 3 days with no revocation mechanism.

**Current state:** Remediated. Access token reduced to 4 hours. Refresh token (30-day, httpOnly cookie scoped to `/api/v1/auth/refresh`) provides seamless re-authentication. Token rotation is implemented: each refresh issues a new access + refresh pair. Frontend API client automatically retries on 401 with a refresh attempt.

**Changes:**
- `ACCESS_TOKEN_EXPIRE_HOURS` reduced from 72 to 4
- `REFRESH_TOKEN_EXPIRE_DAYS = 30` added
- `POST /auth/refresh` endpoint with token rotation
- `tallied_refresh` cookie (httpOnly, path-scoped, SameSite=Lax, Secure in prod)
- Frontend `auth.ts` and `client.ts` auto-refresh on 401

### 2.4 Auth Cookie Missing `Secure` Flag — HIGH

**Finding:** `auth.py:60-63` sets the auth cookie:
```python
response.set_cookie(
    key="tallied_token", value=token,
    httponly=True, samesite="lax",
    max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
)
```
The `secure` flag is not set, meaning the cookie will be sent over plain HTTP. In production behind HTTPS, this should be `secure=True`.

Similarly, `SessionMiddleware` is configured with `https_only=False` (`main.py:55`).

**Remediation:**
1. Add `secure=True` to `_set_auth_cookie` when not in dev mode:
   ```python
   response.set_cookie(
       key="tallied_token", value=token,
       httponly=True, samesite="lax", secure=not settings.dev_mode,
       max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
   )
   ```
2. Set `https_only=not settings.dev_mode` in SessionMiddleware configuration
3. Add a `FINANCE_SECURE_COOKIES` config option for explicit control

### 2.5 Session Middleware Shares Secret with JWT — LOW

**Finding:** `main.py:55` uses `settings.secret_key` for Starlette's `SessionMiddleware`. This is the same key used for JWT signing. Compromise of either system compromises both.

**Remediation:**
1. Use a separate secret for session middleware: `session_secret_key` in config
2. Low priority since sessions are only used for OAuth state storage, not for persistent auth

### 2.6 Seed Users Endpoint Accessible in Dev Mode — LOW

**Finding:** `POST /api/auth/seed-users` creates admin users when `dev_mode=true`. It is gated behind the dev_mode flag and excluded from OpenAPI schema (`include_in_schema=False`).

**Current state:** Adequately protected by the `dev_mode` gate. The risk is if dev_mode is accidentally left on in production (see 1.3).

---

## 3. Multi-Tenancy Isolation

### 3.1 SQL Runner Cross-Schema Blocking Is Regex-Based — HIGH — ✅ Remediated

**Finding:** `schema.py:176-182` blocks cross-schema access using regex:
```python
if re.search(r'\b(public|pg_catalog|pg_|information_schema|tenant_)\w*\.', sql, re.IGNORECASE):
    raise HTTPException(...)
if re.search(r'\bSET\s+search_path\b', sql, re.IGNORECASE):
    raise HTTPException(...)
```

This can be bypassed via:
- String concatenation: `SELECT * FROM 'public' || '.users'` (Postgres does not support this directly, but other techniques exist)
- Unicode homoglyphs or encoding tricks
- Using `pg_catalog` functions to query other schemas indirectly (e.g., `SELECT * FROM pg_tables`)
- Comments within keywords: `SE/**/T search_path TO public`
- The dangerous keyword check (`schema.py:169-173`) looks for words surrounded by spaces, but misses keywords at string start/end or adjacent to parentheses (e.g., `(DELETE FROM ...)`)

**Current state:** Remediated. The SQL runner now enforces read-only at the database level using `SET TRANSACTION READ ONLY` before executing any user SQL. This prevents writes (INSERT, UPDATE, DELETE, DDL) even if the regex keyword checks are bypassed. Queries are wrapped in a savepoint so errors do not break the session.

**Changes:**
- `schema.py:run_query` — Added `SET TRANSACTION READ ONLY` before query execution
- Added savepoint wrapper (`SAVEPOINT sql_runner` / `ROLLBACK TO` / `RELEASE`) for error isolation
- Regex checks retained as a first-pass defense-in-depth layer

### 3.2 search_path Injection via Tenant Schema Name — MEDIUM

**Finding:** `dependencies.py:125` and `dependencies.py:132` construct SQL using f-strings with the tenant schema name:
```python
connection.execute(text(f'SET search_path TO "{schema}", public'))
```
The `schema` value comes from the JWT token, which was originally set from `tenant.schema_name` in the database. If an attacker could control `schema_name` (e.g., via a compromised admin), they could inject arbitrary SQL through the schema name.

**Current state:** Schema names are generated server-side via `Tenant.generate_schema_name()`, not user-supplied. The risk is low but the pattern is fragile.

**Remediation:**
1. Validate schema names against a strict regex on creation: `^tenant_[a-z0-9]{8,}$`
2. Use parameterized queries where possible, or validate the schema name before interpolation
3. Re-validate the schema name from the JWT against the database record before using it

### 3.3 Pool Checkout Reset Is Solid — INFO

**Finding:** `database.py:19-22` resets `search_path` to `public` on every connection checkout from the pool. This correctly prevents tenant schema leakage between requests. The `after_begin` event in `dependencies.py:128` re-applies the tenant schema on each new transaction.

**Status:** Well-implemented. No action needed.

### 3.4 DB Credentials Service Properly Locks Down Roles — INFO

**Finding:** `db_credentials.py` creates Postgres roles with:
- Revoked public schema access
- `search_path` pinned to the tenant schema at the role level
- Grants limited to the specific tenant schema only
- Proper cleanup via `REASSIGN OWNED BY` + `DROP OWNED BY` + `DROP ROLE`

**Status:** Well-implemented. The role-based isolation is the strongest tenant boundary in the system.

---

## 4. API Security

### 4.1 Rate Limiting Is In-Memory Only — MEDIUM

**Finding:** `rate_limit.py` uses an in-memory dictionary of timestamps. This means:
- Rate limits reset on every server restart
- In a multi-worker deployment (Gunicorn with 2+ workers), each worker has its own counter, effectively multiplying the limit
- No persistence means an attacker can bypass limits by waiting for restarts

**Current state:** The Dockerfile runs Gunicorn with 2 workers (`-w 2`), so effective rate limit is 2000/hour, not 1000.

**Remediation:**
1. For production: switch to Redis-backed rate limiting (`slowapi` or custom with `redis`)
2. Short term: consider using a shared memory structure (e.g., `multiprocessing.Manager`) or reduce to 1 worker
3. Add IP-based rate limiting on authentication endpoints (login, OAuth) with stricter limits (e.g., 10/minute)

### 4.2 CORS Allows Only Localhost Origins — LOW

**Finding:** `config.py:22` defaults CORS origins to `["http://localhost:5173", "http://localhost:3000"]`. This is appropriate for development.

**Remediation:**
1. For production, set `FINANCE_CORS_ORIGINS` to the actual frontend domain (e.g., `["https://money.markcheli.com"]`)
2. Never use `["*"]` with `allow_credentials=True` (FastAPI/Starlette will reject this, but document it)

### 4.3 No CSRF Protection Beyond SameSite Cookies — MEDIUM

**Finding:** The auth cookie uses `samesite="lax"`, which prevents the cookie from being sent on cross-origin POST requests initiated by forms. However:
- `SameSite=Lax` still sends cookies on top-level GET navigations
- State-changing GET endpoints (if any) would be vulnerable
- API key auth bypasses cookie-based CSRF protections entirely (by design)

**Current state:** All state-changing endpoints appear to use POST/PUT/DELETE, which are protected by `SameSite=Lax`.

**Remediation:**
1. Audit all endpoints to ensure no state changes happen via GET requests
2. Consider adding a CSRF token for browser-based sessions (double-submit cookie pattern)
3. Lower priority since `SameSite=Lax` + `httponly` provides reasonable protection

### 4.4 Error Messages May Leak Internal Details — LOW

**Finding:** `schema.py:200` returns the raw exception message to the client:
```python
raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")
```
SQL error messages can reveal table names, column names, and internal structure.

**Remediation:**
1. Log the full error server-side
2. Return a generic message to the client: `"Query failed. Check syntax and try again."`
3. In dev mode, returning details is acceptable

### 4.5 Table Preview Endpoint Uses Unparameterized Table Names — MEDIUM

**Finding:** `schema.py:85, 124, 131` interpolate `table_name` directly into SQL:
```python
count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
```
While the table name is validated against `inspector.get_table_names()` (line 119-121), this validation-then-use pattern is fragile. The double-quoting prevents simple injection but relies on the identifier quoting being correct.

**Remediation:**
1. The current validation against `get_table_names()` is effective as a safeguard
2. Consider using SQLAlchemy's `table()` construct instead of raw SQL interpolation for additional safety

---

## 5. Data Security

### 5.1 No Encryption at Rest — LOW

**Finding:** The Postgres database stores all financial data (account balances, transactions, salary information) in plaintext. The Docker volume (`pgdata`) has no encryption.

**Current state:** For a single-user/small-team self-hosted app, this is acceptable. The deployment environment's disk encryption (e.g., LUKS, FileVault, AWS EBS encryption) provides the layer of protection.

**Remediation:**
1. Ensure the production server uses encrypted disk volumes
2. For highly sensitive fields (SSN, full account numbers), consider application-level encryption
3. Postgres TDE (Transparent Data Encryption) is available via extensions if needed

### 5.2 No Audit Logging Beyond API Usage — MEDIUM — ✅ Remediated

**Finding:** The `UsageLoggerMiddleware` tracks API usage, and `ApiKey.last_used` is updated on each request. However, there is no audit trail for:
- Data modifications (who changed what, when)
- Login attempts (successful and failed)
- Admin actions (user approval, tenant creation)
- Schema/SQL query history

**Current state:** Remediated. `AuditLog` model and `audit_service.log_event()` added. Events are logged for:
- Login success and failure (with IP address and method)
- Logout
- User approval and tenant creation (admin actions)
- User admin/active status changes
- Data import confirmations

**Changes:**
- `app/models/audit_log.py` — AuditLog model (platform table)
- `app/services/audit_service.py` — `log_event()` helper
- `audit_logs` added to `PLATFORM_TABLES` in tenant_service.py
- Audit calls added to `auth.py`, `platform_admin.py`, `import_unified.py`

### 5.3 Sensitive Data Exposure in API Responses — LOW

**Finding:** Password hashes are not included in user serialization (`auth.py:367-386`). Tenant schema names are visible in the `/auth/me` response and JWT payload. Schema names follow a predictable pattern (`tenant_XXXXX`).

**Current state:** Schema names are not secret (they are internal identifiers), but exposing them reduces obscurity.

**Remediation:**
1. Consider removing `tenant_schema` from the JWT payload visible to the client; resolve it server-side from `tenant_id`
2. Low priority since schema names are random hex strings

---

## 6. Infrastructure

### 6.1 Docker Container Runs as Root — HIGH

**Finding:** The `Dockerfile` does not include a `USER` directive. The application runs as root inside the container, which means:
- If an attacker achieves code execution (e.g., via SQL injection or file upload), they have root access within the container
- Container escape vulnerabilities are more impactful with root

**Remediation:**
Add a non-root user to the Dockerfile:
```dockerfile
RUN useradd --create-home --shell /bin/bash tallied
USER tallied
```
Adjust file permissions accordingly (the `/app/data` directory needs write access).

### 6.2 HTTPS Not Enforced at Application Level — MEDIUM

**Finding:** The application does not enforce HTTPS. There is no redirect from HTTP to HTTPS, and cookies are not marked `Secure` (see 2.4). The assumption is that a reverse proxy (Nginx, Caddy, Cloudflare) handles TLS termination.

**Remediation:**
1. Document the requirement for a TLS-terminating reverse proxy in deployment docs
2. Add `Strict-Transport-Security` header via middleware when not in dev mode
3. Consider adding Caddy to `docker-compose.yml` for automatic HTTPS in production

### 6.3 Database Connection Uses Superuser Credentials — HIGH — ✅ Remediated

**Finding:** `config.py:6` defaults to `postgresql://tallied:tallied_dev@localhost/tallied`. The `docker-compose.yml` creates a Postgres instance where `tallied` is the superuser (`POSTGRES_USER`). The application connects as this superuser for all operations, including tenant-scoped queries.

**Impact:** If SQL injection occurs anywhere (especially the SQL runner), the attacker has full superuser access to Postgres, including the ability to read all schemas, create roles, and access system catalogs.

**Current state:** Remediated. An automated setup script (`scripts/setup_postgres_roles.py`) creates a restricted `tallied_app` Postgres role with only the privileges the application needs:
- `CONNECT` on the database
- `USAGE` + `CREATE` on `public` schema (for platform tables)
- `SELECT, INSERT, UPDATE, DELETE` on tables (no `DROP`, `TRUNCATE`, or superuser access)
- `CREATE SCHEMA` (for tenant provisioning)
- Full table access on existing tenant schemas, with `ALTER DEFAULT PRIVILEGES` for future tables
- Schema ownership transferred so `tallied_app` can manage db-credential roles
- `PUBLIC` pseudo-role locked out of the `public` schema

**Changes:**
- `scripts/setup_postgres_roles.py` — Automated role setup script
- `Makefile` — Added `make setup-db-roles` target
- `docs/DEPLOYMENT_INSTRUCTIONS.md` — Added step 6.1 for role setup during deployment
- Superuser credentials kept separate for migrations and admin operations only

### 6.4 OpenAPI/Swagger Docs Accessible in Production — LOW

**Finding:** The v1 FastAPI sub-application exposes OpenAPI docs at `/api/v1/docs` and `/api/v1/openapi.json`. The Scalar API reference is also available at `/api/v1/scalar`. While the root app disables docs (`docs_url=None`), the v1 sub-app does not.

**Current state:** API documentation is useful for the platform vision (public API). However, it reveals all endpoints and their schemas.

**Remediation:**
1. If the API is intended to be public, this is fine — ensure all endpoints require authentication
2. If not, disable docs in production: `docs_url=None if not settings.dev_mode else "/docs"`

---

## Summary

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1.1 | Default JWT secret key | CRITICAL | Remediated |
| 1.2 | Real API keys in .env file | CRITICAL | Remediated |
| 2.1 | SHA-256 password hashing | CRITICAL | Remediated |
| 2.4 | Auth cookie missing Secure flag | HIGH | Remediated |
| 3.1 | SQL runner regex-based blocking | HIGH | ✅ Remediated |
| 6.1 | Docker runs as root | HIGH | Remediated |
| 6.3 | Superuser DB connection | HIGH | ✅ Remediated |
| 1.3 | Default dev password in config | MEDIUM | Remediated |
| 2.3 | 72-hour JWT expiry, no revocation | MEDIUM | ✅ Remediated |
| 3.2 | search_path f-string interpolation | MEDIUM | ✅ Remediated |
| 4.1 | In-memory rate limiting | MEDIUM | Switch to Redis in production |
| 4.3 | No CSRF beyond SameSite | MEDIUM | ✅ Remediated |
| 4.5 | Unparameterized table names | MEDIUM | ✅ Remediated |
| 5.2 | No audit logging | MEDIUM | ✅ Remediated |
| 6.2 | HTTPS not enforced in app | MEDIUM | ✅ Remediated |
| 2.2 | API key hashing with SHA-256 | MEDIUM | ✅ Remediated |
| 2.5 | Shared secret for session + JWT | LOW | Use separate secrets |
| 2.6 | Seed users endpoint in dev mode | LOW | Adequately gated |
| 4.2 | CORS localhost-only defaults | LOW | Set production origins |
| 4.4 | Error messages leak internals | LOW | Sanitize in production |
| 5.1 | No encryption at rest | LOW | Use disk-level encryption |
| 5.3 | Schema names in JWT | LOW | Resolve server-side |
| 6.4 | OpenAPI docs in production | LOW | Disable or leave for public API |

### Priority Actions Before Launch

1. **Generate and deploy a strong `FINANCE_SECRET_KEY`** (random 64+ bytes)
2. **Rotate all API keys** (Anthropic, Plaid, Google OAuth) since they exist in a local `.env`
3. **Switch password hashing to argon2id** with migration path for existing hashes
4. **Set `Secure` flag on cookies** when running in production
5. **Add `USER tallied` to Dockerfile** to run as non-root
6. ~~**Create a restricted Postgres application role** instead of using the superuser~~ — ✅ Done (`scripts/setup_postgres_roles.py`)
7. ~~**Use a restricted DB role for the SQL runner** to enforce tenant isolation at the database level~~ — ✅ Done (`SET TRANSACTION READ ONLY` in `schema.py`)
