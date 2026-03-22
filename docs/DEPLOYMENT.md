# Deploying Tallied

## Home Server (83rr-poweredge)

### Add to docker-compose.yml

```yaml
  # ═════════════════════════════════════════════════════════════════════════════
  # Tallied — Personal Finance Dashboard
  # Image published from: github.com/your-username/personal-finance
  # ═════════════════════════════════════════════════════════════════════════════
  tallied:
    image: ghcr.io/your-username/personal-finance:latest
    container_name: tallied
    restart: unless-stopped
    logging: *default-logging
    volumes:
      - tallied-data:/app/data
    environment:
      - FINANCE_ANTHROPIC_API_KEY=${FINANCE_ANTHROPIC_API_KEY}
      - FINANCE_PLAID_CLIENT_ID=${FINANCE_PLAID_CLIENT_ID}
      - FINANCE_PLAID_SECRET=${FINANCE_PLAID_SECRET}
    networks:
      - infrastructure
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  tallied-data:
```

### Add nginx config

Create `infrastructure/nginx/conf.d/your-domain.com.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://tallied:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed later)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # File upload size (for PDF imports)
        client_max_body_size 20M;
    }
}
```

### Add environment variables

Add to `.env` on the home server:
```
FINANCE_ANTHROPIC_API_KEY=sk-ant-...
FINANCE_PLAID_CLIENT_ID=...
FINANCE_PLAID_SECRET=...
```

### First deployment

```bash
# Pull and start
docker compose pull tallied
docker compose up -d tallied

# Seed initial data (optional)
docker exec tallied python scripts/seed_test_data.py

# Seed auth users
docker exec tallied python -c "
import requests
requests.post('http://localhost:8000/api/auth/seed-users')
"
```

### Database backups

Add to crontab on the home server:
```cron
0 3 * * * docker exec tallied cp /app/data/finance.db /app/data/finance.db.backup.$(date +\%Y\%m\%d)
```

### SSL/TLS

TLS is handled by the nginx reverse proxy on the home server. Certificates should be configured in the main nginx config (Let's Encrypt via certbot or similar).
