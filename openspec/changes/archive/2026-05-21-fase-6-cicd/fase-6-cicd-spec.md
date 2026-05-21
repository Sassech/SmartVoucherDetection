# SDD Spec: fase-6-cicd

## ADDED Requirements

### Requirement: R-69 Persistence Configuration (6.4)
The system MUST read configuration weights from `ConfiguracionSistema` table, falling back to defaults.
- GIVEN the application starts
- WHEN `duplicate_service.py` is initialized
- THEN it loads W_REF, W_TEXT, W_MONTO, W_FECHA from the database
- AND uses hardcoded defaults if DB values are missing

### Requirement: R-70 GitHub Actions CI (6.5, 6.6)
The system MUST validate code quality and test coverage on PRs and pushes.
- GIVEN a PR or push event
- WHEN the CI workflow triggers
- THEN it runs `tests-api.yml` with Postgres 16 and Redis 7 services requiring >=70% coverage
- AND it runs `lint.yml` (ruff, next lint) without requiring secrets

### Requirement: R-71 Production Docker Stack (6.10, 6.11)
The system MUST run the API and Webapp via optimized multi-stage non-root containers behind Nginx.
- GIVEN `docker-compose.prod.yml`
- WHEN started
- THEN `api` and `webapp` run as non-root users
- AND Nginx proxies requests enforcing rate limits and forwarding CF-Connecting-IP

### Requirement: R-72 llama-server Docker (C2)
The llama-server MUST run as a separate service without bundling the model.
- GIVEN the `llama-server` image is built
- WHEN CPU-only args are passed (default)
- THEN the image is ~500MB without the model file
- AND the model is mounted via volume (`LLAMA_MODEL_PATH`)

### Requirement: R-73 Cloudflare Tunnel Deploy (6.8, 6.9)
The system MUST deploy automatically via SSH on designated branches/tags.
- GIVEN a push to `develop` or tag `v*`
- WHEN the deploy workflow runs
- THEN it connects via SSH key auth (no passwords)
- AND executes `docker compose pull && up -d` with appropriate profiles

### Requirement: R-74 Backup Scripts (6.12)
The system MUST perform idempotent automated backups.
- GIVEN the backup cron triggers
- WHEN the DB, Redis, or Images scripts run
- THEN they generate date-stamped backups safely even if run multiple times

### Requirement: R-75 Security Hardening (6.13)
The system MUST restrict CORS origins and validate startup secrets.
- GIVEN the API starts
- WHEN `SECRET_KEY` is loaded
- THEN it fails fast if length < 32 chars
- AND restricts CORS origins based on explicit settings (no `*`)

### Requirement: R-76 Documentation (6.14)
The system MUST provide deployment and architectural guides.
- GIVEN a developer joins
- WHEN they read the repo
- THEN `README.md`, `ARCHITECTURE.md`, and `DEPLOYMENT.md` reflect the current stack

### Requirement: R-77 WordPress.org Submission (6.15)
The plugin MUST pass WP.org automated checks.
- GIVEN the Phase 3 warnings
- WHEN the plugin is packaged
- THEN it resolves W-01 to W-05 warnings and updates the `Tested up to` tag

---
*Engram observation ID: #325 | topic_key: sdd/fase-6-cicd/spec*
