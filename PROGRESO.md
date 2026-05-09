# PROGRESO — SmartVoucherDetection

> **Cómo usar este archivo (leer SIEMPRE al iniciar una sesión nueva):**
>
> 1. Buscá el primer `[ ]` (sin marcar) — ahí retomás.
> 2. Marcá `[x]` apenas terminés un paso. **Commit inmediato** del cambio en `PROGRESO.md`.
> 3. Si tomás una decisión técnica nueva, agregala en **§ Decisiones Técnicas**.
> 4. Si descubrís un gotcha, agregalo en **§ Notas y Gotchas** al final.
> 5. NO avances al siguiente paso si el criterio de aceptación del actual no se cumple.

---

## Estado Actual

- **Última fase activa:** Fase 1 — **EN CURSO** (1.1 a 1.7 + 1.8.1–1.8.2 cerradas)
- **Última tarea completada:** `1.8.2` — E2E de `POST /upload-slip` (6 tests) reusando `client`+`db_session` del conftest. Monkeypatch selectivo de `routers.upload.extract_fields` (mock OCR) y `routers.upload.save_upload` (no toca disco). Casos: happy path (201 + fila en DB), MIME inválido (400), >10MB (413), vacío (400), hash duplicado (409 con id existente), OCR 503 (propaga). Suite 174/174 en 0.97s.
- **Próximo paso:** **Fase 1 — `1.8.3`** (coverage gate: `pytest --cov=. --cov-report=term --cov-fail-under=70` desde `api/`). Validar que `services/` tenga ≥70% (probable que ya esté arriba: image_service, ocr_service, parser_service, storage_service y cache_service tienen tests dedicados). Decidir si dejar el threshold global en 70% o subirlo solo para `services/`. Si algún servicio queda por debajo, agregar tests específicos antes de cerrar 1.8.
  - **Plan acordado anterior (1.7.2, ya implementado — referencia historica):**
    1. **Crear `services/cache_service.py` mínimo ahora** (opción B), no instanciar `redis.asyncio` ad-hoc en el endpoint de health. Le da hogar correcto al cliente Redis desde el inicio y evita refactor cuando llegue 2.1.1 (que agrega `check_hash` al mismo módulo).
    2. **Contrato del módulo en 1.7.2:** una sola función pública `async def ping(timeout_s: float = 1.0) -> bool` que devuelve `True` si Redis responde `PONG` dentro del timeout, `False` en cualquier error/timeout. NO levanta excepción (el endpoint health no debe romper si Redis está caído — solo reporta `ok=False`). Cliente Redis con pool global del módulo (no abrir/cerrar conexión por request).
    3. **Tres chequeos del health:**
       - **llama-server**: `httpx.AsyncClient.get("/health")` con timeout 1s. `detail` con latencia en ms (`"42ms"`) o mensaje de error.
       - **postgres**: `await session.execute(text("SELECT 1"))` via dependency `get_session`. Latencia en `detail`.
       - **redis**: `cache_service.ping()`. Latencia en `detail`.
    4. **Ejecutar los 3 chequeos en paralelo** con `asyncio.gather(..., return_exceptions=True)` — si los hacemos secuenciales, el peor caso es ~3s; en paralelo es max(individual). Importante porque el endpoint puede llamarse desde un load balancer cada N segundos.
    5. **Endpoint responde 200 SIEMPRE** (incluso con `ok=False` en todos). El HTTP indica que la API responde; los flags indican qué dependencia está degradada. Solo 503 si la API no puede ni armar el response (caso patológico).
    6. **Tests:** monkeypatch del cliente httpx (mock para llama), session de test, y monkeypatch de `cache_service.ping`. Casos: todos OK, llama caído, db caído, redis caído, timeouts.
- **Bloqueadores:** ninguno

---

## Decisiones Técnicas (NO se discuten de nuevo)

| #    | Decisión                                                                               | Justificación                                                                                                         | Fecha      |
| ---- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------- |
| D-01 | **PostgreSQL desde día 1** (no SQLite)                                                 | `pg_trgm` es crítico para Fase 2 (scoring de duplicados). Migrar después = rehacer modelos y tests.                   | 2026-05-08 |
| D-02 | **Python 3.12** (no 3.14, no 3.11)                                                     | 3.12 tiene wheels prebuilt para OpenCV/pdf2image/asyncpg, soporte hasta 2028. 3.14 muy nuevo, 3.11 ya quedando atrás. | 2026-05-08 |
| D-03 | **Monorepo `/api`, `/plugin-wp`, `/webapp`, `/infra`, `/tests`, `/docs`** desde Fase 0 | Evitar reestructuración traumática en Fase 3.                                                                         | 2026-05-08 |
| D-04 | **Tracking en `PROGRESO.md`** (versionado en Git)                                      | Portable, no depende de herramientas externas.                                                                        | 2026-05-08 |
| D-05 | **PK = UUID v7 client-side** (lib `uuid-utils` o `uuid6` en Python, no `gen_random_uuid()`) | UUID v7 es ordenable por tiempo → mejor performance de índices B-tree en inserts vs v4. Postgres 16 no trae `uuidv7()` nativa (sí PG18+). Se genera en app via `default=...` de SQLAlchemy. | 2026-05-09 |
| D-06 | **Soft delete con `deleted_at TIMESTAMPTZ NULL`** en Organizacion/Usuario/Comprobante/Validacion. LogProcesamiento queda hard delete. | Auditoría requerida por CU-02 (validación manual de duplicados detectados). Logs no necesitan recuperación: políticas de retención por TTL, no soft delete. | 2026-05-09 |
| D-07 | **`uuid-utils` para UUID v7**, **VARCHAR + CHECK constraint** para enums (no `ENUM` nativo Postgres), **bcrypt hash** para `token_api_hash` (renombrado desde `token_api` del ERD). | uuid-utils es Rust-backed (~5x más rápido que uuid6). CHECK permite ALTER TABLE simple para cambiar valores (vs `ALTER TYPE` doloroso). `token_api_hash` deja claro que NO es plain — convención GitHub/Stripe: el plain solo se muestra al usuario una vez. | 2026-05-09 |
| D-08 | **Pipeline OpenCV con orden invertido respecto al plan**: deskew (paso 4 del plan) se aplica ANTES de adaptiveThreshold (paso 3). | `cv2.warpAffine` usa interpolación bilineal/cubica que rompe la binarización: rotar una imagen ya en {0,255} produce píxeles intermedios en los bordes del texto. Lo correcto en pipelines OCR es rotar la grayscale y binarizar después. Documentado en `image_service.py`. | 2026-05-09 |
| D-09 | **Política de retry conservadora en OCR**: tenacity reintenta SOLO en `httpx.RequestError` o 5xx. 4xx → `HTTPException(502)` sin retry. JSON inválido en `content` → `HTTPException(503)` sin retry. | Patrón Stripe/AWS: nunca reintentar errores no idempotentes (4xx = contrato roto, no se arregla con retry). JSON malformado del LLM con `temperature=0` no se corrige reintentando — es un problema de prompt/modelo, escalar a 503 es lo correcto. | 2026-05-09 |
| D-10 | **Parser tolerante (devuelve `None` en input inválido) + monto US-style + banco fuzzy**: (a) `parse_monto/fecha/referencia` retornan `None` ante input vacío/sucio; (b) monto asume coma=miles, punto=decimal (formato MX bancario); (c) `normalize_banco` usa `Levenshtein.ratio ≥ 0.85` + substring match para aliases ≥4 chars, fallback `"OTRO"`. | (a) GLM-OCR puede emitir `null` por campo no detectado; preferimos persistir parcial que romper el flujo (el endpoint decide marcar `error`). (b) Heurísticas europeas se evalúan en Fase 5 con dataset real. (c) Fuzzy absorbe los confusos del OCR (`MÉXICO→MÁXICO`); substring evita falsos negativos en frases tipo "BBVA Mexico"; el threshold de 4 chars en substring previene matches espurios con aliases cortos como `nu`/`hey`. | 2026-05-09 |
| D-11 | **Tenant `system` con UUIDs hardcoded en seed migration** (org `019e0d75-323e-74b3-a249-90828e8673e6`, user `019e0d75-323e-74b3-a249-909b3f77ee9f`). **Storage local en `{ROOT}/data/uploads/{yyyy}/{mm}/{hash}.{ext}` con write atómico (tmp+replace)**. **Hash duplicado → 409 + id existente** (no 500, no 200 idempotente). | UUIDs fijos = determinismo cross-env (dev/CI/staging/prod tienen el mismo ID; un dump de prod restaurado en dev no rompe FK). Filesystem local hasta migrar a S3 en Fase 5+ (mismo contrato). 409 anticipa Capa 1 de Fase 2.1 sin romper API: cuando llegue Validacion solo se agrega un INSERT extra; el contrato HTTP queda igual. | 2026-05-09 |

