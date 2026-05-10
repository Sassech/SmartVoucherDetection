# Proposal: fase-2-deteccion-duplicados

**Date:** 2026-05-09
**Phase:** Propose
**Change:** `fase-2-deteccion-duplicados`

---

## Intent

Build the duplicate-detection engine for SmartVoucherDetection. Today, Fase 1 only catches
exact byte-level duplicates via SHA-256 lookup in Postgres (no Redis, no fuzzy matching,
no async path). Fase 2 adds:

- **Three-layer cascade**: Redis hash → Postgres exact → weighted scoring, short-circuiting
  on first certain match (≥O(1) → O(log n) → O(n) cost model).
- **State machine**: replaces the hardcoded `estado="recibido"` with proper transitions
  through all states in `diagrama_estados.svg`.
- **Async Celery path**: for WooCommerce / batch use-cases where the caller cannot wait.
- **Manual validation**: `POST /validate/{id}` (CU-02) and `GET /report` aggregation.

Without this, every second upload of the same slip returns a generic 409 with no audit
trail, no fuzzy catch for near-duplicates, and no async option.

---

## Decisions Already Made (not re-discussed)

| Decision | Resolution |
|----------|-----------|
| `texto_extraido` | **Persist from Fase 2** — change `upload.py:204` from `texto_extraido=None` to `texto_extraido=crudos.get("content")`. Enables full S_texto (weight 0.30). |
| `id_comprobante_original` | **Add to `Validacion` in Fase 2** (with migration 2.2.2). Required by Fase 4 side-by-side view; cheapest to capture at detection time. |
| `S_texto` when NULL | Treated as `0.0` — no renormalization of weights. Score ceiling 0.70 for comprobantes with NULL texto; cannot reach 0.90 → won't false-positive as duplicado. |
| Artifact store | `openspec` (file-based) |
| Delivery mode | `ask-on-risk` |

---

## Scope

### In Scope

- `cache_service.py`: add `check_hash` + `set_hash` (Capa 1, task 2.1)
- `services/duplicate_service.py`: NEW — Capa 2 exact query + Capa 3 scoring (tasks 2.2, 2.3)
- `services/state_machine.py`: NEW — all transitions from `diagrama_estados.svg` (task 2.6)
- `routers/upload.py`: integrate 3-layer cascade + state machine + Redis set post-commit; persist `texto_extraido`
- `routers/validate.py`: NEW — `POST /validate/{id}` (CU-02, task 2.5.1)
- `routers/report.py`: NEW — `GET /report` (task 2.5.2)
- `routers/status.py`: NEW — `GET /status/{task_id}` (task 2.4.3)
- `routers/async_upload.py`: NEW — `POST /upload-slip/async` (task 2.4.2)
- `tasks/process_slip.py`: NEW — Celery task wrapping full pipeline (task 2.4.1)
- `schemas/validacion.py` + `schemas/report.py`: NEW response schemas
- `alembic/versions/`: one migration — composite index on `(referencia, monto, fecha_deposito)` + `id_comprobante_original` nullable FK on `Validacion`
- `infra/docker-compose.yml`: add `celery-worker` service
- `api/main.py`: register four new routers
- Tests: unit + integration for every new module (strict_tdd: true)
- Acceptance smoke tests (2.7.1–2.7.5)

### Out of Scope

- Fine-tuning scoring weights (Fase 5.1)
- Real labeled dataset of 100 comprobantes (Fase 5.1) — synthetic dataset used for 2.7.1
- Side-by-side UI for manual review (Fase 4)
- WooCommerce webhook integration (Fase 3)
- `GET /report` filtering by org / date range (future enhancement)

---

## Capabilities

### New Capabilities

- `duplicate-detection-cascade`: Three-layer hash→exact→scoring cascade integrated into
  the upload pipeline; short-circuits on first certain match.
- `state-machine`: Formal state transitions for `Comprobante.estado_actual` per
  `diagrama_estados.svg`; guard clauses prevent invalid transitions.
