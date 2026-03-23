# Tallied — Production Deployment on 83RR PowerEdge

Target server: 83RR PowerEdge (Ubuntu 22.04, Docker Compose, NGINX reverse proxy)
Domain: `money.markcheli.com`
Image: `ghcr.io/mcheli/tallied:latest`

These instructions are for a Claude Code agent running on the 83rr-poweredge server.

---

## 1. Prerequisites

The following are already set up on the server:

- Docker and Docker Compose
- NGINX reverse proxy (container `nginx`, config at `~/83rr-poweredge/infrastructure/nginx/conf.d/`)
- Cloudflare Origin Certificates for `*.markcheli.com` (valid until 2040)
- Cloudflare DNS management
- NAS backups at `/mnt/nas/83rr-backup/`

Verify:

```bash
docker --version
docker compose version
```

---

## 2. Add Tallied to the Server Docker Compose

Add the following services to `~/83rr-poweredge/docker-compose.yml` in the services section:

```yaml
  # ═════════════════════════════════════════════════════════════════════════════
  # Tallied (Personal Finance Dashboard)
  # Image published from: github.com/mcheli/tallied
  # ═════════════════════════════════════════════════════════════════════════════
  tallied-db:
    image: postgres:16-alpine
    container_name: tallied-db
    restart: unless-stopped
    logging: *default-logging
    environment:
      - POSTGRES_USER=tallied
      - POSTGRES_PASSWORD=${TALLIED_DB_PASSWORD}
      - POSTGRES_DB=tallied
    volumes:
      - tallied_db_data:/var/lib/postgresql/data
    networks:
      - infrastructure
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tallied -d tallied"]
      interval: 10s
      timeout: 5s
      retries: 5

  tallied:
    image: ghcr.io/mcheli/tallied:latest
    container_name: tallied
    restart: unless-stopped
    logging: *default-logging
    depends_on:
      tallied-db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://tallied:${TALLIED_DB_PASSWORD}@tallied-db:5432/tallied
      - FINANCE_SECRET_KEY=${TALLIED_SECRET_KEY}
      - FINANCE_GOOGLE_CLIENT_ID=${TALLIED_GOOGLE_CLIENT_ID}
      - FINANCE_GOOGLE_CLIENT_SECRET=${TALLIED_GOOGLE_CLIENT_SECRET}
      - FINANCE_BASE_URL=https://money.markcheli.com
      - FINANCE_ANTHROPIC_API_KEY=${TALLIED_ANTHROPIC_API_KEY:-}
      - FINANCE_DEV_MODE=false
    networks:
      - infrastructure
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

Add the volume to the `volumes:` section:

```yaml
  tallied_db_data:
```

Also add the same service definitions (without build context, just image references) to `~/83rr-poweredge/docker-compose.prod.yml`:

```yaml
  tallied-db:
    image: postgres:16-alpine

  tallied:
    image: ghcr.io/mcheli/tallied:latest
```

---

## 3. Configure Environment Variables

Add to `~/83rr-poweredge/.env`:

```bash
# Tallied (Personal Finance Dashboard)
TALLIED_DB_PASSWORD=<generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
TALLIED_SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_urlsafe(64))">
TALLIED_GOOGLE_CLIENT_ID=<from Google Cloud Console>
TALLIED_GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
TALLIED_ANTHROPIC_API_KEY=<Anthropic API key for AI document parsing>
```

Generate the secrets:

```bash
cd ~/83rr-poweredge

# Generate and append secrets to .env
TALLIED_DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
TALLIED_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

cat >> .env << EOF
# Tallied (Personal Finance Dashboard)
TALLIED_DB_PASSWORD=${TALLIED_DB_PASSWORD}
TALLIED_SECRET_KEY=${TALLIED_SECRET_KEY}
TALLIED_GOOGLE_CLIENT_ID=CHANGE_ME
TALLIED_GOOGLE_CLIENT_SECRET=CHANGE_ME
TALLIED_ANTHROPIC_API_KEY=CHANGE_ME
EOF
```

Then manually fill in the Google OAuth and Anthropic credentials.

Google OAuth redirect URI must be set to: `https://money.markcheli.com/api/auth/google/callback`

---

## 4. Configure NGINX

Add the upstream and server block to `~/83rr-poweredge/infrastructure/nginx/conf.d/production.conf`.

Add upstream (with the other upstream definitions near the top):

```nginx
upstream tallied {
    server tallied:8000;
}
```

Add `money.markcheli.com` to the HTTP redirect server block's `server_name` list.

Add HTTPS server block (with the other public service blocks):

```nginx
# Tallied Finance Dashboard (money.markcheli.com)
server {
    listen 443 ssl;
    http2 on;
    server_name money.markcheli.com;

    ssl_certificate /etc/nginx/certs/wildcard-markcheli.crt;
    ssl_certificate_key /etc/nginx/certs/wildcard-markcheli.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # File upload size for PDF/document imports
    client_max_body_size 20M;

    location / {
        limit_req zone=general burst=30 nodelay;

        proxy_pass http://tallied;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for future real-time features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 86400;
    }
}
```

Test and reload NGINX:

