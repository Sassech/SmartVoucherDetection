# Design: fase-2-deteccion-duplicados

**Date:** 2026-05-09
**Phase:** Design
**Change:** `fase-2-deteccion-duplicados`

---

## Technical Approach

Three-layer duplicate cascade (Redis hash → Postgres exact → weighted scoring) wired into
the existing sync upload pipeline, guarded by a pure-function state machine, with an
independent Celery async path sharing the same service layer. All new code follows the
established patterns: no-raise infra wrappers, `Decimal` money, `CAST(:id AS uuid)`
migrations, ASGITransport integration tests.

---

## ⚠️ Pre-Implementation Bug: `sospechoso` missing from `ESTADOS_VALIDOS`

**File:** `api/models/comprobante.py`, line 44-52

`ESTADOS_VALIDOS` does not include `"sospechoso"`. The DB `CHECK` constraint will reject
any INSERT/UPDATE setting `estado_actual = "sospechoso"`, breaking Capa 3 classification.

**Fix required BEFORE migration:**

```python
ESTADOS_VALIDOS = (
    "recibido",
    "procesando",
    "comparando",
    "sospechoso",   # ← ADD THIS
    "en_revision",
    "valido",
    "duplicado",
    "error",
)
```

This also requires an Alembic migration to update the `CHECK` constraint (SQLAlchemy
generates it as a literal tuple string). The Fase 2 migration must drop and recreate it.

---

## Architecture Decisions

### Decision: Pure-function state machine (no class)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Dict + free functions | Simple, no instantiation, trivially testable | **CHOSEN** |
| Class-based FSM (e.g. `transitions` lib) | More features, more deps, harder to mock | Rejected |
| Inline checks in each router | Duplication, no single source of truth | Rejected |

`TRANSITIONS` is a module-level `dict[str, set[str]]`. `transition()` is a free function
that mutates `comprobante.estado_actual` in place — caller owns the session commit.

### Decision: `check_hash` returns `UUID | None`, not `str | None`

The existing `_find_existing_by_hash` returns a `Comprobante`. For Capa 1 cache path,
we only need the id to build the 409 response. Returning `UUID | None` avoids an ORM
load just to get an id, consistent with the existing 409 contract in upload.py.
Redis stores the UUID as a UTF-8 string; `check_hash` decodes it.

### Decision: `set_hash` is fire-and-forget, `check_hash` falls through on RedisError

Same pattern as `ping()` — infra wrappers never raise. If Redis is down during
`check_hash`, returns `None` → pipeline falls through to Capa 2 (existing DB path).
This preserves the existing `IntegrityError` race-condition guard.

### Decision: No weight renormalization when `texto_extraido` is NULL

`S_texto = 0.0` when either side is NULL. Maximum reachable score without texto: 0.70
(0.35 + 0.20 + 0.15). This cannot reach the 0.90 `duplicado` threshold — Capa 1 and
Capa 2 still catch those. Score ceiling of 0.70 for NULL-texto pairs prevents
false-positive `duplicado` classification. Decision is ACCEPTED per proposal §Decisions.

### Decision: Celery result backend = Redis, key prefix `celery:`

Same Redis instance, separate logical namespace. No additional infra needed.
`CELERY_TASK_ALWAYS_EAGER=True` in conftest via `monkeypatch` — no broker in CI.

### Decision: `POST /validate/{id}` only accepted when `estado = en_revision`

`sospechoso` auto-transitions to `en_revision` (always). Manual endpoint only acts on
`en_revision`. This keeps the FSM deterministic: no jump from `sospechoso` directly to
`valido` bypassing the audit step.

---

## Data Flow

```
POST /upload-slip
│
├─ 1. _read_upload(bytes)
├─ 2. validate_mime
├─ 3. compute_hash → sha256
│
├─ 4. [CAPA 1] cache_service.check_hash(sha256)
│      hit  ─→ INSERT Validacion(hash_exacto, clasificacion=duplicado)
│              → raise 409
│      miss ─→ continue
│
├─ 5. save_upload (filesystem)
├─ 6. pdf_to_image (if PDF)
├─ 7. preprocess + to_base64
├─ 8. ocr.extract_fields
├─ 9. parse_* + normalize_banco
│      + texto_extraido = crudos.get("content")   ← [FIX line 204]
│
├─ 10. state_machine.transition(comp_stub, "procesando")
│       INSERT Comprobante(estado_actual="procesando", texto_extraido=...)
│       await session.commit()
│
├─ 11. state_machine.transition(comp, "comparando")
│       await session.commit()
│
├─ 12. [CAPA 2] duplicate_service.run_capa2(session, nuevo)
│      hit  ─→ transition("duplicado")
│              INSERT Validacion(campos_exactos, score=None)
│              await session.commit()
│              return 200 ComprobanteResponse
│      miss ─→ continue
│
├─ 13. [CAPA 3] duplicate_service.run_capa3(session, nuevo)
│      score ≥ 0.90 → transition("duplicado")
│      0.75–0.90   → transition("sospechoso") → transition("en_revision")
│      < 0.75      → transition("valido")
│      INSERT Validacion(scoring_ponderado, score=score)
│      await session.commit()
│
├─ 14. cache_service.set_hash(sha256, comp.id_comprobante)   ← fire-and-forget
│
└─ 15. return ComprobanteResponse
```