- `async-processing`: Celery task path (`POST /upload-slip/async` +
  `GET /status/{task_id}`) for non-blocking upload processing.
- `manual-validation`: `POST /validate/{id}` — operator moves a comprobante from
  `en_revision` to `valido` or `duplicado`; records a `manual` Validacion entry.
- `report-aggregation`: `GET /report` — counts by estado + average pipeline latency.

### Modified Capabilities

- `upload-slip`: existing sync endpoint gains 3-layer detection, state-machine transitions,
  Redis set post-commit, and `texto_extraido` persistence.

---

## Approach

### Three-Layer Cascade in `upload.py`

```
[pre-OCR]
  1. compute_hash(bytes) → sha256
  2. cache_service.check_hash(sha256)          ← Capa 1 (Redis, <100ms)
     → hit  → INSERT Validacion(hash_exacto) → 409
     → miss → continue

[post-OCR, after parse_* + normalize_banco]
  3. state_machine.transition(comp, "comparando")
  4. duplicate_service.find_exact_match(ref, monto, fecha)  ← Capa 2 (Postgres)
     → match → INSERT Validacion(campos_exactos) → estado=duplicado → return
  5. duplicate_service.compute_score(nuevo, candidatos)     ← Capa 3
     → score ≥ 0.90 → INSERT Validacion(scoring_ponderado) → estado=duplicado
     → 0.75–0.90   → INSERT Validacion(scoring_ponderado) → estado=sospechoso
     → < 0.75      → estado=valido
  6. cache_service.set_hash(sha256, id_comprobante, ttl_days=7)  ← only on success
```

**Fallback**: if Redis is down, `check_hash` returns `None` (never raises); pipeline falls
through to Capa 2. The existing `catch IntegrityError` (D-11) is preserved.

### State Machine (`services/state_machine.py`)

```
States: recibido | procesando | comparando | valido | sospechoso | duplicado | en_revision | error
Terminals: valido, duplicado, error

Valid transitions:
  recibido    → procesando   (auto, on upload start)
  procesando  → comparando   (auto, post-OCR success)
  procesando  → error        (OCR failure)
  comparando  → valido       (no match, score < 0.75)
  comparando  → sospechoso   (score 0.75–0.90)
  comparando  → duplicado    (hash/exact/score ≥ 0.90)
  comparando  → error        (scoring failure)
  sospechoso  → en_revision  (auto, always — sospechoso is never terminal)
  en_revision → valido       (manual confirm)
  en_revision → duplicado    (manual reject)

Guards:
  - Cannot transition to current state (no-op raises InvalidTransitionError)
  - Cannot transition FROM terminal states
  - POST /validate/{id} only accepted when estado = en_revision
```

### Scoring Formula

```python
Score = 0.35 * S_ref + 0.30 * S_texto + 0.20 * S_monto + 0.15 * S_fecha

S_ref   = Levenshtein.ratio(ref_nuevo, ref_existente)
S_texto = cosine_similarity(tfidf(texto_nuevo), tfidf(texto_existente))
          → 0.0 if either texto_extraido is NULL
S_monto = 1 - abs(a - b) / max(a, b)   # Decimal arithmetic, never float
S_fecha = 1 - min(abs(days_diff), 30) / 30
```

### Celery Design

- App defined in `api/celery_app.py` (new file), imported by worker and by `tasks/`.
- `CELERY_TASK_ALWAYS_EAGER = True` injected in `conftest.py` via `monkeypatch` — tasks
  run synchronously in tests; NO real broker needed.
- Task stores intermediate status in Redis key `task:{task_id}` (JSON, TTL 24h).
- Worker command: `celery -A api.celery_app worker --loglevel=info --concurrency=4`

