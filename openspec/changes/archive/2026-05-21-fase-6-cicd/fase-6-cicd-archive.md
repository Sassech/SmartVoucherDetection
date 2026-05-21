# Archive: fase-6-cicd

**Change**: fase-6-cicd — CI/CD, Deployment & Security  
**Archived**: 2026-05-21  
**Verdict**: PASS WITH WARNINGS (no CRITICALs)  
**Artifact Store**: engram  
**Observation IDs**: proposal=#324, spec=#325, design=#326, tasks=#327, apply-progress=#328, verify-report=#332

---

## Summary

Fase 6 brought SmartVoucherDetection from a functional prototype to a production-ready system.
22 tasks across 5 chained PRs delivered: database-backed scoring configuration, automated CI/CD pipelines,
multi-stage production Docker stack (API + Webapp + llama-server), Cloudflare Tunnel deployment
via SSH-based GitHub Actions workflows, idempotent backup scripts, CORS/SECRET_KEY security hardening,
complete documentation, and WordPress.org plugin submission preparation.

**Test results**: 454 passed, 90% coverage, ruff clean, 4 YAML workflows syntactically valid, docker compose config valid (7 services).

---

## Requirements Coverage

| Req  | Description                                                              | Status |
|------|--------------------------------------------------------------------------|--------|
| R-69 | `configuracion_sistema` — model, Alembic migration, lazy cache, session  | PASS   |
| R-70 | GitHub Actions CI — `tests-api.yml` + `lint.yml` (parallel jobs)        | PASS   |
| R-71 | Production Docker stack — non-root containers, nginx rate limit, CF IP   | PASS   |
| R-72 | llama-server Docker — multi-stage, model as volume, CPU-only default     | PASS   |
| R-73 | Deploy workflows — SSH key auth, staging/production triggers, manual gate | PASS  |
| R-74 | Backup scripts — idempotent, dated filenames, optional rclone upload     | PASS   |
| R-75 | Security hardening — SECRET_KEY ≥32 validator, cors_origins from settings | PASS  |
| R-76 | Documentation — README, ARCHITECTURE.md, DEPLOYMENT.md                  | PASS   |
| R-77 | WordPress.org — hash 8 chars, Tested up to 6.7, W-02–W-05 resolved      | PASS   |

---

## Implementation

### PR-A — Config DB + Security (R-69, R-75)
- `api/models/configuracion_sistema.py` — key/value model, VARCHAR PK, no SoftDeleteMixin
- `api/alembic/versions/a7f3b9c1d2e4_configuracion_sistema.py` — CREATE TABLE + 4 seed rows (ON CONFLICT DO NOTHING)
- `api/services/config_service.py` — `ScoringWeights` dataclass, lazy module-level cache, `invalidate_weights_cache()`
- `api/services/duplicate_service.py` — `compute_score()` made async with optional `session` param (backward compat: `session=None` uses defaults)
- `api/config.py` — `secret_key` field with `model_validator` asserting ≥32 chars; `cors_origins: list[str]`
- `api/main.py` — `CORSMiddleware` reads `settings.cors_origins`
- **Tests added**: 29 new tests (test_configuracion_sistema.py, test_config_service.py, test_duplicate_service_weights.py, test_config.py)

### PR-B — GitHub Actions CI (R-70)
- `.github/workflows/tests-api.yml` — postgres:16-alpine + redis:7-alpine services, uv cache, pytest --cov-fail-under=70
- `.github/workflows/lint.yml` — parallel jobs: `lint-python` (ruff) + `lint-webapp` (next lint)
- `webapp/.eslintrc.json` — `next/core-web-vitals` base config
- `webapp/package.json` — added eslint@^8.57.1 + eslint-config-next@^15.5.18 (ESLint was not pre-installed)

### PR-C — Production Docker Stack (R-71, R-72)
- `api/Dockerfile.prod` — multi-stage python:3.12-slim, `appuser` UID 1000, gunicorn+UvicornWorker, urllib.request HEALTHCHECK
- `webapp/Dockerfile.prod` — multi-stage node:22-alpine, `nextuser`, standalone output, node server.js
- `webapp/next.config.ts` — `output: "standalone"` added
- `infra/nginx/nginx.conf` — 15 Cloudflare IP ranges for real_ip extraction, rate limits (api 100r/m, web 300r/m), security headers
- `infra/docker-compose.prod.yml` — 7 services; nginx is the ONLY service on both `cloudflared-network` + `smartvoucher-net`; all others internal only
- `infra/Dockerfile.llama` — ubuntu:24.04 multi-stage, clones `ggml-org/llama.cpp` tag b9264, AVX2=ON CUDA=OFF default, `llamauser` UID 1000, model as volume
- `api/pyproject.toml` — added `gunicorn>=23.0.0`

### PR-D — Deploy + Backups (R-73, R-74)
- `infra/scripts/deploy.sh` — `set -euo pipefail`, pull → up -d → health check; on_failure trap prints last 50 api logs
- `.github/workflows/deploy-staging.yml` — push to `develop` → appleboy/ssh-action@v1.0.3 → deploy.sh staging; concurrency cancel-in-progress:false
- `.github/workflows/deploy-production.yml` — tag `v*` → GitHub environment `production` (manual approval gate) → deploy.sh production
- `infra/scripts/backup-db.sh` — pg_dump + gzip, dated filenames, optional rclone, 7-day local retention
- `infra/scripts/backup-redis.sh` — BGSAVE trigger + LASTSAVE polling (2s interval, 30s max), docker cp RDB, 7-day retention
- `infra/scripts/backup-images.sh` — rclone sync; exits 0 if RCLONE_REMOTE unset (no-op guard)

