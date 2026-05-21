# Proposal: Fase 6 (CI/CD, Deployment & Security)

## Intent
Automate testing, linting, and deployment processes, secure the system, establish production-ready Docker setups with Cloudflare Tunnels, persist configuration variables in the database, and prepare the WordPress.org plugin submission.

## Scope

### In Scope
- `configuracion_sistema` database model, migration, and service implementation.
- GitHub Actions for CI (`tests-api.yml`, `lint.yml`).
- Production multi-stage Docker setup (`api/Dockerfile.prod`, `docker-compose.prod.yml`).
- Nginx configuration with rate-limiting and reverse proxy.
- Backup scripts (`pg_dump`, Redis RDB).
- Security hardening (CORS, Nginx headers, `SECRET_KEY` validation).
- Documentation (README, ARCHITECTURE.md, DEPLOYMENT.md).
- WordPress plugin finalization (fixing 5 warnings, Plugin Check).

### Out of Scope
- Dockerizing `llama-server` (will run as native host process).
- Cloud provider migration (sticking to local machine + Cloudflare Tunnel).
- End-to-end testing with Playwright (deferred).

## Capabilities

### New Capabilities
- `system-config`: Database-backed management of system configuration and scoring weights.
- `cicd-pipeline`: Automated testing and linting pipelines.
- `production-deployment`: Docker Compose prod environment with Nginx and Cloudflare Tunnel routing.
- `system-backup`: Automated data persistence snapshots.

### Modified Capabilities
- `voucher-scoring`: Loads dynamic scoring weights (`W_REF`, `W_TEXT`, `W_MONTO`, `W_FECHA`) from the database instead of hardcoded constants.

## Approach

1.  **Persistence**: Create SQLAlchemy model `ConfiguracionSistema`, generate Alembic migration, and refactor `duplicate_service.py` to read weights at startup with defaults fallback.
2.  **CI**: Create `.github/workflows/tests-api.yml` with `uv`, `pytest`, `postgres`, and `redis` services for full API tests. Create `lint.yml` (Ruff, Next.js lint, ESLint).
3.  **Docker Prod**: Create `api/Dockerfile.prod` using uv's multi-stage build pattern. Create `infra/docker-compose.prod.yml` routing internal traffic through an Nginx container.
4.  **Deployment**: Document Cloudflare Tunnel (`cloudflared-network`) routing to Nginx in `DEPLOYMENT.md`. Suggest local deploy via `docker compose pull && up -d`.
5.  **Backups**: Implement `infra/scripts/backup.sh` (pg_dump + gzip) and `infra/scripts/backup-redis.sh` (BGSAVE + copy RDB) with cron instructions.
6.  **Security**: Restrict `allow_origins`, validate `SECRET_KEY`, and add security headers to `nginx.conf`.
7.  **Docs & WP**: Write README, ARCHITECTURE.md, DEPLOYMENT.md. Finalize the 5 known warnings for `plugin-wp/` and run the official Plugin Check.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `api/models/` | New | `configuracion_sistema` model |
| `api/services/duplicate_service.py` | Modified | Use dynamic scoring weights |
| `.github/workflows/` | New | `tests-api.yml`, `lint.yml` |
| `api/Dockerfile.prod` | New | Multi-stage production build |
| `infra/docker-compose.prod.yml` | New | Production stack |
| `infra/nginx/nginx.conf` | New | Rate limiting & proxy |
| `infra/scripts/` | New | Backup scripts |
| `plugin-wp/` | Modified | Fix warnings for WP submission |
| Root | New | Documentation files |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Database weights delay scoring | Low | Cache weights on startup/request lifecycle |
| Missing Llama-server on prod | Low | Document requirement explicitly in DEPLOYMENT.md |

## Rollback Plan
- Revert codebase changes via Git.
- Restore PostgreSQL from `pg_dump` backup if the Alembic migration fails.
- Revert `docker-compose.prod.yml` to the previous state.

## Success Criteria
- [ ] API tests and lint pipelines pass successfully on PRs.
- [ ] `duplicate_service` calculates scores using database weights.
- [ ] `docker-compose.prod.yml` correctly spins up the API, WebApp, Postgres, Redis, Celery, and Nginx.
- [ ] Nginx proxies internal traffic and applies rate limits.
- [ ] Backup scripts produce valid archives.
- [ ] WordPress plugin passes the official `plugin-check` with 0 warnings.

---
*Engram observation ID: #324 | topic_key: sdd/fase-6-cicd/proposal*