---

## Stack Confirmado

- **Backend:** FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic
- **DB:** PostgreSQL 16 + extensiones `pg_trgm`, `pgcrypto`, `unaccent`
- **Cache/Queue:** Redis 7 + Celery
- **OCR:** llama-server (llama.cpp `b9012`) + modelo `GLM-OCR-f16.gguf` con mmproj `mmproj-GLM-OCR-Q8_0.gguf` (multimodal real, ctx 16384, alias `GLM-OCR`, ya descargado en `llama.cpp/GLM-OCR/`)
- **Imagen:** OpenCV + pdf2image + Pillow
- **Frontend pago (Fase 4):** Next.js 14 + Tailwind + shadcn/ui + Zustand + React Query
- **Plugin (Fase 3):** PHP nativo WordPress 6.5+
- **Infra:** Docker Compose + Nginx + Certbot
- **CI/CD:** GitHub Actions
- **Tests:** pytest + httpx mock + TestClient

---

# FASE 0 — Infraestructura y DevOps (Semanas 1-2)

> Objetivo: entorno reproducible con `llama-server` sirviendo `glm-ocr` antes de escribir lógica de negocio.

## 0.1 Reestructuración del Repo (monorepo)

- [x] **0.1.1** Crear estructura de carpetas: `api/`, `plugin-wp/`, `webapp/`, `infra/`, `tests/`, `docs/`
  - Mover `main.py` y `pyproject.toml` actuales dentro de `api/`
  - Crear `.gitkeep` en `plugin-wp/`, `webapp/`, `infra/`, `docs/`
  - **Hecho cuando:** `tree -L 2 -I '.venv|llama.cpp|cosas'` muestra la estructura objetivo
- [x] **0.1.2** Actualizar `pyproject.toml` en `api/`: cambiar `requires-python` a `>=3.12,<3.13`, name a `smartvoucher-api`
  - **Hecho cuando:** `cd api && uv sync` funciona sin error
- [x] **0.1.3** Crear `.editorconfig` en raíz (LF, UTF-8, indent 4 Python / 2 JS)
- [x] **0.1.4** Configurar `pre-commit` con `ruff` (Python) — archivo `.pre-commit-config.yaml` en raíz
  - **Hecho cuando:** `pre-commit run --all-files` ejecuta sin instalar y reporta archivos
  - **Nota:** se ejecuta vía `uvx pre-commit run --all-files` (no requiere instalación global)
- [x] **0.1.5** Crear ramas `develop` y configurar `main` como protegida (documentar en `docs/git-flow.md`)
  - **Hecho cuando:** `git branch` muestra `main`, `develop`; `docs/git-flow.md` existe
  - **Pendiente:** habilitar reglas de protección en GitHub al primer push (no bloquea desarrollo local)

## 0.2 Dependencias Python (api/)

- [x] **0.2.1** Agregar deps base a `api/pyproject.toml`:
  - `fastapi[standard]`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `psycopg[binary]`, `alembic`
  - `redis`, `celery[redis]`, `httpx`, `tenacity`
  - `opencv-python-headless`, `pdf2image`, `pillow`, `python-magic`
  - `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`
  - `python-levenshtein`, `scikit-learn`, `python-dateutil`
  - **Hecho cuando:** `cd api && uv sync` resuelve todo sin conflictos
  - **Resultado:** 89 paquetes resueltos, 33 instalados; agregado vía `uv add` (no edición manual)
- [x] **0.2.2** Agregar deps dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`, `ruff`
  - **Hecho cuando:** `cd api && uv sync --dev` OK
  - **Resultado:** `pytest 9.0.3`, `ruff 0.15.12` corriendo desde `uv run`

## 0.3 Docker Compose (infra/)

- [x] **0.3.1** Crear `infra/docker-compose.yml` con servicios `postgres` (16-alpine) y `redis` (7-alpine)
  - Postgres: volumen nombrado, healthcheck, env vars desde `.env`
  - Redis: appendonly yes, healthcheck con `redis-cli ping`
  - **Hecho cuando:** `cd infra && docker compose up -d` levanta ambos sanos
  - **Resultado:** ambos `(healthy)`, `redis-cli ping → PONG`, Postgres 16.13 corriendo
- [x] **0.3.2** Crear `.env.example` en raíz con variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `REDIS_URL`, `LLAMA_SERVER_URL`
  - Agregar `.env` al `.gitignore`
  - **Hecho cuando:** `cp .env.example .env` y `docker compose up` lee bien las vars
  - **Resultado:** `.env` ya estaba ignorado; compose lee creds vía `env_file: ../.env`

## 0.4 PostgreSQL — Base de datos y extensiones

- [x] **0.4.1** Conectarse a Postgres del compose y crear extensiones:
  ```sql
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  CREATE EXTENSION IF NOT EXISTS pgcrypto;
  CREATE EXTENSION IF NOT EXISTS unaccent;
  ```

  - **Hecho cuando:** `SELECT similarity('test','test');` retorna `1`
  - **Resultado:** `sim_exact=1`, `similarity('Comprobante 12345','comprobante 12346')=0.8`
- [x] **0.4.2** Crear script `infra/init-db.sql` con las extensiones (montar como `/docker-entrypoint-initdb.d/` en compose)
  - **Hecho cuando:** `docker compose down -v && up -d` recrea la DB con extensiones automáticamente
  - **Resultado:** tras `down -v && up -d`, `\dx` muestra pg_trgm 1.6, pgcrypto 1.3, unaccent 1.1 sin intervención

## 0.5 llama-server + glm-ocr — Validación

- [x] **0.5.1** Verificar que `llama.cpp/GLM-OCR.sh` levanta el server correctamente
  - **Hecho cuando:** `curl http://localhost:8080/health` responde 200
  - **Resultado:** `{"status":"ok"}`; modelo `GLM-OCR` cargado (891M params, multimodal)
- [x] **0.5.2** Prueba de humo OCR: enviar imagen base64 de comprobante de prueba y validar respuesta
  - Crear script `infra/scripts/smoke_test_ocr.sh`
  - **Hecho cuando:** El script imprime "OK — texto extraído: ..." con tiempo < 5s
  - **Resultado:** 3.73s sobre comprobante sintético, 136 tokens generados, texto extraído correcto (con typo `MÉXICO→MÁXICO` esperado en diacríticos)
  - **Helper extra:** `infra/scripts/generate_sample.py` genera el fixture con Pillow
