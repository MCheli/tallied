# Deploying Tallied

Production runs on the 83RR PowerEdge (Ubuntu, Docker Compose, NGINX reverse proxy, Cloudflare in front) at `money.markcheli.com`. The image is `ghcr.io/mcheli/tallied:latest`, built and pushed by `.github/workflows/ci.yml` on every push to `main` that passes tests. Revised 2026-10-29; supersedes the March `DEPLOYMENT_INSTRUCTIONS.md` (now in `docs/archive/`).

## What runs

| Container | Image | Role |
|---|---|---|
| `tallied-db` | `postgres:16-alpine` | the database, volume `tallied_db_data` |
| `tallied` | `ghcr.io/mcheli/tallied:latest` | `backend/entrypoint.sh`: `alembic upgrade head`, then gunicorn serving the API and the built SPA on 8000 |
| `tallied-scheduler` (optional) | same image, `command: python -m app.scheduler`, `APP_ROLE=scheduler` | the sync scheduler (SimpleFIN on a 12h loop plus NOTIFY-driven manual syncs). Without it, set nothing and the web container runs the scheduler in-process. If you add it, set `APP_ROLE=web` on `tallied`. |
| `email-receipt` worker | Cloudflare Worker in `workers/email-receipt/` | receives forwarded receipts at the configured address and POSTs them to `/api/v1/email-import/inbound` |

Startup refuses to run with default secrets, and refuses `FINANCE_DEV_MODE=true` against a non-local database.

## Environment

Set in `~/83rr-poweredge/.env` and passed through the compose file. All app settings use the `FINANCE_` prefix (`backend/app/config.py` is the list).

```bash
DATABASE_URL=postgresql://tallied:<db password>@tallied-db:5432/tallied   # or FINANCE_DATABASE_URL
FINANCE_SECRET_KEY=<64 random bytes>            # JWT signing; python3 -c "import secrets; print(secrets.token_urlsafe(64))"
FINANCE_API_KEY_PEPPER=<32 random bytes>        # HMAC pepper for API keys; changing it invalidates every key
FINANCE_CREDENTIAL_KEY=<Fernet key>             # encrypts provider credentials at rest; python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FINANCE_GOOGLE_CLIENT_ID=...                    # Google SSO; redirect URI https://money.markcheli.com/api/v1/auth/google/callback
FINANCE_GOOGLE_CLIENT_SECRET=...
FINANCE_BASE_URL=https://money.markcheli.com
FINANCE_DEV_MODE=false
FINANCE_ANTHROPIC_API_KEY=sk-ant-...            # document import, receipts, valuations
FINANCE_AI_MODEL_IMPORT=claude-opus-5-5         # document import (default)
FINANCE_AI_MODEL_FAST=claude-sonnet-5-5         # receipts, review chat, valuations (default)
FINANCE_EMAIL_WEBHOOK_SECRET=<random>           # shared with the Cloudflare worker
FINANCE_CORS_ORIGINS=["https://money.markcheli.com"]
FINANCE_DB_PUBLIC_HOST=...                      # only if direct DB credentials are offered; host users connect to
FINANCE_DB_PUBLIC_PORT=5432
```

Plaid and Monarch settings are gone; both integrations were removed in October 2026.

## Database role

The app should not connect as the Postgres superuser. After the first boot:

```bash
docker exec tallied bash -c "cd /app && PYTHONPATH=backend python scripts/setup_postgres_roles.py"
```

prints a connection string for the `tallied_app` role; put it in `DATABASE_URL` and restart `tallied`. Keep the superuser URL for `pg_dump` and manual work. Migrations run as whatever `DATABASE_URL` is, so `tallied_app` keeps `CREATE` on the database and ownership of tenant schemas (the script does this).

The SQL runner on the Database page executes queries as `tallied_sql_runner`, a role with no login and no privileges on `public`, which the app creates and grants per tenant schema on demand. Nothing to configure.

## First boot and first user

1. `docker compose pull tallied && docker compose up -d tallied-db tallied`
2. Watch `docker compose logs -f tallied` for `Running database migrations...` then gunicorn's workers booting. The migrations create the platform tables; there is no `create_all` at startup.
3. Sign in with Google at `https://money.markcheli.com`. The first user is `pending`. Approve and grant admin:

```bash
docker exec tallied-db psql -U tallied -d tallied -c \
  "UPDATE public.users SET is_admin = true, status = 'active' WHERE email = 'you@example.com';"
```

A tenant schema is created for the user at first login. Nothing else is seeded in production; the Claudius seed is for local development only.

## Updating

```bash
cd ~/83rr-poweredge
docker compose pull tallied
docker compose up -d tallied            # entrypoint runs alembic upgrade head before serving
docker compose logs --tail 30 tallied
curl -s https://money.markcheli.com/api/v1/health
```

If a migration fails the container exits and the old image is not restored automatically: `docker compose logs tallied` shows the Alembic error; fix forward or `docker compose up -d` with the previous image tag (`ghcr.io/mcheli/tallied:<sha>`).

## NGINX and DNS

Unchanged from the March setup: upstream `tallied:8000`, HTTPS server block for `money.markcheli.com` with the wildcard Cloudflare origin certificate, `client_max_body_size 20M` for document uploads, and a proxied A record in Cloudflare with SSL mode "Full (Strict)". The app adds its own HSTS header outside dev mode.

## Backups

The server backup script dumps the database nightly (`backup_tallied_db` in `~/83rr-poweredge/scripts/backup.sh`) and copies the `tallied_db_data` volume. Manual:

```bash
docker exec tallied-db pg_dump -U tallied tallied | gzip > tallied_$(date +%Y%m%d).sql.gz
gunzip < tallied_YYYYMMDD.sql.gz | docker exec -i tallied-db psql -U tallied tallied   # restore
```

Uploaded documents are not stored; only extracted data is. Provider credentials in the dump are encrypted with `FINANCE_CREDENTIAL_KEY`, so back that key up with the dump.

## Email receipts worker

`workers/email-receipt/` is a Cloudflare Email Worker. Deploy with `wrangler deploy` from that directory with `EMAIL_WEBHOOK_SECRET` (same value as `FINANCE_EMAIL_WEBHOOK_SECRET`) and `TALLIED_API_URL=https://money.markcheli.com` as worker secrets. The receipt address users forward to is configured in Cloudflare Email Routing. Each user registers the address they forward *from* on Settings → Email Receipts; a receipt from an unregistered address is rejected with 422.

## Troubleshooting

| Symptom | Check |
|---|---|
| Container exits at start | `docker compose logs tallied`: a `FATAL:` line names the missing or default secret, or the Alembic error |
| 502 from NGINX | container still migrating or unhealthy: `docker ps`, then the health endpoint from inside the server |
| Google sign-in loops | redirect URI in Google Cloud Console must be exactly `https://money.markcheli.com/api/v1/auth/google/callback` |
| SimpleFIN sync stuck "running" | the watchdog fails jobs older than the cutoff at next boot; `SELECT * FROM <tenant>.sync_jobs ORDER BY id DESC LIMIT 5` |
| Receipts rejected 401 | `FINANCE_EMAIL_WEBHOOK_SECRET` differs between worker and app |