### New Endpoints

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/upload-slip/async` | same as sync | `{task_id, status: "queued"}` 202 |
| `GET`  | `/status/{task_id}` | public | `{status, result?, error?}` 200 |
| `POST` | `/validate/{id}` | operator | `ComprobanteResponse` 200 |
| `GET`  | `/report` | operator | `{validos, sospechosos, duplicados, avg_latency_ms}` 200 |

### DB Migration (single Alembic revision)

```sql
-- Composite index for Capa 2
CREATE INDEX ix_comprobante_ref_monto_fecha
  ON comprobante (referencia, monto, fecha_deposito);

-- FK for audit trail (Fase 4 side-by-side)
ALTER TABLE validacion
  ADD COLUMN id_comprobante_original UUID
  REFERENCES comprobante(id) ON DELETE SET NULL;
```

### texto_extraido Fix

`api/routers/upload.py`, line 204:
```python
# Before (Fase 1):
texto_extraido=None,
# After (Fase 2):
texto_extraido=crudos.get("content"),
```

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `api/services/cache_service.py` | Modified | Add `check_hash`, `set_hash` |
| `api/services/duplicate_service.py` | **New** | Capa 2 query + Capa 3 scoring |
| `api/services/state_machine.py` | **New** | Transition table + guard clauses |
| `api/tasks/process_slip.py` | **New** | Celery task (full pipeline) |
| `api/celery_app.py` | **New** | Celery app factory |
| `api/routers/upload.py` | Modified | Cascade integration + texto_extraido |
| `api/routers/validate.py` | **New** | `POST /validate/{id}` |
| `api/routers/report.py` | **New** | `GET /report` |
| `api/routers/status.py` | **New** | `GET /status/{task_id}` |
| `api/routers/async_upload.py` | **New** | `POST /upload-slip/async` |
| `api/schemas/validacion.py` | **New** | Validacion + task status schemas |
| `api/schemas/report.py` | **New** | Report schema |
| `api/main.py` | Modified | Register 4 new routers |
| `api/alembic/versions/` | **New** | Composite index + `id_comprobante_original` |
| `infra/docker-compose.yml` | Modified | `celery-worker` service |
| `api/tests/test_cache_service.py` | Modified | `check_hash`/`set_hash` tests |
| `api/tests/test_duplicate_service.py` | **New** | Unit: scoring + Capa 2 query |
| `api/tests/test_state_machine.py` | **New** | Unit: every valid + invalid transition |
| `api/tests/test_upload_endpoint.py` | Modified | Cases: 3-layer cascade active |
| `api/tests/test_validate_endpoint.py` | **New** | Integration: CU-02 |
| `api/tests/test_report_endpoint.py` | **New** | Integration: report counts |
| `api/tests/test_process_slip_task.py` | **New** | Celery: task_always_eager |

---

## Test Strategy

| Layer | Scope | Mock pattern |
|-------|-------|--------------|
| `state_machine` | Unit: all 10 transitions + 5 invalid guards | No mocks — pure Python |
| `cache_service` (check/set_hash) | Unit | `monkeypatch` Redis client |
| `duplicate_service` | Unit: Capa 2 query + Capa 3 scoring (parametric table) | `db_session` fixture (NullPool rollback) |
| `upload.py` integration | Integration: cascade scenarios (Redis hit, exact hit, score hit, valido) | `httpx.MockTransport` for OCR + `monkeypatch` for cache |
| `validate/{id}` + `report` | Integration: ASGI via ASGITransport | Standard `client` fixture |
| Celery task | Unit via `task_always_eager=True` in conftest | Same OCR + cache mocks |
| Acceptance (2.7.x) | Synthetic dataset: 20 unique + 10 duplicates + 10 suspicious | Parametric pytest fixture; no real broker |

**Coverage gate:** existing 96% — must not drop below 70% (CI config).

---

## Recommended Implementation Order

```
[A — Foundations]
A1: upload.py line 204 → persist texto_extraido  (1 line, test update)
A2: state_machine.py                              (task 2.6.1)
A3: test_state_machine.py                         (task 2.6.2)