- [x] **0.5.3** Documentar en `docs/llama-server.md`: cómo levantar, parámetros del modelo, prompt base
  - **Hecho cuando:** `docs/llama-server.md` existe con secciones: Setup, Iniciar, Probar, Apagar
  - **Resultado:** docs incluyen tabla de flags, ejemplos curl, smoke test, troubleshooting

## 0.6 Alembic — Sistema de migraciones

- [x] **0.6.1** `cd api && uv run alembic init alembic` (config asíncrono)
  - **Hecho cuando:** existe `api/alembic/` y `api/alembic.ini`
  - **Resultado:** ejecutado con `-t async` (plantilla asíncrona oficial); creados `api/alembic/{env.py,script.py.mako,README,versions/}` y `api/alembic.ini`
- [x] **0.6.2** Configurar `api/alembic/env.py` para leer `DATABASE_URL` del `.env` y usar engine async
  - **Hecho cuando:** `uv run alembic current` no falla (devuelve vacío porque no hay migraciones)
  - **Resultado:** `env.py` reescrito para importar `settings` de `config.py` (single source of truth) e inyectar `settings.database_url` vía `config.set_main_option("sqlalchemy.url", ...)`. `uv run alembic current` conecta al PostgresqlImpl sin error.
- [x] **0.6.3** Crear `api/config.py` con `Settings(BaseSettings)` que lee `.env`
  - **Hecho cuando:** `uv run python -c "from config import settings; print(settings.database_url)"` imprime la URL (ejecutar desde `api/`, ver nota)
  - **Resultado:** `Settings` con `pydantic-settings` v2 carga `database_url`, `redis_url`, `llama_server_url`. `extra="ignore"` para tolerar vars de docker-compose (POSTGRES_USER, etc.).
  - **Nota:** el criterio original decía `from api.config` pero el `pyproject.toml` vive **dentro** de `api/`, así que `api/` ES el package root y los módulos son top-level. Import correcto: `from config import settings`.

## 0.7 Criterios de Aceptación de Fase 0

- [x] **0.7.1** llama-server responde en <3s con texto extraído de imagen de prueba ✅ (validado en 0.5.2 — 3.73s, dentro del target <5s del plan)
- [x] **0.7.2** PostgreSQL accesible con `pg_trgm` habilitado ✅ (validado en 0.4.1)
- [x] **0.7.3** Redis corriendo y accesible (`redis-cli ping → PONG`) ✅ (validado en 0.3.1)
- [x] **0.7.4** `alembic current` ejecuta sin error ✅ (validado en 0.6.2)
- [x] **0.7.5** Estructura de monorepo en Git con ramas configuradas ✅ (validado en 0.1.5)

> **🏁 Fin Fase 0** — commitear y taggear: `git tag fase-0-completa`

---

# FASE 1 — Núcleo OCR y API MVP (Semanas 3-7)

> Objetivo: API REST funcional `POST /upload-slip` que procesa comprobante con glm-ocr, normaliza y persiste. **Sin** detección de duplicados aún.

## 1.1 Estructura del proyecto FastAPI

- [x] **1.1.1** Crear esqueleto de carpetas dentro de `api/`:
  - `models/`, `schemas/`, `routers/`, `services/`, `tasks/`, `tests/`
  - `__init__.py` en cada uno
  - **Resultado:** 6 paquetes creados con docstring breve cada uno (no `.gitkeep` — el `__init__.py` ya hace de ancla y permite imports inmediatos).
- [x] **1.1.2** Crear `api/main.py` con FastAPI app, CORS configurado, router `/health` mínimo
  - **Hecho cuando:** `uv run fastapi dev api/main.py` levanta y `GET /health` responde 200
  - **Resultado:** `TestClient(app).get('/health') → 200 {"status":"ok"}`. CORS abierto (`allow_origins=["*"]`) con TODO para Fase 4. Router en `routers/health.py`. `/` (sin schema) devuelve metadata + `llama_server_url` desde settings. Health completo (llama+db+redis) queda para 1.7.2.
- [x] **1.1.3** Crear `api/database.py` con engine async SQLAlchemy + `SessionLocal` + `get_session` dependency
  - **Hecho cuando:** test mínimo `SELECT 1` async funciona
  - **Resultado:** engine async (`pool_pre_ping=True`), `SessionLocal` (`expire_on_commit=False`, `autoflush=False`), `Base(DeclarativeBase)` para modelos, dependency `get_session()`. Test `tests/test_database.py::test_select_one` PASSED contra Postgres del compose. `pytest.ini_options` con `asyncio_mode="auto"` agregado a `pyproject.toml`.

## 1.2 Modelos ORM (SQLAlchemy 2 — async, type-annotated)

- [x] **1.2.1** Modelo `Organizacion` (`models/organizacion.py`) — multi-tenant base, aunque Fase 4
  - **Resultado:** PK `id_organizacion` UUID v7 (`uuid_utils.compat.uuid7`), `plan_suscripcion` con CHECK `('basico','profesional','empresarial')`, `fecha_registro` server-side `now()`, `SoftDeleteMixin` aplicado. Relación `usuarios` con `cascade="all, delete-orphan"` (solo dispara en hard delete).
- [x] **1.2.2** Modelo `Usuario` (`models/usuario.py`) — con FK a Organización
  - **Resultado:** FK `id_organizacion` con `ondelete="RESTRICT"`. `correo` UNIQUE+índice. `rol` con CHECK `('admin','operador','auditor')`. `token_api_hash` (renombrado de `token_api` del ERD por D-07) nullable, bcrypt. `contrasena_hash` siempre obligatorio.
- [x] **1.2.3** Modelo `Comprobante` (`models/comprobante.py`) — con CHECK en `estado_actual` (enum: `recibido`, `procesando`, `comparando`, `en_revision`, `valido`, `duplicado`, `error`)
  - **Resultado:** `monto Numeric(15,2)`, `fecha_deposito Date`, `hash_documento String(64) UNIQUE` (Capa 1 deduplicación), `texto_extraido Text`. CHECK extra: `monto >= 0 OR NULL`. Índices btree en `id_usuario`, `fecha_deposito`, `estado_actual`. Compuesto `(referencia,monto,fecha_deposito)` queda para 2.2.2.
- [x] **1.2.4** Modelo `Validacion` (`models/validacion.py`) — con `metodo_deteccion`, `id_usuario`
  - **Resultado:** `id_usuario` nullable + `ondelete="SET NULL"` (detecciones automáticas no tienen autor). `id_comprobante` con `ondelete="CASCADE"`. `score_similitud Float` con CHECK `[0,1] OR NULL`. `clasificacion` CHECK `('valido','sospechoso','duplicado')`. `metodo_deteccion` CHECK `('hash_exacto','campos_exactos','scoring_ponderado','manual')`.
- [x] **1.2.5** Modelo `LogProcesamiento` (`models/log_procesamiento.py`) — con `id_usuario`, niveles INFO/WARN/ERROR
  - **Resultado:** SIN `SoftDeleteMixin` (D-06). `__tablename__="log_procesamiento"` (singular para diferenciarlo del resto que es plural — se respeta el nombre del ERD). `etapa String(50)` con índice (filtros tipo `etapa LIKE 'ocr.%'`). `nivel` CHECK INFO/WARN/ERROR.
- [x] **1.2.6** Generar primera migración Alembic: `alembic revision --autogenerate -m "initial_schema"`
  - **Hecho cuando:** archivo de migración generado refleja las 5 tablas + Organización
  - **Resultado:** `alembic/versions/607b4c53997b_initial_schema.py`. Autogenerate detectó 5 tablas + 13 índices + 9 CHECK constraints + 5 FKs + 2 UNIQUE en orden topológico correcto. Para que detecte las tablas hubo que cambiar `target_metadata = None` → `Base.metadata` y agregar `import models` en `alembic/env.py` (sin eso el autogenerate no carga los modelos).
