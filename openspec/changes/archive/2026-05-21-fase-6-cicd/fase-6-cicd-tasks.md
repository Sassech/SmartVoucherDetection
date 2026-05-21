# SDD Tasks: fase-6-cicd

**Total**: 22 tasks | 5 chained PRs | All complete ✅

## Group 6.A — configuracion_sistema (R-69)

### 6.A.1 — Create ConfiguracionSistema model and migration ✅ PR-A
**Files**: `api/models/configuracion_sistema.py`, `api/models/__init__.py`, `api/alembic/versions/a7f3b9c1d2e4_configuracion_sistema.py`

### 6.A.2 — Create config_service with lazy weight cache ✅ PR-A
**Files**: `api/services/config_service.py`

### 6.A.3 — Wire config_service into duplicate_service ✅ PR-A
**Files**: `api/services/duplicate_service.py`

---

## Group 6.B — GitHub Actions CI (R-70)

### 6.B.1 — Create tests-api.yml workflow ✅ PR-B
**Files**: `.github/workflows/tests-api.yml`

### 6.B.2 — Create lint.yml workflow + ESLint config ✅ PR-B
**Files**: `.github/workflows/lint.yml`, `webapp/.eslintrc.json`

---

## Group 6.C — Production Docker stack (R-71)

### 6.C.1 — Add output:standalone to next.config.ts ✅ PR-C
**Files**: `webapp/next.config.ts`

### 6.C.2 — Create api/Dockerfile.prod ✅ PR-C
**Files**: `api/Dockerfile.prod`

### 6.C.3 — Create webapp/Dockerfile.prod ✅ PR-C
**Files**: `webapp/Dockerfile.prod`

### 6.C.4 — Create infra/nginx/nginx.conf ✅ PR-C
**Files**: `infra/nginx/nginx.conf`

### 6.C.5 — Create infra/docker-compose.prod.yml ✅ PR-C
**Files**: `infra/docker-compose.prod.yml`, `.env.example`

---

## Group 6.C2 — llama-server Docker (R-72)

### 6.C2.1 — Create infra/Dockerfile.llama ✅ PR-C
**Files**: `infra/Dockerfile.llama`

### 6.C2.2 — Add llama-server to docker-compose.prod.yml ✅ PR-C (merged with 6.C.5)
**Files**: `infra/docker-compose.prod.yml`

---

## Group 6.D — Deploy workflows (R-73)

### 6.D.1 — Create host deploy.sh script ✅ PR-D
**Files**: `infra/scripts/deploy.sh`

### 6.D.2 — Create deploy-staging.yml workflow ✅ PR-D
**Files**: `.github/workflows/deploy-staging.yml`

### 6.D.3 — Create deploy-production.yml workflow ✅ PR-D
**Files**: `.github/workflows/deploy-production.yml`

---

## Group 6.E — Backup scripts (R-74)

### 6.E.1 — Create backup-db.sh ✅ PR-D
**Files**: `infra/scripts/backup-db.sh`

### 6.E.2 — Create backup-redis.sh and backup-images.sh ✅ PR-D
**Files**: `infra/scripts/backup-redis.sh`, `infra/scripts/backup-images.sh`

---

## Group 6.F — Security hardening (R-75)

### 6.F.1 — SECRET_KEY validation + CORS from settings ✅ PR-A
**Files**: `api/config.py`, `api/main.py`

---

## Group 6.G — Documentation (R-76)

### 6.G.1 — Create README.md ✅ PR-E
**Files**: `README.md`

### 6.G.2 — Create ARCHITECTURE.md and DEPLOYMENT.md ✅ PR-E
**Files**: `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`

---

## Group 6.H — WordPress.org (R-77)

### 6.H.1 — Fix Phase 3 warnings W-02 through W-05 ✅ PR-E
**Files**: `plugin-wp/comprobantes-ocr/admin/history-widget.php`, `plugin-wp/comprobantes-ocr/languages/comprobantes-ocr-es_MX.po`

### 6.H.2 — Plugin Check + submission prep ✅ PR-E
**Files**: `plugin-wp/comprobantes-ocr/readme.txt`, `plugin-wp/comprobantes-ocr/PLUGIN-CHECK.md`

---

## Review Workload Forecast

| PR | Tasks | Focus | ~Lines |
|----|-------|-------|--------|
| PR-A | 6.A.1–6.A.3 + 6.F.1 | Config DB + Security base | ~205 |
| PR-B | 6.B.1–6.B.2 | GitHub Actions CI | ~125 |
| PR-C | 6.C.1–6.C.5 + 6.C2.1–6.C2.2 | Docker prod stack | ~373 |
| PR-D | 6.D.1–6.D.3 + 6.E.1–6.E.2 | Deploy + Backups | ~255 |
| PR-E | 6.G.1–6.G.2 + 6.H.1–6.H.2 | Docs + WP.org | ~500 |

---
*Engram observation ID: #327 | topic_key: sdd/fase-6-cicd/tasks*
