# SmartVoucherDetection — SDD Project Context

**Initialized**: 2026-05-09  
**Mode**: openspec (file-based)  
**Strict TDD**: enabled

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Package manager | uv |
| Web framework | FastAPI 0.136+ (async) |
| ORM | SQLAlchemy 2.0 async (asyncpg driver) |
| Database | PostgreSQL 16 (Docker) |
| Cache / broker | Redis 7 (Docker) |
| Async tasks | Celery + Redis |
| OCR engine | llama.cpp server (external HTTP) |
| Image processing | OpenCV (headless), Pillow, pdf2image |
| Migrations | Alembic |
| Linter / formatter | Ruff |
| Pre-commit | pre-commit (ruff + whitespace/yaml/toml hooks) |
| Containerization | Docker Compose (`infra/docker-compose.yml`) |

---

## Project Layout

```
SmartVoucherDetection/
├── api/                    # FastAPI application
│   ├── main.py             # App entry point, CORS, router registration
│   ├── config.py           # Pydantic settings
│   ├── database.py         # Async SQLAlchemy engine + session
│   ├── routers/            # health.py, history.py, upload.py
│   ├── services/           # cache_service, image_service, ocr_service,
│   │                       # parser_service, storage_service
│   ├── models/             # SQLAlchemy models (+ seed.py)
│   ├── schemas/            # Pydantic schemas
│   ├── tasks/              # Celery task definitions
│   ├── alembic/            # DB migrations
│   └── tests/              # 174 pytest tests (12 test files)
├── infra/
│   ├── docker-compose.yml  # PostgreSQL 16 + Redis 7
│   └── init-db.sql         # One-time DB initialization
├── webapp/                 # (frontend, separate concern)
├── plugin-wp/              # WordPress plugin
├── docs/                   # Project documentation
├── openspec/               # SDD artifact store (this directory)
└── .pre-commit-config.yaml
```

---

## Testing Capabilities

**Strict TDD Mode**: enabled  
**Test count**: 174 passing (confirmed 2026-05-09)  
**Coverage threshold**: 70% global (`fail_under = 70`); actual ~96%

### Test Runner
- **Command**: `cd api && uv run pytest tests/ -q`
- **Framework**: pytest 9.0+ with pytest-asyncio (`asyncio_mode = auto`)
- **Coverage**: `cd api && uv run pytest tests/ --cov --cov-report=term-missing`

### Test Layers

| Layer | Available | Tool / Notes |
|-------|-----------|--------------|
| Unit | ✅ | pytest — services, models |
| Integration | ✅ | httpx + ASGITransport (ASGI TestClient) |
| E2E | ❌ | — |

### Test Files
- `test_cache_service.py` — Redis cache service unit tests
- `test_database.py` — DB connectivity
- `test_health_endpoint.py` — `/health` router integration
- `test_history_endpoint.py` — `/history` router integration
- `test_image_service.py` — image processing unit tests
- `test_ocr_service.py` — OCR service unit tests
- `test_parser_service.py` — parser service unit tests
- `test_storage_service.py` — storage service unit tests
- `test_upload_endpoint.py` — `/upload` router integration

### Quality Tools

| Tool | Available | Command |
|------|-----------|---------|
| Linter | ✅ | `uv run ruff check api/` |
| Formatter | ✅ | `uv run ruff format api/` |
| Type checker | ❌ | Not configured (no mypy/pyright) |

---

## Key Conventions

- All services are async (`async def`) — use `await` everywhere.
- Coverage uses `sysmon` core (Python 3.12 sys.monitoring) for accurate async coverage.
- `alembic/` and `models/seed.py` are excluded from coverage reporting.
- CORS is open (`allow_origins=["*"]`) during dev; will be tightened in Fase 4.
- `.env` at project root is loaded by both Docker Compose and the API config.
- `$$VAR` in Docker Compose healthchecks escapes Compose interpolation (resolves inside container).

---

## SDD Phase Map

| Phase | Artifact path |
|-------|--------------|
| Proposal | `openspec/changes/{id}-proposal.md` |
| Spec | `openspec/specs/{id}-spec.md` |
| Design | `openspec/changes/{id}-design.md` |
| Tasks | `openspec/changes/{id}-tasks.md` |
| Apply | `openspec/changes/{id}-apply.md` |
| Verify | `openspec/changes/{id}-verify.md` |
| Archive | `openspec/changes/archive/{id}-archive.md` |