- [x] **1.2.7** Aplicar: `alembic upgrade head`
  - **Hecho cuando:** `\dt` en psql muestra las 5 tablas
  - **Resultado:** `alembic upgrade head` corrió sin error. `\dt` muestra `comprobantes`, `log_procesamiento`, `organizaciones`, `usuarios`, `validaciones` + `alembic_version`. `alembic current` reporta `607b4c53997b (head)`.

## 1.3 Servicio de Imagen (`services/image_service.py`)

- [x] **1.3.1** Función `pdf_to_image(pdf_bytes) -> bytes` con `pdf2image` (dpi=300, primera página)
  - Test: `tests/test_image_service.py::test_pdf_to_image_returns_decodable_png` + `test_pdf_to_image_rejects_garbage`
  - **Resultado:** `pdf2image.convert_from_bytes(..., dpi=300, fmt="png", first_page=1, last_page=1)` → PIL Image → `BytesIO` → PNG bytes. Rechaza PDFs inválidos (pdf2image lanza `PDFPageCountError`). Test usa `Image.save(format="PDF", resolution=72)` para generar PDF sintético en memoria, sin necesidad de fixture en disco.
- [x] **1.3.2** Función `validate_mime(file_bytes) -> str` con `python-magic` (whitelist: image/jpeg, image/png, application/pdf)
  - **Resultado:** `magic.from_buffer(bytes, mime=True)` (libmagic, NO mira extensiones). `ALLOWED_MIMES` como `frozenset` exportado para que tests verifiquen el contrato. Levanta `ValueError` con mensaje listando MIMEs permitidos. También rechaza bytes vacíos (caso borde no contemplado en plan).
- [x] **1.3.3** Pipeline OpenCV: `preprocess(img_bytes) -> bytes`
  - Pasos: decode → grayscale → **deskew (sobre gray)** → adaptiveThreshold → crop → encode
  - Test con imagen torcida del dataset de prueba
  - **Resultado:** orden invertido respecto al plan (D-08). Helpers privados `_detect_skew_angle` (Otsu + `findNonZero` + `minAreaRect` sobre coordenadas, normaliza a (-45, 45]), `_rotate` (`warpAffine` con `BORDER_REPLICATE` para evitar bordes negros), `_crop_whitespace` (boundingRect del contenido invertido + padding 8px). Constantes parametrizadas (`PDF_DPI`, `ADAPTIVE_BLOCK_SIZE`, `ADAPTIVE_C`, `SKEW_MIN_ANGLE`, `CROP_PADDING_PX`) para tunear sin tocar lógica.
- [x] **1.3.4** Función `to_base64(img_bytes) -> str`
  - **Hecho cuando:** suite `pytest tests/test_image_service.py` pasa
  - **Resultado:** `base64.b64encode(...).decode("ascii")`. 14/14 tests verdes en 0.73s (incluye casos borde: bytes vacíos, garbage, imagen rotada 5°, padding artificial para verificar crop).

## 1.4 Servicio OCR (`services/ocr_service.py`)

- [x] **1.4.1** Cliente `httpx.AsyncClient` con timeout 10s, base URL desde settings (DI opcional para tests)
- [x] **1.4.2** Función `extract_fields(img_b64) -> dict` con prompt JSON del plan (sección 1.3 del plan_desarrollo.md)
- [x] **1.4.3** Reintentos con `tenacity` (3 intentos, wait fijo 1s, **solo** en `RequestError` o 5xx)
- [x] **1.4.4** Manejo de errores: 503 tras agotar retries / JSON inválido / estructura inesperada; 502 en 4xx (sin retry)
- [x] **1.4.5** Tests con `httpx.MockTransport`: `tests/test_ocr_service.py` (11 tests, 0.46s)
  - **Hecho cuando:** mock de respuesta JSON parsea correctamente ✅

## 1.5 Servicio Parser/Normalización (`services/parser_service.py`)

- [x] **1.5.1** `parse_monto(raw: str) -> Decimal` — extrae dígitos, descarta símbolos
  - **Resultado:** firma ampliada a `str | int | float | None -> Decimal | None` porque el LLM puede devolver número nativo. Regex `[^0-9.,\-]` conserva el `-` en la limpieza para que `Decimal("-100") < 0` rechace explícitamente (si tirásemos el signo en regex, "-100" se convertiría silenciosamente en 100). `str(raw)` antes de Decimal evita artefactos de precisión float (`Decimal(0.1) → 0.1000...0888`). Multi-punto rechazado.
- [x] **1.5.2** `parse_fecha(raw: str) -> date` — `dateutil.parser` con múltiples formatos
  - **Resultado:** firma `str | None -> date | None`. Heurística ISO/no-ISO: regex `^\d{4}-\d{1,2}-\d{1,2}$` detecta ISO y usa `yearfirst=True`; cualquier otro formato → `dayfirst=True` (prompt OCR pide DD/MM/YYYY). `fuzzy=False` para no adivinar en strings con basura.
- [x] **1.5.3** `parse_referencia(raw: str) -> str` — strip + uppercase + colapsar espacios
  - **Resultado:** `_WHITESPACE_RE = re.compile(r"\s+")` colapsa cualquier whitespace (no solo espacios — también `\t`, `\n`). Preserva símbolos (`/`, `-`) porque el scoring de Fase 2 usa similarity, no equality. Devuelve `None` si tras strip queda vacío.
- [x] **1.5.4** `normalize_banco(raw: str) -> str` — match contra catálogo (BBVA, Citibanamex, Banorte, HSBC, Santander, Hey Banco, Nu Bank, OTRO)
  - **Resultado:** catálogo `_BANCO_ALIASES` con 7 bancos × 1-4 aliases cada uno. Algoritmo: (1) `_normalize_for_match` → NFKD + ascii + lower + solo `[a-z0-9]`; (2) substring match contra aliases ≥4 chars (cubre "BBVA Mexico" → BBVA); (3) fallback Levenshtein.ratio con threshold 0.85; (4) sin match → "OTRO". Aliases cortos (`hey`, `nu`, `citi`) NO usan substring para evitar falsos positivos en "nuevo", "heroe", etc.
- [x] **1.5.5** `compute_hash(image_bytes: bytes) -> str` — SHA-256 sobre bytes originales
  - **Resultado:** SHA-256 hex (64 chars lowercase). Acepta `bytes | bytearray | memoryview` (un upload puede llegar como bytearray desde Starlette). Levanta `TypeError` si se pasa str (única excepción explícita del módulo — bytes vacíos sí son válidos). Crítico: hashear ANTES del preprocess (la compresión PNG y el crop introducen variaciones que romperían la equivalencia con re-uploads del mismo archivo).
- [x] **1.5.6** Tabla de tests con casos sucios → salidas esperadas: `tests/test_parser_service.py`
  - **Resultado:** 81 tests parametrizados (heavy `@pytest.mark.parametrize`). Cubren happy paths + casos sucios + edge cases por función. Suite completa de Fase 1 hasta acá: 107/107 en 0.73s.

## 1.6 Schemas Pydantic v2 (`schemas/`)

