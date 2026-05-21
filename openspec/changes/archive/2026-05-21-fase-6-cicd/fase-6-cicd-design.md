# Design: fase-6-cicd

## Technical Approach

Extend the existing FastAPI/PostgreSQL/Redis/Celery monorepo to production-readiness via: (1) DB-backed configuration model for scoring weights, (2) GitHub Actions CI (tests + lint), (3) multi-stage production Dockerfiles for api + webapp + llama, (4) docker-compose.prod.yml with nginx proxy + Cloudflare Tunnel network, (5) SSH-based deploy workflows, (6) idempotent backup scripts, (7) security hardening (CORS, SECRET_KEY, rate limiting). All new settings extend `api/config.py` BaseSettings pattern; new model follows SoftDeleteMixin-less key/value table.

---

## Architecture Decisions

### Decision: ConfiguracionSistema — simple key/value table, no SoftDelete

**Choice**: `VARCHAR PK key, TEXT value, TIMESTAMPTZ updated_at` — no UUID PK, no SoftDeleteMixin  
**Alternatives**: config in environment variables, UUID PK with soft delete  
**Rationale**: Config entries are identified by their key (natural PK). No delete semantics needed — keys are seeded and updated, never removed. Avoids UUID overhead for a tiny table.

### Decision: Weight loading — module-level lazy singleton, not per-request

**Choice**: `_weights_cache: ScoringWeights | None = None` initialized on first call to `get_scoring_weights()`, invalidated by explicit `reload_weights()` call  
**Alternatives**: per-request DB load, app startup event  
**Rationale**: Weights change rarely (admin action). Per-request DB query is wasteful. Startup event doesn't work for Celery workers. Module-level lazy init works across all process types. Cache invalidation is explicit (admin endpoint or process restart).

### Decision: CI caching — uv cache via actions/cache, not pip cache

**Choice**: `cache-dependency-path: api/uv.lock` with `~/.cache/uv` cache path  
**Alternatives**: pip wheel cache, Docker layer cache  
**Rationale**: Project uses uv exclusively. uv's cache is separate from pip's. Matching lock file as cache key gives correct invalidation.

### Decision: Gunicorn + UvicornWorker, NOT `fastapi run`

**Choice**: `gunicorn -k uvicorn.workers.UvicornWorker -w 4 main:app`  
**Alternatives**: `uvicorn` directly, `fastapi run`  
**Rationale**: Gunicorn provides process supervision, graceful restart, and worker recycling that bare uvicorn lacks. UvicornWorker preserves full ASGI async behavior. `-w 4` = 2×CPU default, configurable via `$GUNICORN_WORKERS` env var.

### Decision: llama image — ubuntu:24.04 base, no CUDA by default

**Choice**: Multi-stage ubuntu:24.04; build args `GGML_AVX2=ON`, `GGML_CUDA=OFF`; model volume only  
**Alternatives**: Official llama.cpp Docker image, alpine base  
**Rationale**: alpine lacks glibc needed for AVX intrinsics. Official image may include CUDA layers (+2GB). ubuntu:24.04 is LTS, well-known APT deps. Model volume prevents image bloat and allows model updates without rebuild.

### Decision: Deploy — appleboy/ssh-action + host-side deploy.sh script

**Choice**: `appleboy/ssh-action@v1` executes `~/deploy.sh` on host  
**Alternatives**: raw SSH step, Ansible, Kamal  
**Rationale**: `appleboy/ssh-action` handles known_hosts fingerprint and key injection cleanly. Host-side script decouples CI from deployment logic (rollback, env selection). Single script is auditable.

### Decision: nginx — separate container in compose.prod.yml, not host-level

**Choice**: `nginx:alpine` service in compose.prod.yml on `cloudflared-network`  
**Alternatives**: host nginx, Traefik  
**Rationale**: Cloudflare Tunnel connects to nginx container on `cloudflared-network` bridge. Traefik adds complexity not needed here. nginx:alpine is minimal and well-understood.

---

## Data Flow

