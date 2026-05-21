# Deployment

## Prerequisites

- **Docker** + **Docker Compose v2** (`docker compose` — not `docker-compose`)
- **Cloudflare account** with a tunnel configured in Zero Trust dashboard
- **GLM-OCR model files** (~1.78 GB) — see [llama-server Setup](llama-server.md)
- **rclone** (optional) — for automated backups to S3, Backblaze B2, or other remotes

## Environment Setup

```bash
cp .env.example .env
# Edit .env with your values — see the reference table below
```

### Environment Variable Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async connection URL | `postgresql+asyncpg://user:pass@postgres:5432/db` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379` |
| `LLAMA_SERVER_URL` | llama-server URL (internal Docker network) | `http://llama-server:8080` |
| `LLAMA_MODEL_DIR` | Host path to the GLM-OCR model directory | `/home/user/llama.cpp/GLM-OCR` |
| `LLAMA_MODEL_FILE` | Model filename inside `LLAMA_MODEL_DIR` | `GLM-OCR-f16.gguf` |
| `SECRET_KEY` | API signing secret — minimum 32 characters | generate with: `openssl rand -hex 32` |
| `CORS_ORIGINS` | JSON list of allowed CORS origins | `["https://app.yourdomain.com"]` |
| `POSTGRES_USER` | PostgreSQL username | `smartvoucher` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `changeme` |
| `POSTGRES_DB` | PostgreSQL database name | `smartvoucher` |

## llama-server Setup

### Option A: llama-server as Docker service (recommended for portability)

```bash
# Build the llama-server image (takes 10–15 min first time — compiles llama.cpp from source)
docker build -f infra/Dockerfile.llama -t smartvoucher-llama infra/

# Set model directory in .env
LLAMA_MODEL_DIR=/path/to/llama.cpp/GLM-OCR
LLAMA_MODEL_FILE=GLM-OCR-f16.gguf
```

The `llama-server` service in `docker-compose.prod.yml` mounts `${LLAMA_MODEL_DIR}` as `/models` and starts `llama-server` automatically.

### Option B: llama-server native (current dev setup)

```bash
# Start llama-server natively on the host
bash llama.cpp/GLM-OCR.sh

# Update .env to point the API at the host
LLAMA_SERVER_URL=http://host.docker.internal:8080
```

> **Note**: When using Option B, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `api` service in your compose file so the container can reach the host network.

## Start Production Stack

```bash
cd infra

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Run database migrations
docker compose -f docker-compose.prod.yml exec api uv run alembic upgrade head

# Verify all services are healthy
docker compose -f docker-compose.prod.yml ps
```

## Cloudflare Tunnel Setup

1. Create a tunnel in the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) → Networks → Tunnels
2. Add public hostname routes:
   - `api.yourdomain.com` → `http://nginx:80`
   - `app.yourdomain.com` → `http://nginx:80`
3. Copy the tunnel token and set it in `cloudflare/.env`:
   ```
   CLOUDFLARED_TOKEN=<your-tunnel-token>
   ```
4. Start the cloudflared container:
   ```bash
   cd ~/Downloads/vm-share/Linux/docker/cloudflare
   docker compose up -d
   ```
5. nginx receives requests from `cloudflared-network` and routes `/api/` paths to the FastAPI backend and all other paths to the Next.js webapp.

## Backup Setup

Add these cron jobs on the deployment machine:

```cron
# Daily DB backup at 02:00
0 2 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-db.sh

# Daily Redis backup at 02:30
30 2 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-redis.sh

# Daily image/uploads backup at 03:00 (requires RCLONE_REMOTE in env)
0 3 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-images.sh
```

Backups are compressed with gzip and retained locally for 7 days. If `RCLONE_REMOTE` is set, they are also uploaded to the configured remote (S3, B2, etc.).

## GitHub Actions Secrets

Configure these secrets in the repository Settings → Secrets and variables → Actions:

| Secret | Description |
|--------|-------------|
| `SSH_HOST` | IP address or hostname of the deployment machine |
| `SSH_USER` | SSH username for deployment |
| `SSH_KEY` | Private SSH key (RSA or Ed25519) — paste the full key including headers |
| `SSH_PORT` | SSH port (default: `22`) |

## GitHub Environments

1. Go to repository **Settings → Environments**
2. Create a `production` environment
3. Enable **Required reviewers** and add at least one reviewer
4. The `deploy-production.yml` workflow targets this environment, which enforces a manual approval gate before each production deploy

## Deployment Workflows

| Workflow | Trigger | Target |
|----------|---------|--------|
| `deploy-staging.yml` | Push to `develop` branch | Staging server (auto) |
| `deploy-production.yml` | Push tag matching `v*` | Production server (requires approval) |

Both workflows use `infra/scripts/deploy.sh` via SSH. The script pulls images, restarts services, and verifies health endpoints before exiting.