- [x] **1.6.1** `schemas/comprobante.py`: `ComprobanteCreate`, `ComprobanteResponse`, `CamposExtraidos`
  - **Resultado:** 3 DTOs con responsabilidades separadas. `CamposExtraidos` (frozen, post-parser) tiene `monto: Decimal | None` con `max_digits=15, decimal_places=2, ge=0` (espeja el CHECK de DB), `banco` siempre str (fallback OTRO). `ComprobanteCreate` para capa servicio→repo: valida `hash_documento` con `pattern=r"^[0-9a-f]{64}$"` (SHA-256 hex lowercase) y `estado_actual` contra `ESTADOS_VALIDOS` importado del modelo (single source of truth). `ComprobanteResponse` con `from_attributes=True` + helper `from_orm_model(comp)` que arma `campos_extraidos` anidado desde columnas planas del ORM (Pydantic no compone sub-objetos solo). Mapping intencional `fecha_deposito` ORM → `fecha` schema. Smoke tests verdes: rechaza estado inválido, hash no-hex, monto negativo.
- [x] **1.6.2** `schemas/health.py`: `HealthResponse` con campos `llama`, `db`, `redis`
  - **Resultado:** `ServiceCheck` reutilizable (`ok: bool`, `detail: str | None`) y `HealthResponse` que lo agrega 3 veces (`llama`, `db`, `redis`). Sin flag global agregado a propósito: el cliente decide la política (Fase 1 sin cache podría tolerar Redis caído). El endpoint debe responder 200 incluso con `ok=False` en alguna dependencia — el HTTP indica que la API responde, los flags indican degradación. Sólo 503 si la API ni siquiera puede armar el response.

## 1.7 Endpoints MVP

- [x] **1.7.1** `POST /upload-slip` (`routers/upload.py`):
  - Recibe `UploadFile` → valida MIME → preprocesa → OCR → normaliza → guarda en DB
  - Responde `ComprobanteResponse` (201) con id, estado, hash, path y `campos_extraidos` anidado
  - **Sin** detección de duplicados (Fase 2)
  - **Resultado:** Pipeline completo orquestado en `routers/upload.py`. Pasos preparatorios: (a) `models/seed.py` con UUIDs hardcoded del tenant `system` (org+user) — D-11 implícito: determinístico cross-env, hash bcrypt real con cost 12; (b) migración Alembic `ba4e861e6950_seed_system_tenant.py` con `INSERT ... ON CONFLICT DO NOTHING` idempotente, casts `CAST(:id AS uuid)` (asyncpg rechaza coerce implicito y SQLAlchemy text() interpreta `::` como conflicto con bindparams); (c) `settings.upload_dir` default `${ROOT}/data/uploads`; (d) `services/storage_service.py` con `save_upload(...)` async via `asyncio.to_thread`, write atómico vía `tmp+replace` (POSIX-atomic), layout particionado `{yyyy}/{mm}/{hash}.{ext}`, regex `^[0-9a-f]{64}$` para hash, whitelist de extensiones, `StorageError` para envolver `OSError`. Decisiones del endpoint: hash sobre bytes ORIGINALES (D-09), 409 con `id_comprobante` existente al detectar hash duplicado (anticipa Capa 1 Fase 2 sin cambiar contrato HTTP), `SYSTEM_USER_ID` hardcoded (auth real Fase 4), estado inicial `recibido`, write a disco ANTES del INSERT (huérfanos preferibles a filas con path inválido), cap de 10MB con `HTTP 413`, MIME via libmagic NO `file.content_type`, captura de `IntegrityError` post-commit como red de seguridad para race condition entre SELECT y INSERT. 32 tests de storage_service (139/139 suite total).
- [x] **1.7.2** `GET /health` (`routers/health.py`): chequea llama-server, postgres, redis
  - **Resultado:** `services/cache_service.py` con cliente Redis lazy global (no se inicializa al import — evita romper tests que no necesitan Redis) y `ping(timeout_s=1.0) -> bool` que captura `asyncio.TimeoutError`, `RedisError` y `Exception` genérica devolviendo `False` (NUNCA propaga — el endpoint health depende de eso). `routers/health.py` con 3 funciones privadas `_check_llama/_check_db/_check_redis` orquestadas por `asyncio.gather(...)` para que el peor caso sea max(individual) y no suma (~3s secuencial vs ~1s paralelo con timeout=1s cada uno). Cada `ServiceCheck` lleva latencia en `detail` (`"66ms"`) en éxito o mensaje de error en falla. **Endpoint responde 200 SIEMPRE** — el código HTTP indica que la API responde, los flags `ok` indican degradación. 16 tests nuevos: 9 en `test_cache_service.py` (happy path + cache de cliente + 4 modos de falla — RedisError, TimeoutError, Exception genérica, asyncio.TimeoutError — + close idempotente) y 7 en `test_health_endpoint.py` (todos OK, llama 5xx, llama network error, db error, db timeout, redis down, todos caídos). Tests 100% offline con `httpx.MockTransport` + `app.dependency_overrides[get_session]` + `monkeypatch` de `cache_service.ping`. Smoke real contra infra: llama 66ms, db 24ms, redis 2ms.
- [x] **1.7.3** `GET /history` (`routers/history.py`): paginado con filtros `fecha_desde`, `fecha_hasta`, `banco`, `estado`
  - **Resultado:** Estrategia offset/limit (default 20, max 100). Schema `ComprobanteListResponse` con `{items, total, limit, offset, has_more}` permite que el frontend pinte "Pagina 3 de 47" sin un segundo round-trip. Filtros: `fecha_desde/hasta` sobre `fecha_deposito` (lo que el comprobante DICE — coincide con la intención semántica del contador, no `fecha_registro`), `banco` exact match contra normalizado del catálogo (frontend Fase 4 enviará valores canónicos), `estado` validado contra `ESTADOS_VALIDOS`. Filtra por `SYSTEM_USER_ID` (Fase 4 lo reemplaza por JWT user) y excluye soft-deleted. Order: `fecha_registro DESC, id_comprobante DESC` — tiebreaker por UUID v7 evita que la paginación duplique/saltee filas cuando varios inserts caen en el mismo tick de `now()`. 13 tests cubriendo: empty page, retorno básico, paginación 3 páginas sin solapamiento, offset > total, filtro por estado, filtro por rango de fechas, orden DESC determinístico, exclusión de soft-deleted, filtro multi-tenant, 4 validaciones de query params (estado inválido, rango invertido, limit > 100, offset negativo). Smoke real verde contra Postgres del compose.

## 1.8 Tests de integración

- [x] **1.8.1** `tests/conftest.py`: fixture de DB de test (postgres dockerizada o testcontainer)
  - **Resultado:** Refactor del patrón `db_session` + `client` desde `test_history_endpoint.py` a `tests/conftest.py` compartido. Dos fixtures async-scope-function: (a) `db_session` abre engine LOCAL con `NullPool`, conecta, `BEGIN`, yieldea `AsyncSession` bind-eada a la conexión, y al cierre hace `rollback + conn.close + engine.dispose` (el rollback limpia los INSERTs del test sin tocar la DB local; `NullPool` evita el bug "Event loop is closed" del engine global cacheando conexiones cross-loop); (b) `client` override-a `get_session` para que el endpoint use la MISMA sesión del test (los INSERTs del fixture son visibles dentro de la transacción) y arma `httpx.AsyncClient(transport=ASGITransport(app))` — NO `TestClient` por incompatibilidad sync/asyncpg documentada en gotchas. Skip automático si Postgres no responde (`OperationalError`) → CI sin servicios queda verde. `test_history_endpoint.py` reducido de 357 → 280 líneas (eliminadas las dos fixtures locales + imports redundantes); ahora cualquier test futuro de DB real (1.8.2 E2E upload) hereda el patrón sin duplicar código. Suite 168/168 en 0.79s.