[B — Synchronous detection layers]
B1: cache_service.py → check_hash + set_hash      (task 2.1)
B2: test_cache_service.py additions
B3: Alembic migration                             (task 2.2.2)
B4: duplicate_service.py → Capa 2                 (task 2.2.1 + 2.2.3)
B5: duplicate_service.py → Capa 3 scoring         (task 2.3)
B6: test_duplicate_service.py
B7: upload.py → integrate cascade                 (task 2.7 integration)
B8: test_upload_endpoint.py updates

[C — New sync endpoints]
C1: validate.py + test_validate_endpoint.py       (task 2.5.1)
C2: report.py + test_report_endpoint.py           (task 2.5.2)

[D — Celery async path]
D1: celery_app.py + docker-compose.yml            (task 2.4.5)
D2: tasks/process_slip.py                         (task 2.4.1)
D3: async_upload.py + status.py                   (tasks 2.4.2 + 2.4.3)
D4: test_process_slip_task.py

[E — Acceptance]
E1: Synthetic dataset fixtures (40 comprobantes)  (task 2.7.1)
E2: Smoke tests 2.7.2–2.7.5
```

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| TF-IDF on short references | Med | S_texto uses `texto_extraido` (full OCR text), NOT `referencia`. Short-text issue only if texto is NULL → treated as 0.0. |
| Score ceiling 0.70 when texto=NULL | Med | Accepted: NULL texto → cannot reach 0.90 → won't false-positive as duplicado. Capa 1+2 still catch exact duplicates. |
| Celery broker not in tests | Med | `CELERY_TASK_ALWAYS_EAGER=True` in conftest; no broker needed in CI. |
| Synthetic dataset doesn't validate scoring | Med | Generate cases programmatically with known field distances; assert score falls in expected bucket. |
| Redis down during Capa 1 | Low | `check_hash` never raises; pipeline falls to Capa 2 automatically. |
| D-12 / 2.7.1 contradiction | Low | Resolved: 2.7.1 uses synthetic dataset; real 100-comprobante benchmark stays in Fase 5.1. |
| Alembic UUID cast gotcha | Low | Use `CAST(:id AS uuid)` pattern (established in Fase 1); not `text(":id::uuid")`. |
| Race condition Capa 1+2 | Low | Preserved existing `catch IntegrityError` in upload.py; Redis is additive, not replacing. |

---

## Rollback Plan

1. **Migration**: run `alembic downgrade -1` — drops composite index and `id_comprobante_original` column.
2. **Code**: revert `upload.py` to Fase 1 version (git revert commit from B7).
3. **Redis keys**: TTL-based expiry (7 days max); no manual cleanup needed.
4. **docker-compose**: remove `celery-worker` service; existing containers unaffected.
5. **New routers**: remove from `main.py`; files can stay inert.

All steps are independently reversible; no cross-phase data loss.

---

## Dependencies

- `python-Levenshtein` (Capa 3: S_ref) — add to `pyproject.toml`
- `scikit-learn` (Capa 3: TF-IDF + cosine) — add to `pyproject.toml`
- `celery[redis]` — add to `pyproject.toml`
- Redis 7 already running (Fase 1 infrastructure)
- PostgreSQL 16 already running (Fase 1 infrastructure)
- Alembic already configured

---

## Success Criteria

- [ ] 2.7.1 — Synthetic dataset: ≥90% correct classification (20 unique + 10 duplicates + 10 suspicious)
- [ ] 2.7.2 — Redis hash exact match detected in <100ms (cache hit path)
- [ ] 2.7.3 — Full synchronous pipeline completes in ≤5s (including OCR)
- [ ] 2.7.4 — Celery task completes in <30s
- [ ] 2.7.5 — `POST /validate/{id}` updates estado correctly in 100% of test cases
- [ ] Coverage does not drop below 70% (currently 96%)
- [ ] All new modules pass `ruff check` + `ruff format` pre-commit hooks
- [ ] `alembic upgrade head` runs clean; `alembic downgrade -1` fully reverts
