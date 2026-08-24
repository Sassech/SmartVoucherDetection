# Testing Guide

> Stack: Python 3.12 / FastAPI / pytest-asyncio (api) — Next.js / Vitest (webapp)
> Última actualización: 2026-08-24

## Estructura

```
api/
├── tests/
│   ├── conftest.py          # Fixtures compartidas (db_session, client, client_jwt, redis_client)
│   ├── unit/                # Tests unitarios sin DB (rápidos, <10s)
│   ├── integration/         # Tests contra Postgres real vía httpx.AsyncClient
│   └── e2e/                 # Playwright E2E (excluidos del run normal)
webapp/
├── src/**/__tests__/*.test.tsx   # Vitest + React Testing Library (co-locados)
└── e2e/                          # Playwright E2E
scripts/                         # Dataset tooling — sin tests
plugin-wp/comprobantes-ocr/      # Plugin WP — sin tests
```

## Requisitos previos

Los tests de integración necesitan **Postgres y Redis levantados**:

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
```

El `.env` del repo apunta a los hostnames internos de Docker (`postgres:5432`). Para correr tests **desde el host**, exportar las URLs de localhost antes de pytest:

```bash
cd api
export DATABASE_URL="$(grep '^DATABASE_URL' ../.env.local | cut -d= -f2-)"
export REDIS_URL="$(grep '^REDIS_URL' ../.env.local | cut -d= -f2-)"
```

> `.env.local` es la copia del `.env` con hostnames `localhost` para ejecución desde host. Está en `.gitignore`.

Si el volumen de Postgres es nuevo, aplicar migraciones primero:

```bash
uv run alembic upgrade head
```

## Correr los tests

### API

```bash
cd api

# Suite completa (unit + integration), excluye e2e
uv run pytest tests/unit tests/integration -q --ignore=tests/e2e

# Solo unit (sin DB necesaria)
uv run pytest tests/unit -q

# Un archivo específico
uv run pytest tests/unit/test_duplicate_service.py -v

# Con coverage (reporte para SonarQube)
uv run pytest tests/unit tests/integration \
  --cov=. --cov-report=xml:coverage.xml --ignore=tests/e2e
```

### Webapp

```bash
cd webapp

pnpm test                        # vitest run (una pasada)
pnpm test:watch                  # modo watch
pnpm exec vitest run --coverage  # con coverage lcov para Sonar
pnpm typecheck                   # tsc --noEmit
```

### E2E (opcional)

```bash
cd api && uv run pytest tests/e2e          # requiere servicios levantados
cd webapp && pnpm exec playwright test     # requiere webapp + api corriendo
```

## Baseline esperado (2026-08-24)

| Suite                    | Resultado                                                          |
| ------------------------ | ------------------------------------------------------------------ |
| api unit                 | 332 passed, 1 skipped (Postgres no reachable si no está levantado) |
| api integration (con DB) | **482 passed, 0 failed** (unit+integration combinado)              |
| api integration (sin DB) | ~70 skipped (`Postgres not reachable`)                             |
| webapp                   | 89 passed (15 files)                                               |

## Comportamiento clave de los fixtures (`api/tests/conftest.py`)

- **Engine por test**: cada test crea un engine local con `NullPool` porque pytest-asyncio abre un event loop nuevo por test; reusar conexiones del pool global lanza `RuntimeError: Event loop is closed`.
- **Transaccional + rollback**: cada test corre dentro de una transacción que se hace rollback al final — los INSERTs no contaminan la DB entre runs.
- **Override de dependencias**: `get_session`, `require_user`, `require_api_key` y `require_jwt` se override-an para usar la sesión del test y un usuario mock (`SYSTEM_USER_ID`).
- **Redis fake**: `redis_client` usa `fakeredis` — ningún test unitario necesita Redis real.
- **Skip automático**: si Postgres no responde, los tests de integración hacen `pytest.skip()` — la suite sigue verde en CI sin servicios.

## Coverage para SonarQube

```bash
# API -> api/coverage.xml (formato Cobertura XML)
cd api && uv run pytest tests/unit tests/integration \
  --cov=. --cov-report=xml:coverage.xml --ignore=tests/e2e

# Webapp -> webapp/coverage/lcov.info (formato LCOV)
cd webapp && pnpm exec vitest run --coverage
```

Ambos paths ya están configurados en `sonar-project.properties`:

```
sonar.python.coverage.reportPaths=api/coverage.xml
sonar.javascript.lcov.reportPaths=webapp/coverage/lcov.info
sonar.coverage.exclusions=scripts/**,plugin-wp/**,infra/scripts/**,api/alembic/**
```

Coverage actual: API ~80% line-rate, webapp ~38%.

## Consideraciones de testing

1. Los tests están bien — **no se modifican para hacerlos pasar**. Si un fix de código rompe un test, el fix está mal.
2. Antes de refactorizar, correr la suite como baseline y confirmar que queda igual al terminar.
3. Los tests usan duck typing (`cast(Comprobante, SimpleNamespace(...))`) para evitar overhead ORM — no instanciar modelos SQLAlchemy reales en unit tests.
4. `pytest-cov` con `core = "sysmon"` (Python 3.12) es obligatorio para coverage correcto de funciones async (ver comentario en `api/pyproject.toml`).