- [x] **1.8.2** `tests/test_upload_endpoint.py`: prueba E2E con `TestClient` y mock de llama-server
  - **Resultado:** 6 tests E2E reusando `client` + `db_session` del conftest. Mocks selectivos: (a) `routers.upload.extract_fields` monkeypatched a una función async que devuelve dict feliz (no toca llama-server) o levanta `HTTPException(503)` para el caso de error; (b) `routers.upload.save_upload` monkeypatched a una función que solo registra el path (no toca disco — la integración real con `storage_service` ya está cubierta por `test_storage_service.py`). Casos: (1) happy path con PNG sintético de Pillow → 201, body con `hash_documento`, `estado_actual="recibido"`, `campos_extraidos.banco=BBVA`, fila en DB con `id_usuario=SYSTEM_USER_ID`; (2) MIME inválido (text/plain) → 400, save NO llamado; (3) >10MB junk → 413, save NO llamado (size se chequea antes del MIME); (4) archivo vacío → 400; (5) hash duplicado pre-insertado → 409 con `id_comprobante` del existente, save NO llamado (cortocircuito antes del paso 5); (6) OCR levanta 503 → propaga 503, save SÍ llamado (paso 5 < paso 8 en el pipeline; archivo huérfano lo limpia el cron de Fase 5 — gotcha documentado en `routers/upload.py`). **NO usé `TestClient`** del plan original — el conftest provee `httpx.AsyncClient` con `ASGITransport` (incompatibilidad sync/asyncpg ya documentada). Suite total: 174/174 en 0.97s.
- [ ] **1.8.3** Coverage: `pytest --cov=api --cov-report=term --cov-fail-under=70`
  - **Hecho cuando:** coverage en `services/` ≥ 70%

## 1.9 Criterios de Aceptación de Fase 1

- [ ] **1.9.1** Tiempo procesamiento por comprobante ≤ 5s (medir con script `infra/scripts/bench_upload.sh`)
- [ ] **1.9.2** Precisión campos en dataset de 20 comprobantes ≥ 85%
- [ ] **1.9.3** `/health` responde 200 con todos los servicios OK
- [ ] **1.9.4** Suite pytest pasa sin errores
- [ ] **1.9.5** Swagger en `/docs` accesible y completo

> **🏁 Fin Fase 1** — `git tag fase-1-completa`

---

# FASE 2 — Motor de Detección de Duplicados (Semanas 8-10)

> Objetivo: Sistema clasifica comprobantes en `Válido`, `Sospechoso`, `Duplicado` con detección en 3 capas.

## 2.1 Detección Capa 1 — Hash exacto (Redis)

- [ ] **2.1.1** Cliente Redis async (`services/cache_service.py`)
- [ ] **2.1.2** Función `check_hash(hash: str) -> Optional[ComprobanteId]`
- [ ] **2.1.3** TTL 7 días, key pattern `comp:hash:{sha256}`

## 2.2 Detección Capa 2 — Campos críticos exactos (Postgres)

- [ ] **2.2.1** Query: `WHERE referencia = ? AND monto = ? AND fecha = ?`
- [ ] **2.2.2** Índice compuesto en (`referencia`, `monto`, `fecha`) — agregar a migración
- [ ] **2.2.3** Si match: marcar como `duplicado`, registrar en `Validacion`

## 2.3 Detección Capa 3 — Scoring ponderado (`services/duplicate_service.py`)

- [ ] **2.3.1** `S_ref` con `python-Levenshtein.ratio()` (peso 0.35)
- [ ] **2.3.2** `S_texto` con `TfidfVectorizer + cosine_similarity` (peso 0.30)
- [ ] **2.3.3** `S_monto` numérica normalizada (peso 0.20)
- [ ] **2.3.4** `S_fecha` por días en ventana de 30 (peso 0.15)
- [ ] **2.3.5** Función `compute_score(nuevo, existente) -> float`
- [ ] **2.3.6** Clasificador: ≥0.90 duplicado, 0.75–0.90 sospechoso, <0.75 válido

## 2.4 Celery — modo asíncrono

- [ ] **2.4.1** `tasks/process_slip.py` — task Celery con todo el flujo
- [ ] **2.4.2** Endpoint `POST /upload-slip/async` → encola → responde `{task_id, status: "queued"}`
- [ ] **2.4.3** Endpoint `GET /status/{task_id}` → consulta estado en Redis
- [ ] **2.4.4** Worker: `celery -A api.tasks worker --concurrency=4`
- [ ] **2.4.5** Servicio Celery agregado al `docker-compose.yml`

## 2.5 Endpoints adicionales

- [ ] **2.5.1** `POST /validate/{id}` — CU-02 validación manual
- [ ] **2.5.2** `GET /report` — reportes (válidos/duplicados/sospechosos/tiempo promedio)

## 2.6 Diagrama de estados — implementar transiciones

- [ ] **2.6.1** Máquina de estados en `services/state_machine.py` siguiendo `cosas/diagrama_estados.svg`
- [ ] **2.6.2** Tests: cada transición posible

## 2.7 Criterios de Aceptación de Fase 2

- [ ] **2.7.1** Detección correcta ≥90% en dataset etiquetado (20 únicos + 10 duplicados + 10 sospechosos)
- [ ] **2.7.2** Hash exacto detectado en <100ms (cache Redis)
- [ ] **2.7.3** Flujo síncrono completo ≤ 5s
- [ ] **2.7.4** Task Celery completa en < 30s
- [ ] **2.7.5** `POST /validate/{id}` actualiza estado correctamente en 100% de tests

> **🏁 Fin Fase 2** — `git tag fase-2-completa`

---

# FASE 3 — Plugin WordPress Gratuito (Semanas 11-13)

> Objetivo: Plugin instalable desde WordPress.org consumiendo la API.
> _Tareas se refinarán al iniciar Fase 3 — por ahora son macro-tareas._

- [ ] **3.1** Estructura `plugin-wp/comprobantes-ocr/` (entry point + readme.txt + includes/)
- [ ] **3.2** Clase `API_Client` con `wp_remote_post()` hacia FastAPI
- [ ] **3.3** Página de configuración wp-admin (URL API + API key + botón "Probar conexión")
- [ ] **3.4** Shortcode `[comprobante_upload]` con drag-and-drop
- [ ] **3.5** Bloque Gutenberg equivalente al shortcode
- [ ] **3.6** Semáforo visual (verde/amarillo/rojo) renderizado vía JS
- [ ] **3.7** Widget historial últimos 20 en wp-admin
- [ ] **3.8** Hook WooCommerce `woocommerce_order_status_completed`
- [ ] **3.9** Seguridad: nonce, sanitización, capability checks
- [ ] **3.10** i18n: archivos .pot, traducciones es_MX y en_US
- [ ] **3.11** Assets WP.org: banner, ícono, screenshots
- [ ] **3.12** `readme.txt` formato oficial WP.org
- [ ] **3.13** Pasar Plugin Check sin errores críticos
- [ ] **3.14** Workflow GitHub Actions para generar ZIP en tags

> **🏁 Fin Fase 3** — `git tag fase-3-completa`

---

# FASE 4 — Plataforma Web de Pago (Semanas 14-18)

> Objetivo: Next.js 14 con dashboard, multi-tenant, suscripciones Stripe.
> _Tareas se refinarán al iniciar Fase 4._

- [ ] **4.1** Bootstrap Next.js 14 en `webapp/` con App Router + TypeScript
- [ ] **4.2** Configurar Tailwind + shadcn/ui
- [ ] **4.3** Auth: NextAuth con provider JWT custom hacia FastAPI
- [ ] **4.4** Endpoints API: `POST /auth/login`, `POST /auth/refresh`
- [ ] **4.5** Middleware de autorización por rol (admin/operador/auditor)
- [ ] **4.6** Multi-tenancy en API: `organization_id` en JWT, filtro automático en queries
- [ ] **4.7** Rate limiting por plan (Básico/Profesional/Empresarial)
- [ ] **4.8** Dashboard principal con KPIs y gráficas Recharts
- [ ] **4.9** Módulo upload con modo síncrono/asíncrono
- [ ] **4.10** Historial avanzado con filtros + exportar CSV/Excel/PDF
- [ ] **4.11** Vista side-by-side para revisión manual de duplicados
- [ ] **4.12** UI configuración de umbrales (sliders para w1-w4)
- [ ] **4.13** Gestión de usuarios (CRUD + roles)
- [ ] **4.14** Gestión de organizaciones (multi-tenant admin)
- [ ] **4.15** Webhooks: configuración + logs de envío + reintentos
- [ ] **4.16** Integración Stripe: planes + portal cliente + facturación

