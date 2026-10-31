# Deploying Tallied

Production runs on the 83RR PowerEdge (Ubuntu, Docker Compose, NGINX reverse proxy, Cloudflare in front) at `money.markcheli.com`. The image is `ghcr.io/mcheli/tallied:latest`, built and pushed by `.github/workflows/ci.yml` on every push to `main` that passes tests. Revised 2026-10-29; supersedes the March `DEPLOYMENT_INSTRUCTIONS.md` (now in `docs/archive/`).

## What runs

| Container | Image | Role |
|---|---|---|
| `tallied-db` | `postgres:16-alpine` | the database, volume `tallied_db_data` |
| `tallied` | `ghcr.io/mcheli/tallied:latest` | `backend/entrypoint.sh`: `alembic upgrade head`, then gunicorn serving the API and the built SPA on 8000 |
| `tallied-scheduler` (optional) | same image, `command: python -m app.scheduler`, `APP_ROLE=scheduler` | the sync scheduler (SimpleFIN on a 12h loop plus NOTIFY-driven manual syncs). Without it, set nothing and the web container runs the scheduler in-process. If you add it, set `APP_ROLE=web` on `tallied`. |
| `weekly-recap` worker | Cloudflare Worker in `workers/weekly-recap/` | Mondays 12:00 UTC: fetches `/api/v1/recap/weekly/email` with a read-only API key and sends it through Email Routing |
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

The SQL runner on the Database page executes queries as `tallied_sql_runner_<tenant schema>`, one role per tenant with no login, no privileges on `public` and SELECT on that tenant's schema only, which the app creates on demand. Nothing to configure. The shared `tallied_sql_runner` role used before 2026-10-31 is dropped the first time a query runs; if the app role cannot drop it, the log says so and gives the SQL to run as the superuser.

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
docker exec tallied-db pg_dump -U tallied tallied | gzip > ~/tallied-backups/pre-$(date +%F-%H%M).sql.gz
docker compose pull tallied tallied-scheduler
docker compose up -d --no-deps tallied tallied-scheduler   # entrypoint runs alembic upgrade head before serving;
                                                          # --no-deps keeps compose from recreating tallied-db
docker compose logs --tail 30 tallied
docker logs --tail 20 tallied-scheduler                   # expect "Sync scheduler started" and a succeeded sync job
curl -s https://money.markcheli.com/api/v1/health
```

Done this way on 2026-10-29 (first deploy of the October overhaul): backup, migrations 0002removal and 0003vehval applied, the SimpleFIN credential encrypted in place, the boot sync succeeded against the real accounts.

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

## Weekly recap email worker

`workers/weekly-recap/` runs on a cron trigger (Mondays 12:00 UTC) and emails the last Sunday–Saturday week's recap. Tallied renders the message (`GET /api/v1/recap/weekly/email`: subject, HTML, text); the worker only fetches it and sends it with a `send_email` binding, so the app needs no mail server.

- The recipient must be a verified Email Routing destination address on the Cloudflare account, and `RECAP_FROM` must be on a domain with Email Routing enabled.
- Secrets: `TALLIED_API_KEY` (a **read**-permission key named `weekly-recap-email`), `RECAP_TO`, `TRIGGER_TOKEN`.
- Deploy: `cd workers/weekly-recap && npm install && CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... npx wrangler deploy`.
- Send one now: `curl -X POST "https://tallied-weekly-recap.<subdomain>.workers.dev/send?token=$TRIGGER_TOKEN"`; it answers `sent: <subject>` or `failed: <reason>`.
- A failed Monday run shows as an error on the worker's Cron Events in the Cloudflare dashboard.


## Public demo (money-demo.markcheli.com)

The same image in demo mode, on its own database, holding only the Claudius seed. It must never share the production database, secrets or `.env` (startup refuses AI and Google secrets and any database with non-persona users).

| Container | Role |
|---|---|
| `tallied-demo-db` | `postgres:16-alpine`, volume `tallied_demo_db_data`, no published port |
| `tallied-demo` | `ghcr.io/mcheli/tallied:latest` with `FINANCE_DEMO_MODE=true` and `APP_ROLE=web` (no scheduler). The entrypoint runs migrations, then `scripts/seed_test_data.py --reset`, then gunicorn. |

- Its environment is listed in the compose file, not taken from `.env`: `DATABASE_URL` (the demo database, as its owner), `FINANCE_SECRET_KEY`, `FINANCE_API_KEY_PEPPER` and `FINANCE_CREDENTIAL_KEY` (its own, from `TALLIED_DEMO_*` in `.env`), `FINANCE_BASE_URL=https://money-demo.markcheli.com`, `FINANCE_CORS_ORIGINS`, `FINANCE_DEMO_MODE=true`.
- Fresh data: the server crontab restarts `tallied-demo` at 08:00 UTC each day, and the restart reseeds; the site answers 502 for the few seconds that takes.
- Production shows the demo link when `FINANCE_DEMO_URL=https://money-demo.markcheli.com` is set on `tallied`.
- NGINX: a server block for `money-demo.markcheli.com` proxying to `tallied-demo:8000`, with the wildcard certificate. DNS: a proxied A record like `money`'s. (`demo.money.markcheli.com` would need a second-level certificate, which is why the name is flat.)
- Check after a deploy: `curl -s https://money-demo.markcheli.com/api/v1/auth/config` shows `"demo_mode":true`, a POST to `/api/v1/api-keys/` answers 403, and the login page's "Enter the demo" opens the Dashboard.