**Capa 2 exact match query:**
```sql
SELECT * FROM comprobantes
WHERE referencia = :ref AND monto = :monto AND fecha_deposito = :fecha
  AND deleted_at IS NULL
  AND id_comprobante != :self_id
ORDER BY fecha_registro DESC
LIMIT 1
```
Uses the new composite index `idx_comp_dedup`.

**Capa 3 candidate window:**
Same filter as Capa 2 but relaxed: `fecha_deposito BETWEEN :fecha - 30 AND :fecha + 30`.
Returns all candidates; `compute_score` runs against each; best score wins.

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `api/models/comprobante.py` | **Modify** | Add `"sospechoso"` to `ESTADOS_VALIDOS` |
| `api/services/state_machine.py` | **Create** | `TRANSITIONS` dict, `InvalidTransitionError`, `transition()` |
| `api/services/duplicate_service.py` | **Create** | `compute_score`, `classify`, `find_candidates`, `run_capa2`, `run_capa3` |
| `api/services/cache_service.py` | **Modify** | Add `check_hash(sha256) → UUID \| None`, `set_hash(sha256, id, ttl_days)` |
| `api/routers/upload.py` | **Modify** | Integrate 3-layer cascade, state machine, `texto_extraido` fix (line 204) |
| `api/routers/validate.py` | **Create** | `POST /validate/{id}` — manual CU-02 |
| `api/routers/report.py` | **Create** | `GET /report` — aggregated counts + avg latency |
| `api/routers/status.py` | **Create** | `GET /status/{task_id}` — Celery result poll |
| `api/routers/async_upload.py` | **Create** | `POST /upload-slip/async` — enqueue task |
| `api/tasks/process_slip.py` | **Create** | Celery task wrapping full pipeline |
| `api/celery_app.py` | **Create** | Celery app factory (`broker=redis_url, backend=redis_url`) |
| `api/schemas/validacion.py` | **Create** | `ValidacionResponse`, `TaskStatusResponse` |
| `api/schemas/report.py` | **Create** | `ReportResponse` |
| `api/main.py` | **Modify** | Register 4 new routers |
| `api/alembic/versions/XXXX_fase2_schema.py` | **Create** | Drop+recreate CHECK, composite index, `id_comprobante_original` FK |
| `infra/docker-compose.yml` | **Modify** | Add `celery-worker` service |
| `api/pyproject.toml` | **Modify** | Add `python-Levenshtein`, `scikit-learn`, `celery[redis]` |
| `api/tests/test_state_machine.py` | **Create** | All valid + invalid transitions (no DB) |
| `api/tests/test_cache_service.py` | **Modify** | `check_hash` / `set_hash` cases (mock Redis) |
| `api/tests/test_duplicate_service.py` | **Create** | `compute_score` parametric + `find_candidates` DB fixture |
| `api/tests/test_upload_endpoint.py` | **Modify** | Extend with Capa 1/2/3 dedup scenarios |
| `api/tests/test_validate_endpoint.py` | **Create** | CU-02 integration |
| `api/tests/test_report_endpoint.py` | **Create** | Report counts integration |
| `api/tests/test_process_slip_task.py` | **Create** | Celery `task_always_eager` |

---

## Interfaces / Contracts

### `services/state_machine.py`

```python
TRANSITIONS: dict[str, set[str]] = {
    "recibido":    {"procesando"},
    "procesando":  {"comparando", "error"},
    "comparando":  {"valido", "sospechoso", "duplicado", "error"},
    "sospechoso":  {"en_revision"},
    "en_revision": {"valido", "duplicado"},
    # valido, duplicado, error → terminal (no outgoing edges)
}

class InvalidTransitionError(Exception):
    def __init__(self, from_state: str, to_state: str) -> None: ...

async def transition(
    comp: Comprobante,
    new_state: str,
    session: AsyncSession,
) -> None:
    """Mutates comp.estado_actual. Caller commits."""
```

### `services/cache_service.py` additions

```python
KEY_PREFIX = "comp:hash:"

async def check_hash(sha256: str) -> UUID | None:
    """Redis GET → UUID. Returns None on miss or RedisError. Never raises."""

async def set_hash(sha256: str, comp_id: UUID, ttl_days: int = 7) -> None:
    """Redis SETEX. Fire-and-forget. Never raises."""
```

### `services/duplicate_service.py`