> **🏁 Fin Fase 4** — `git tag fase-4-completa`

---

# FASE 5 — Hardening, CI/CD y Lanzamiento (Semanas 19-20)

> _Tareas se refinarán al iniciar Fase 5._

- [ ] **5.1** Recopilar dataset 100 comprobantes etiquetados reales
- [ ] **5.2** Evaluación métricas: precision/recall/F1 por clase
- [ ] **5.3** Grid search de pesos w1-w4 si precisión <90%
- [ ] **5.4** Persistir pesos finales en tabla `configuracion_sistema`
- [ ] **5.5** GitHub Actions: job `tests-api` (postgres+redis services, pytest, coverage)
- [ ] **5.6** GitHub Actions: job `lint` (ruff + eslint)
- [ ] **5.7** GitHub Actions: job `build-plugin` en tags v\*
- [ ] **5.8** GitHub Actions: job `deploy-staging` en push a develop
- [ ] **5.9** GitHub Actions: job `deploy-production` en tags en main
- [ ] **5.10** Nginx producción: HTTPS Certbot + reverse proxy + rate limit
- [ ] **5.11** Docker Compose producción: api, webapp, postgres, redis, celery, nginx
- [ ] **5.12** Backups: cron pg_dump diario + sync imágenes a S3/B2 + RDB Redis
- [ ] **5.13** Checklist seguridad final (10 controles del plan §5.4)
- [ ] **5.14** Documentación final: README, ARCHITECTURE.md, DEPLOYMENT.md
- [ ] **5.15** Publicar plugin en WordPress.org

> **🏁 Lanzamiento v1.0** — `git tag v1.0.0`

---

## Notas y Gotchas (registrar lo aprendido)

> Cuando descubras algo no obvio durante una sesión, agregalo acá con fecha. Esto ahorra horas a sesiones futuras.