```
[A] ConfiguracionSistema weight loading:

  App startup (any worker)
       │
       ▼
  get_scoring_weights()
       │  _weights_cache is None?
       ├─YES→ SELECT * FROM configuracion_sistema
       │         WHERE key IN (w_ref, w_text, w_monto, w_fecha)
       │       build ScoringWeights dataclass
       │       set _weights_cache
       └─NO→  return _weights_cache
       │
       ▼
  compute_score() uses ScoringWeights fields

[B] Production request flow:

  Internet → Cloudflare Tunnel
       → nginx:alpine (rate limit, real IP, headers)
       → api:8000 (gunicorn+uvicorn workers)
       → postgres / redis

  webapp:3000 → nginx upstream (Next.js standalone server)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `api/models/configuracion_sistema.py` | Create | SQLAlchemy model: key/value + updated_at |
| `api/models/__init__.py` | Modify | Export ConfiguracionSistema so alembic autogenerate picks it up |
| `api/services/config_service.py` | Create | `get_scoring_weights()`, `reload_weights()`, `ScoringWeights` dataclass |
| `api/services/duplicate_service.py` | Modify | Replace module-level W_* constants with `get_scoring_weights()` call in `compute_score()` |
| `api/config.py` | Modify | Add `secret_key: str`, `cors_origins: list[str]`, `gunicorn_workers: int = 4`; add `model_validator` to assert `len(secret_key) >= 32` |
| `api/main.py` | Modify | Change `allow_origins=[settings.webapp_origin]` → `allow_origins=settings.cors_origins` |
| `api/alembic/versions/xxxx_configuracion_sistema.py` | Create | CREATE TABLE + seed INSERT for 4 weights (ON CONFLICT DO NOTHING) |
| `api/Dockerfile.prod` | Create | Multi-stage builder→runtime, non-root `appuser`, gunicorn entrypoint, HEALTHCHECK |
| `webapp/Dockerfile.prod` | Create | Next.js standalone output, non-root user |
| `infra/Dockerfile.llama` | Create | Multi-stage ubuntu:24.04 build+runtime, llama-server binary only |
| `infra/docker-compose.prod.yml` | Create | All services + nginx + llama on smartvoucher-net + cloudflared-network |
| `infra/nginx/nginx.conf` | Create | Upstreams, rate limits, CF real IP, security headers |
| `.github/workflows/tests-api.yml` | Create | pytest with postgres:16-alpine + redis:7-alpine services, coverage ≥70% |
| `.github/workflows/lint.yml` | Create | ruff check + ruff format --check + next lint |
| `.github/workflows/deploy-staging.yml` | Create | push to develop → SSH deploy |
| `.github/workflows/deploy-production.yml` | Create | tag v* → SSH deploy |
| `infra/scripts/backup-db.sh` | Create | pg_dump + gzip + dated filename + optional rclone |
| `infra/scripts/backup-redis.sh` | Create | BGSAVE + RDB copy |
| `infra/scripts/backup-images.sh` | Create | rclone sync data/uploads/ |
| `infra/scripts/deploy.sh` | Create | Host-side deploy script (pull + up -d + prune) |
| `api/tests/test_configuracion_sistema.py` | Create | Unit + integration tests for ConfiguracionSistema model and config_service |
| `docs/README.md` | Modify | Update with current stack |
| `docs/ARCHITECTURE.md` | Create | Architecture overview |
| `docs/DEPLOYMENT.md` | Create | Deployment guide |

---

## Interfaces / Contracts

```python
# api/models/configuracion_sistema.py
class ConfiguracionSistema(Base):
    __tablename__ = "configuracion_sistema"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

# api/services/config_service.py
@dataclass
class ScoringWeights:
    w_ref: float = 0.35
    w_text: float = 0.30
    w_monto: float = 0.20
    w_fecha: float = 0.15

_weights_cache: ScoringWeights | None = None

async def get_scoring_weights(session: AsyncSession) -> ScoringWeights: ...
def reload_weights() -> None:  # sets _weights_cache = None
    global _weights_cache; _weights_cache = None

# api/config.py additions
class Settings(BaseSettings):
    secret_key: str  # no default — must be set
    cors_origins: list[str] = ["http://localhost:3000"]
    gunicorn_workers: int = 4

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return self
```

**nginx rate limit zones**:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
limit_req_zone $binary_remote_addr zone=web_limit:10m rate=300r/m;
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | ScoringWeights dataclass defaults, weight fallback logic, SECRET_KEY validator | pytest, no DB |
| Integration | ConfiguracionSistema CRUD, get_scoring_weights() reads from DB, migration idempotency | pytest + real postgres (CI service) |
| Integration | duplicate_service.compute_score() uses DB weights | patch `get_scoring_weights` return |
| CI | tests-api.yml runs all 425+ tests with coverage ≥70% | GitHub Actions matrix |

---

## Migration / Rollout

1. Alembic migration `xxxx_configuracion_sistema`: CREATE TABLE + seed 4 rows (idempotent via ON CONFLICT DO NOTHING)
2. `duplicate_service.py` weight constants remain as fallback defaults in `ScoringWeights` dataclass — no behavioral change if table has no rows
3. `config.py` `secret_key` field: existing `.env` files must add `SECRET_KEY=<32+ chars>` — fail-fast on startup catches missing config before any traffic
4. `cors_origins` list replaces `webapp_origin` single string — `.env` updated; `main.py` reads new field
5. Dockerfile.prod: replaces `Dockerfile.dev` for production only — dev workflow unchanged

---
*Engram observation ID: #326 | topic_key: sdd/fase-6-cicd/design*