```python
def compute_score(nuevo: Comprobante, existente: Comprobante) -> float:
    # S_ref: Levenshtein.ratio — 0.0 if either referencia is None
    # S_texto: TF-IDF cosine — 0.0 if either texto_extraido is None
    # S_monto: 1 - abs(a-b)/max(a,b) — Decimal arithmetic — 0.0 if either None
    # S_fecha: 1 - min(abs(days), 30)/30 — 0.0 if either fecha is None
    # Score = 0.35*S_ref + 0.30*S_texto + 0.20*S_monto + 0.15*S_fecha

def classify(score: float) -> str:
    # >= 0.90 → "duplicado" | >= 0.75 → "sospechoso" | else → "valido"

async def find_candidates(
    session: AsyncSession, nuevo: Comprobante
) -> list[Comprobante]:
    # 30-day window, same org, not deleted, id != nuevo.id_comprobante

async def run_capa2(
    session: AsyncSession, nuevo: Comprobante
) -> Comprobante | None:
    # Exact: referencia + monto + fecha_deposito (uses composite index)

async def run_capa3(
    session: AsyncSession, nuevo: Comprobante
) -> tuple[Comprobante | None, float, str]:
    # (best_match, score, clasificacion); best_match=None + score=0.0 if no candidates
```

### `schemas/validacion.py`

```python
class ValidacionResponse(BaseModel):
    id_validacion: UUID
    id_comprobante: UUID
    id_comprobante_original: UUID | None
    clasificacion: str
    metodo_deteccion: str
    score_similitud: float | None
    fecha_validacion: datetime

class TaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "done", "error"]
    result: ComprobanteResponse | None = None
    error: str | None = None
```

### Migration (single Alembic revision)

```sql
-- 1. Fix CHECK constraint (sospechoso was missing)
ALTER TABLE comprobantes DROP CONSTRAINT ck_comprobantes_estado_actual;
ALTER TABLE comprobantes ADD CONSTRAINT ck_comprobantes_estado_actual
  CHECK (estado_actual IN ('recibido','procesando','comparando','sospechoso',
                           'en_revision','valido','duplicado','error'));

-- 2. Composite index for Capa 2 (CONCURRENTLY → no table lock)
CREATE INDEX CONCURRENTLY idx_comp_dedup
  ON comprobantes (referencia, monto, fecha_deposito)
  WHERE referencia IS NOT NULL;

-- 3. FK for audit trail
ALTER TABLE validaciones
  ADD COLUMN id_comprobante_original UUID
  REFERENCES comprobantes(id_comprobante) ON DELETE SET NULL;
```

**Note:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. The Alembic
migration must use `op.execute()` outside `with op.get_bind() as conn` or set
`transaction_per_migration = false` in `alembic.ini`.

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — `state_machine` | All 10 valid transitions + 5 invalid guards (same state, terminal, invalid pair) | Pure Python, no DB, no mocks |
| Unit — `cache_service` | `check_hash` hit/miss/RedisError, `set_hash` success/error | `monkeypatch` Redis client |
| Unit — `duplicate_service` | `compute_score` with known inputs (parametric table covering NULL fields), `classify` thresholds, `run_capa2` hit/miss | `db_session` NullPool fixture |
| Integration — `upload.py` | Capa 1 Redis hit → 409; Capa 2 exact hit → 200 duplicado; Capa 3 score hit → 200 sospechoso; clean upload → 201 valido | `httpx.MockTransport` for OCR + `monkeypatch` for cache |
| Integration — `validate` | `en_revision → valido`, `en_revision → duplicado`, 409 on wrong state | ASGITransport `client` fixture |
| Integration — `report` | Counts match DB state | ASGITransport `client` fixture |
| Celery — `process_slip` | Full pipeline via `CELERY_TASK_ALWAYS_EAGER=True` in `conftest.py` | Same OCR + cache mocks as upload |
| Acceptance — `2.7.x` | Synthetic dataset: 20 unique + 10 duplicates + 10 suspicious → ≥90% correct | Parametric pytest fixture, no real broker |

---

## Migration / Rollout

**Recommended implementation order matches proposal §Recommended Implementation Order:**
`A (foundations) → B (sync detection) → C (new sync endpoints) → D (Celery) → E (acceptance)`

**Rollback:**
1. `alembic downgrade -1` — restores CHECK, drops index + column.
2. `git revert` upload.py cascade commit (B7).
3. Redis keys expire via TTL (7d max) — no manual cleanup.
4. Remove `celery-worker` from docker-compose; existing containers unaffected.

**400-line PR budget:** This change touches ~20 files. Chained PRs recommended:
- PR-A: `state_machine.py` + `comprobante.py` fix + migration (foundations)
- PR-B: `duplicate_service.py` + `cache_service.py` additions + `upload.py` integration
- PR-C: New routers (`validate`, `report`, `status`, `async_upload`) + schemas
- PR-D: Celery task + `celery_app.py` + `docker-compose.yml` + acceptance tests

---

## Open Questions

- [ ] **`CREATE INDEX CONCURRENTLY` in Alembic**: must confirm `transaction_per_migration`
  config or use raw `op.execute()` with explicit non-transactional context. Needs
  verification against project's `alembic.ini`.
- [ ] **`GET /report` scope**: counts across ALL orgs or scoped to `id_usuario`?
  Proposal says no org filtering yet, but the model has `id_usuario` on comprobantes.
  Default: global counts. Clarify before implementing `report.py`.
- [ ] **`/status/{task_id}` result shape when `done`**: confirmed as full
  `ComprobanteResponse` per `TaskStatusResponse` schema above. Verify with team.