```bash
cd ~/83rr-poweredge
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

---

## 5. Add DNS Record

Add a Cloudflare DNS record for `money.markcheli.com`:

```bash
source venv/bin/activate
python scripts/cloudflare_dns_manager.py add money 173.48.98.211
```

Or add manually in Cloudflare dashboard:
- Type: A
- Name: money
- Content: 173.48.98.211
- Proxy status: Proxied (orange cloud)

Verify Cloudflare SSL mode is set to "Full (Strict)".

---

## 6. Start the Service

```bash
cd ~/83rr-poweredge

# Pull the Tallied image
docker compose pull tallied

# Start Tallied and its database
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d tallied-db tallied

# Verify containers are running and healthy
docker ps | grep tallied

# Check logs for startup errors
docker compose logs --tail 50 tallied
docker compose logs --tail 50 tallied-db
```

The app auto-creates all database tables on first startup. No migration step needed.

### 6.1 Set Up Restricted Database Role

After the app has started and created its tables, create a restricted `tallied_app` Postgres role. This ensures the application no longer connects as the superuser:

```bash
# From the tallied repo on your local machine (or inside the container)
docker exec tallied bash -c "cd /app && PYTHONPATH=. python scripts/setup_postgres_roles.py"
```

The script outputs a new connection string. Update the `TALLIED_DATABASE_URL` (or `DATABASE_URL`) in `~/83rr-poweredge/.env` to use the `tallied_app` role, then restart:

```bash
cd ~/83rr-poweredge
# Edit .env — replace the DATABASE_URL with the tallied_app connection string
docker compose up -d tallied
```

Keep the superuser credentials stored separately for migrations and administrative operations only.

Verify the health endpoint:

```bash
curl -s http://localhost:8000/api/v1/health  # from the server
curl -s https://money.markcheli.com/api/v1/health  # via NGINX
```

---

## 7. First User Setup

Sign in via Google SSO at `https://money.markcheli.com`. The first user lands in `pending` status. Approve and grant admin:

```bash
docker exec tallied-db psql -U tallied -d tallied -c "
UPDATE public.users SET is_admin = true, status = 'active' WHERE email = 'your-email@example.com';
"
```

Verify:

```bash
docker exec tallied-db psql -U tallied -d tallied -c "
SELECT email, status, is_admin FROM public.users;
"
```

---

## 8. SSL/TLS

SSL is handled automatically by the existing infrastructure:

- Cloudflare terminates public SSL (client -> Cloudflare)
- Cloudflare Origin Certificate encrypts Cloudflare -> NGINX (wildcard cert for `*.markcheli.com`, valid until 2040)
- No per-service certificate management needed
- Cloudflare SSL mode must be "Full (Strict)"

No action required for Tallied specifically.

---

## 9. Backups

Add Tallied database to the server's existing backup script at `~/83rr-poweredge/scripts/backup.sh`.

Add a new function:

```bash
# Dump Tallied PostgreSQL database
backup_tallied_db() {
    log "Backing up Tallied database..."
    local dump_file="${BACKUP_ROOT}/databases/tallied_${TIMESTAMP}.sql"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would dump Tallied PostgreSQL to ${dump_file}"
        return
    fi

    docker exec tallied-db pg_dump -U tallied tallied \
        > "${dump_file}" 2>/dev/null || {
        error "Failed to dump Tallied database"
        return 1
    }

    gzip -f "${dump_file}"
    success "Tallied database backed up: ${dump_file}.gz"
}
```

Call it from the `main()` function alongside the other database backups:

```bash
backup_tallied_db || true
```

Add `tallied_db_data` to the `backup_docker_volumes` function's volume list:

```bash
"83rr-poweredge_tallied_db_data"
```

### Manual backup

```bash
docker exec tallied-db pg_dump -U tallied tallied > tallied_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore from backup

```bash
gunzip < tallied_backup_YYYYMMDD.sql.gz | docker exec -i tallied-db psql -U tallied tallied
```

---

## 10. Updating

The CI/CD pipeline at `.github/workflows/ci.yml` in the tallied repo runs tests, then builds and pushes `ghcr.io/mcheli/tallied:latest` on every push to `main`.

To deploy a new version on the server:

```bash
cd ~/83rr-poweredge

# Pull the latest image
docker compose pull tallied

# Restart with new image
docker compose up -d tallied

# Verify
docker ps | grep tallied
docker compose logs --tail 20 tallied
curl -s https://money.markcheli.com/api/v1/health
```

Or use the Makefile shortcut (if `deploy` target supports it):

```bash
make deploy s=tallied
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| App won't start | `docker compose logs tallied` — look for import errors or missing env vars |
| Can't connect to DB | Verify `TALLIED_DB_PASSWORD` in `.env` matches what tallied-db was initialized with. If mismatch, remove the volume and recreate: `docker volume rm 83rr-poweredge_tallied_db_data` |
| Google SSO fails | Verify `TALLIED_GOOGLE_CLIENT_ID` and `TALLIED_GOOGLE_CLIENT_SECRET` in `.env`. Verify redirect URI in Google Cloud Console matches `https://money.markcheli.com/api/auth/google/callback` |
| 502 Bad Gateway | Container may still be starting. Check `docker ps` for health status. Check `docker compose logs tallied` |
| Health check fails | `docker exec tallied curl -f http://localhost:8000/api/v1/health` |
| NGINX config error | `docker compose exec nginx nginx -t` |
| DNS not resolving | `dig money.markcheli.com +short` — should return Cloudflare IPs (proxied) |