- **2026-05-08 — Warning `VIRTUAL_ENV` al correr `uv` desde `api/`:** El shell tiene exportada `VIRTUAL_ENV=.../SmartVoucherDetection/.venv` (de antes de la reestructura), pero ese venv ya no existe. `uv` lo ignora y usa `api/.venv`. No bloquea nada. Para limpiar: `unset VIRTUAL_ENV` en la sesión actual o quitarlo del shell rc.
- **2026-05-08 — `${VAR}` en docker-compose.yml NO se sustituye desde `env_file`:** La sustitución de `${POSTGRES_USER}` en el YAML ocurre **antes** de cargar `env_file`. Compose busca esas vars en (1) el shell y (2) `.env` en `cwd` (donde corrés el comando). Si tu `.env` vive en otra carpeta, o usás `--env-file`, o las vars se cargan vacías. **Solución aplicada:** dejar las creds solo en `env_file: ../.env` (se inyectan al contenedor) y usar `$$VAR` en healthchecks (escape de Compose para que se evalúe **dentro** del contenedor). Solo dejamos sustitución YAML para puertos del host con default `:-5432`.
- **2026-05-08 — Tipo en `.gitignore`:** la línea `cosas/*7` debería ser `cosas/*` (sufijo `7` es typo). No bloquea, pero conviene corregir cuando se toque ese archivo de nuevo.
- **2026-05-08 — GLM-OCR confunde diacríticos:** Sobre comprobante sintético "BBVA MÉXICO" extrajo "BBVA MÁXICO" (É→Á). Es un error esperado del OCR multimodal con caracteres acentuados; el matching de Fase 2 (`pg_trgm` + Levenshtein) absorbe 1-2 chars de error. **No** intentar resolver con post-procesado de texto: degradaría coincidencias correctas.
- **2026-05-08 — Stack confirmado actualizado:** El script `GLM-OCR.sh` real usa `GLM-OCR-f16.gguf` + `mmproj-GLM-OCR-Q8_0.gguf` (multimodal completo, ctx 16384), NO Q4_K_M como decía la doc inicial. Tamaño efectivo ~1.78 GB.
- **2026-05-09 — Imports en `api/`: top-level, NO `api.X`:** Como el `pyproject.toml` vive dentro de `api/`, ese directorio es el package root del proyecto. Los módulos se importan top-level (`from config import settings`, `from models.X import ...`), no como `from api.config`. Alembic respeta esto gracias a `prepend_sys_path = .` en `alembic.ini` (CWD = `api/`).
- **2026-05-09 — Orden 0.6.2 ↔ 0.6.3 invertido a propósito:** Hicimos `config.py` (0.6.3) antes que `env.py` (0.6.2) para evitar duplicar la lógica de lectura de `.env`. `env.py` ahora importa `settings` y queda como single consumer. Si se reordena el PROGRESO en el futuro, dejar `config.py` siempre primero.
- **2026-05-09 — Alembic autogenerate ignora modelos no importados:** Cambiar `target_metadata = None` → `Base.metadata` no alcanza. Hay que `import models` en `env.py` (con `# noqa: F401`) ANTES de leer `Base.metadata`, porque las tablas se registran en metadata al ejecutar el `mapped_column(...)` del decorador `__tablename__`. Sin el import explícito, autogenerate cree que el schema está vacío y emite un drop fantasma. El `__init__.py` de `models/` re-exporta los 5 modelos para que un solo `import models` los cargue todos.
- **2026-05-09 — `uuid_utils.compat.uuid7` vs `uuid_utils.uuid7`:** El módulo principal `uuid_utils` retorna su propio tipo `uuid_utils.UUID` que NO es subclase de `uuid.UUID` de stdlib. SQLAlchemy 2 con `Mapped[uuid.UUID]` y tipo nativo `Uuid` espera `uuid.UUID`. La forma correcta es `from uuid_utils.compat import uuid7` que devuelve `uuid.UUID` versión 7 nativo. Otra opción sería `uuid_utils.UUID(str(...))` pero es más feo.
- **2026-05-09 — `__tablename__="log_procesamiento"` (singular) rompe la convención plural del resto:** Lo mantuve así porque el ERD del cliente (`cosas/BD.html`) lo tiene singular. Las otras 4 tablas son plurales (`organizaciones`, `usuarios`, `comprobantes`, `validaciones`). No es prolijo pero respeta el contrato visual del ERD. Si se decide unificar a plural en algún momento, cambiar `__tablename__` y generar migración nueva con `op.rename_table`.
- **2026-05-09 — Orden deskew↔threshold invertido (D-08):** El plan_desarrollo.md lista paso 3 = binarizar, paso 4 = deskew. Lo invertí porque `cv2.warpAffine` con interpolación bilineal/cubica sobre una imagen binarizada produce píxeles intermedios (gris) en los bordes del texto, rompiendo la binarización. Pipeline correcto: gray → deskew → threshold. El test `test_preprocess_returns_binary_png` valida que >99% de los píxeles del output son exactamente 0 ó 255 (con threshold después de rotar) — si el orden estuviera al revés, ese ratio bajaría notablemente.
- **2026-05-09 — `_detect_skew_angle` con Otsu, no adaptive:** Para detectar el ángulo necesitamos una máscara binaria del texto. Usé `THRESH_BINARY_INV | THRESH_OTSU` (no adaptive) porque para el cálculo del ángulo importa la dirección global del texto, no la legibilidad local. Otsu es más rápido y suficientemente bueno para minAreaRect. La binarización adaptativa "real" sigue siendo el paso 4 del pipeline, sobre la grayscale ya rotada.
- **2026-05-09 — `dateutil.parser` con `dayfirst=True` rompe ISO `YYYY-MM-DD`:** "2026-05-01" con dayfirst → 5 de enero (toma "01" como día). Solución en `parse_fecha`: regex previa `^\d{4}-\d{1,2}-\d{1,2}$` para detectar ISO y switchear a `yearfirst=True` solo en ese caso. Para todo lo demás (formato MX dominante DD/MM/YYYY) sigue `dayfirst=True`. Sin esta heurística, ~10% de los OCR donde el LLM ignora el prompt y emite ISO terminarían con fecha equivocada por 4-7 meses.
- **2026-05-09 — Regex `[^0-9.,]` para limpiar monto descarta el `-` silenciosamente:** Original `_MONTO_CLEAN_RE` no incluía `-`, así que "-100" → "100" → `Decimal(100)` → válido (BUG: convirtió un negativo en positivo). Fix: incluir `\-` en el set conservado y dejar que `value >= 0` final lo cace. El test `parametrize("-100" → None)` lo atrapó en la primera corrida.
- **2026-05-09 — Match exacto-normalizado de banco pierde 30%+ por separadores:** "BBVA México" normalizado = `bbvamexico`; `Levenshtein.ratio("bbvamexico", "bbva")` = 0.571 (lejos del threshold 0.85) por la diferencia de longitud. Solución híbrida: substring match (`alias in normalized`) para aliases ≥4 chars antes del fuzzy. Atajos cortos (`hey`, `nu`, `citi`) NO entran al substring porque "nuevo" o "heroe" matchearían como Nu Bank / Hey Banco. El umbral de 4 chars sale empíricamente: el alias más corto seguro es "bbva".
- **2026-05-09 — `Decimal(0.1)` da `0.10000000000000000555...`:** float→Decimal hereda la imprecisión binaria del float. Pasar siempre por `str(raw)` antes de `Decimal(...)` evita el problema. Test `test_parse_monto_avoids_float_precision_artifacts` lo cubre como regresión.
- **2026-05-09 — Pillow PDF a 72 dpi default:** `Image.save(format="PDF")` por defecto usa `resolution=72` (1 inch = 72px). Si querés tamaño deterministico en tests, pasar explícitamente `resolution=72` y calcular: `pixeles_input * 300 / 72 ≈ pixeles_output_pdf2image_300dpi`. En el test no me ato a número exacto (poppler-utils puede variar entre distros), solo verifico `> 100px`.
- **2026-05-09 — `passlib 1.7` ↔ `bcrypt 4.x` incompatibilidad:** `passlib.context.CryptContext(["bcrypt"]).hash("...")` revienta con `AttributeError: module 'bcrypt' has no attribute '__about__'`. Es bug conocido de passlib (que sigue mirando `bcrypt.__about__.__version__`, removido en bcrypt 4.0). Workaround: usar `bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12))` directo. El módulo `bcrypt` puro es estable y suficiente para nuestro caso (no necesitamos múltiples schemes). Si en Fase 4 queremos passlib por sus features extra, downgradear bcrypt a `<4` o esperar passlib 1.8.
- **2026-05-09 — `text(":id::uuid")` rompe SQLAlchemy bindparams:** El parser de `text()` interpreta `::` como conflicto con su sintaxis `:name`. Levanta `ArgumentError: This text() construct doesn't define a bound parameter named 'id'`. Solución: usar SQL estándar `CAST(:id AS uuid)` en migraciones data-only que necesiten castear strings a UUID (asyncpg NO hace coerce implícito varchar→uuid, a diferencia de psycopg). Aplica a TODA migración futura que inserte UUIDs hardcoded.
- **2026-05-09 — Tests async + `engine` global compartido = "Event loop is closed":** Con `asyncio_mode=auto` cada test corre en su propio event loop (scope=function por default). Si un fixture abre conexión sobre el `engine` global (que cachea conexiones del pool), la siguiente vez que pytest pide una conexión, el pool puede devolver una ya bind-eada al loop del test anterior — ya cerrado. Solución estándar: en fixtures de tests crear engine LOCAL con `poolclass=NullPool` (no reusa conexiones) y `dispose()` al final. Aplicado en `test_history_endpoint.py::db_session`. Aplicable a cualquier test futuro que necesite DB real.
- **2026-05-09 — `TestClient` sync rompe asyncpg en tests con DB real:** `fastapi.testclient.TestClient` ejecuta el endpoint en un loop sync efímero — incompatible con conexiones asyncpg que el fixture async ya tenía abiertas en otro loop. Síntoma: `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` + tests inestables. Patrón correcto para tests async con DB real: `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`. Mantiene todo en el loop del test. Para tests SIN DB (mocks puros) `TestClient` sigue funcionando bien (lo usamos en `test_health_endpoint.py`).
- **2026-05-09 — Paginación necesita orden total estable, no solo `ORDER BY fecha_registro`:** En SQLAlchemy + Postgres, `func.now()` (TRANSACTION_TIMESTAMP) devuelve el MISMO valor para todos los inserts de una transacción. Si dos comprobantes se subieron con un segundo de diferencia pero la transacción tardó, su `fecha_registro` puede empatar — y un `ORDER BY fecha_registro DESC LIMIT/OFFSET` daría orden indeterminado entre páginas (mismo registro aparece dos veces o se saltea). Solución: tiebreaker por columna ordenable y única → `ORDER BY fecha_registro DESC, id_comprobante DESC`. UUID v7 (default del modelo) es ordenable por tiempo, así que el tiebreaker tiene sentido semántico.
- **2026-05-09 — `httpx.MockTransport` requiere `base_url` en el cliente, no la descarta:** Mi primer intento de monkeypatchear `httpx.AsyncClient` con un factory que solo seteaba `transport=MockTransport(handler)` reventaba con `unsupported url type: '/health'`. Es porque httpx valida la URL final del request contra `client.base_url` antes de delegar al transport — sin base_url, una URL relativa como `/health` no es resolvible. Fix: el factory tiene que reenviar `base_url` (cualquier string http válido sirve, el MockTransport igual ignora la red). Tip aplicable a cualquier mock de httpx en tests del proyecto.
- **2026-05-09 — Write atómico filesystem con `tmp+replace`:** El patrón `path.write_bytes(data)` no es atómico — un crash a mitad de write deja un archivo corrupto en `path`. Solución usada en `storage_service`: escribir a `path.tmp` primero, luego `tmp.replace(path)` (`os.replace` es POSIX-atomic). Si crashea entre write y replace, `path` queda con la versión vieja (o no existe), nunca corrupto. Importante porque el endpoint commitea la fila DB DESPUÉS del write — entre write y commit puede morir el server, y un archivo huérfano (que cron de Fase 5 limpia) es infinitamente preferible a una fila DB apuntando a un archivo a medias.

---

## Glosario rápido para retomar

- **glm-ocr**: modelo OCR multimodal en formato GGUF, sirve por llama-server, ya está en `llama.cpp/GLM-OCR/`
- **comprobante**: imagen/PDF de depósito bancario que el sistema valida
- **scoring híbrido**: combinación ponderada de Levenshtein + TF-IDF + numérico + temporal
- **multi-tenant**: cada organización ve solo sus datos (Fase 4)
- **CU-02**: caso de uso "Validación manual de comprobantes sospechosos"