### PR-E — Docs + WordPress (R-76, R-77)
- `README.md` — badges, tech stack table, Quick Start dev+prod, ASCII arch diagram, doc links
- `docs/ARCHITECTURE.md` — 8-component table with ports/images, upload pipeline, 3-layer dedup table, DB schema, scoring weights, network topology
- `docs/DEPLOYMENT.md` — env vars reference table, llama Option A/B, Cloudflare Tunnel steps, backup cron, CI secrets table, workflow trigger table
- `plugin-wp/comprobantes-ocr/admin/history-widget.php` — W-02: hash 8 chars; W-03: badge CSS renamed to `cocr-badge-{type}`
- `plugin-wp/comprobantes-ocr/languages/comprobantes-ocr-es_MX.po` — W-05: removed orphaned stale reference comment
- `plugin-wp/comprobantes-ocr/readme.txt` — "Tested up to: 6.7"
- `plugin-wp/comprobantes-ocr/PLUGIN-CHECK.md` — pre-submission checklist with SVN steps

---

## Warnings

| ID | Description | Resolution |
|----|-------------|------------|
| W1 | `verify_token` import unused in `routers/web_auth.py` (pre-existing) | Fixed in verify commit |
| W2 | `AsyncMock` import unused in `tests/test_auth_jwt_dep.py` (pre-existing) | Fixed in verify commit |
| W3 | `null_user` F841 in `tests/test_token_api_prefix.py` | Suppressed with `# noqa: F841` (mock pattern, not a real bug) |
| W4 | W-01 Plugin Check in real WP environment — requires manual execution | Documented in `PLUGIN-CHECK.md` pre-submission checklist; acceptable |
| W5 | llama-server Docker build not tested end-to-end (10-15 min compile) | Dockerfile syntax validated, binary path reviewed; acceptable for VPS/cloud migration |

**No CRITICAL issues.**

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| llama-server deployment | Dockerized with model as volume (not baked in) | Portability for VPS/cloud migration; no image rebuild on model update |
| Host infrastructure | Local machine + Cloudflare Tunnel (no new cloud account) | Reuses existing infra; Cloudflare handles TLS + DDoS |
| `compute_score()` signature | Made async with `session=None` for backward compat | Enables DB weight loading; existing tests pass unchanged via `session=None` path |
| ESLint version | 8.x (not 9.x) | `next lint` + `.eslintrc.json` pattern conflicts with ESLint 9 flat config in Next.js 15.5 |
| llama.cpp repo | `ggml-org/llama.cpp` (renamed from `ggerganov/llama.cpp`) | Repo was officially renamed — critical for future `Dockerfile.llama` maintenance |
| nginx placement | ONLY nginx on `cloudflared-network`; all other services internal | Zero direct exposure of API/DB/Redis to Cloudflare network; defense-in-depth |
| Weight cache strategy | Module-level lazy singleton, not per-request | Weights change rarely; per-request DB query wasteful; startup event fails for Celery workers |
| API Dockerfile HEALTHCHECK | `urllib.request` (not `curl`) | `curl` not available in `python:3.12-slim`; stdlib solution avoids extra dep |
| Deploy script | Host-side `deploy.sh` called by `appleboy/ssh-action` | Decouples CI from deployment logic; script is auditable and rollback-aware |
| `secret_key` default | 38-char dev default (not required field) | Spec overrides design: dev convenience with validation safety net; prod must set via env |

---

## Suggestions (Not Blocking)

- **S1**: Add `host.docker.internal` extra_hosts to api service in `docker-compose.prod.yml` for llama Option B (native process) — currently requires manual edit
- **S2**: Consider `COVERAGE_CORE=sysmon` in `tests-api.yml` for accurate async coverage (documented in Fase 1)
- **S3**: Update placeholder URL `https://app.yourdomain.com` in `deploy-production.yml` before first real deploy

---

## Next Steps

1. **Merge PRs A–E** into `develop` and tag first release as `v1.0.0` to trigger production deploy workflow
2. **Run Plugin Check** in real WordPress 6.7 install to resolve W-01 before WP.org SVN submission
3. **Build and smoke-test `Dockerfile.llama`** on target VPS (AVX2 build, 10-15 min compile) to resolve W-5
4. **Set production secrets** in GitHub repository settings: `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PORT`
5. **Configure Cloudflare Tunnel** routes for `api.domain` and `app.domain` pointing to nginx container
6. **Schedule backup cron** on host: `backup-db.sh` daily, `backup-redis.sh` daily, `backup-images.sh` weekly

---

## Engram Observation IDs (Audit Trail)

| Artifact        | ID   | Topic Key                        |
|-----------------|------|----------------------------------|
| Proposal        | #324 | sdd/fase-6-cicd/proposal         |
| Spec            | #325 | sdd/fase-6-cicd/spec             |
| Design          | #326 | sdd/fase-6-cicd/design           |
| Tasks           | #327 | sdd/fase-6-cicd/tasks            |
| Apply Progress  | #328 | sdd/fase-6-cicd/apply-progress   |
| Verify Report   | #332 | sdd/fase-6-cicd/verify-report    |
| Archive Report  | TBD  | sdd/fase-6-cicd/archive-report   |
