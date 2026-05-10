# Fase 2 — Motor de Detección de Duplicados: Especificación

**Change:** `fase-2-deteccion-duplicados`  
**Date:** 2026-05-09  
**Phase:** Spec  
**Mode:** openspec (new specs — no prior specs exist for these capabilities)

---

## CAP-01: Persistencia de `texto_extraido`

### Requirement: Persist Raw OCR Text on Upload

The system MUST persist the raw OCR text returned by the extraction service as `texto_extraido` on every new `Comprobante` record created via `POST /upload-slip`.

The system MUST accept `NULL` as a valid value for `texto_extraido` (e.g., when the OCR service returns no content field).

The system SHOULD NOT renormalize scoring weights when `texto_extraido` is NULL; instead, `S_texto` MUST be treated as `0.0`, capping the maximum achievable score at `0.70`.

#### Scenario: OCR returns content — texto_extraido is persisted

- GIVEN a valid image upload where the OCR service response includes a `content` field
- WHEN `POST /upload-slip` processes the file successfully
- THEN the created `Comprobante` record has `texto_extraido` set to the value of `crudos["content"]`
- AND the value is retrievable via subsequent reads of that comprobante

#### Scenario: OCR returns no content field — texto_extraido is NULL

- GIVEN a valid image upload where the OCR service response does NOT include a `content` field
- WHEN `POST /upload-slip` processes the file successfully
- THEN the created `Comprobante` record has `texto_extraido = NULL`
- AND the upload still succeeds (no error raised for missing content)

#### Scenario: NULL texto_extraido caps scoring ceiling at 0.70

- GIVEN two comprobantes where both have `texto_extraido = NULL`
- WHEN `compute_score(nuevo, existente)` is computed
- THEN `S_texto` evaluates to `0.0`
- AND the maximum possible score is `0.70` (sum of `S_ref×0.35 + S_monto×0.20 + S_fecha×0.15`)
- AND the `duplicado` threshold of `0.90` is unreachable without texto

#### Scenario: Existing comprobantes with NULL texto_extraido remain valid

- GIVEN comprobantes created before Fase 2 that have `texto_extraido = NULL`
- WHEN any detection layer reads those records
- THEN no error is raised for the NULL value
- AND those records participate normally in Capa 2 and Capa 1 detection

**Constraints:**
- Backward-compatible: NULL is always valid; no backfill required.
- Score ceiling of `0.70` when texto is NULL is an accepted product decision, not a bug.
- No weight renormalization when texto is NULL.

---

## CAP-02: Máquina de Estados (`state_machine.py`)

### Requirement: Formal State Transitions for Comprobante

The system MUST enforce a formal state machine for `Comprobante.estado_actual` with exactly eight states: `recibido`, `procesando`, `comparando`, `en_revision`, `valido`, `sospechoso`, `duplicado`, `error`.

Terminal states are: `valido`, `duplicado`, `error`. The system MUST NOT allow any transition FROM a terminal state.

The system MUST expose a `transition(comp: Comprobante, target_state: str) -> Comprobante` function that applies the transition and returns the updated comprobante.

The system MUST raise `InvalidTransitionError` for any illegal transition, including transitions to the current state (no self-loops).

Valid transitions are exactly:

| From | To | Trigger |
|------|----|---------|
| `recibido` | `procesando` | upload start |
| `procesando` | `comparando` | OCR success |
| `procesando` | `error` | OCR failure |
| `comparando` | `valido` | score < 0.75, no match |
| `comparando` | `sospechoso` | 0.75 ≤ score < 0.90 |
| `comparando` | `duplicado` | hash/exact match or score ≥ 0.90 |
| `comparando` | `error` | scoring failure |
| `sospechoso` | `en_revision` | automatic (sospechoso is never terminal) |
| `en_revision` | `valido` | manual confirm |
| `en_revision` | `duplicado` | manual reject |

#### Scenario: Valid transition succeeds and updates estado

- GIVEN a `Comprobante` with `estado_actual = "recibido"`
- WHEN `transition(comp, "procesando")` is called
- THEN the comprobante's `estado_actual` becomes `"procesando"`
- AND the updated comprobante is returned

#### Scenario: Illegal transition raises InvalidTransitionError

- GIVEN a `Comprobante` with `estado_actual = "procesando"`
- WHEN `transition(comp, "valido")` is called (not an allowed edge)
- THEN `InvalidTransitionError` is raised
- AND `estado_actual` remains unchanged

#### Scenario: Self-transition raises InvalidTransitionError

- GIVEN a `Comprobante` with `estado_actual = "comparando"`
- WHEN `transition(comp, "comparando")` is called
- THEN `InvalidTransitionError` is raised

#### Scenario: Transition FROM terminal state is forbidden

- GIVEN a `Comprobante` with `estado_actual = "valido"` (terminal)
- WHEN `transition(comp, "procesando")` is called
- THEN `InvalidTransitionError` is raised

#### Scenario: sospechoso auto-advances to en_revision

- GIVEN a `Comprobante` with `estado_actual = "comparando"`
- WHEN `transition(comp, "sospechoso")` is called
- THEN `estado_actual` becomes `"sospechoso"`
- AND the caller is responsible for immediately calling `transition(comp, "en_revision")` afterward (the state machine records the intermediate state)

**Constraints:**
- `InvalidTransitionError` is a custom exception defined in `state_machine.py`.
- No I/O inside the state machine — it operates only on the in-memory model.
- All 10 valid transitions AND all illegal transitions MUST have unit tests (no mocks needed — pure Python).

---

## CAP-03: Capa 1 — Hash Exacto Redis

### Requirement: Redis-backed Hash Lookup and Storage

The system MUST provide `check_hash(sha256: str) -> UUID | None` that returns the `id_comprobante` of an existing comprobante if the hash is found in Redis, or `None` if not found or if Redis is unavailable.

The system MUST provide `set_hash(sha256: str, comp_id: UUID, ttl_days: int = 7) -> None` that stores the hash→id mapping in Redis with the given TTL.

The system MUST use the key pattern `comp:hash:{sha256}` for all hash entries.

The system MUST fall back to `None` (not raise) when Redis is unavailable — the pipeline continues to Capa 2.

#### Scenario: Hash found in Redis — returns existing id

- GIVEN a hash `h` is stored in Redis under key `comp:hash:{h}` with value `{uuid}`
- WHEN `check_hash(h)` is called
- THEN the function returns the UUID of the existing comprobante
- AND no database query is made

#### Scenario: Hash not in Redis — returns None

- GIVEN a hash `h` is NOT stored in Redis
- WHEN `check_hash(h)` is called
- THEN the function returns `None`
- AND the pipeline proceeds to Capa 2

#### Scenario: Redis is down — returns None without raising

- GIVEN Redis is unavailable (connection refused)
- WHEN `check_hash(sha256)` is called
- THEN the function returns `None`
- AND no exception propagates to the caller

#### Scenario: set_hash stores key with correct TTL

- GIVEN a comprobante with id `{uuid}` and hash `h`
- WHEN `set_hash(h, uuid, ttl_days=7)` is called
- THEN Redis contains key `comp:hash:{h}` with value `{uuid}`
- AND the key has a TTL between 604,799 and 604,800 seconds (7 days ±1s)

#### Scenario: set_hash silently swallows Redis errors

- GIVEN Redis is unavailable
- WHEN `set_hash(h, uuid)` is called
- THEN no exception propagates
- AND the function returns normally

**Constraints:**
- Both functions MUST never raise — any Redis error is swallowed and logged.
- `decode_responses=False` is the established pool pattern; callers handle decoding.
- TTL default is 7 days. Callers MAY override.
- Key pattern is exactly `comp:hash:{sha256}` (no other format).

---

## CAP-04: Capa 2 — Exact Match Postgres

### Requirement: Exact Field Query for Duplicate Detection

The system MUST query the `comprobante` table for existing records matching `referencia`, `monto`, AND `fecha_deposito` simultaneously, excluding soft-deleted records (`deleted_at IS NULL`).

On a match, the system MUST create a `Validacion` record with `metodo_deteccion = "campos_exactos"` and `clasificacion = "duplicado"`.

On a match, the system MUST also set `id_comprobante_original` on the `Validacion` record to the ID of the matched comprobante.

A composite index on `(referencia, monto, fecha_deposito)` MUST exist before this query runs in production (Alembic migration).

#### Scenario: Exact match found — returns matched comprobante and creates Validacion

- GIVEN a comprobante exists with `referencia="TRF-001"`, `monto=1500.00`, `fecha_deposito=2026-05-01`
- WHEN `find_exact_match(referencia="TRF-001", monto=1500.00, fecha="2026-05-01")` is called
- THEN the existing comprobante is returned
- AND a `Validacion` record is created with `metodo_deteccion="campos_exactos"`, `clasificacion="duplicado"`, and `id_comprobante_original` set to the matched comprobante's ID

#### Scenario: No exact match — returns None

- GIVEN no comprobante exists with `referencia="TRF-999"`, `monto=500.00`, `fecha_deposito=2026-05-01`
- WHEN `find_exact_match(referencia="TRF-999", monto=500.00, fecha="2026-05-01")` is called
- THEN the function returns `None`
- AND no `Validacion` record is created

#### Scenario: Soft-deleted records are excluded from matching

- GIVEN a comprobante exists with matching fields but `deleted_at IS NOT NULL`
- WHEN `find_exact_match(...)` is called with those same fields
- THEN the function returns `None` (soft-deleted record is not a match)

#### Scenario: Partial field match does not trigger duplicate

- GIVEN a comprobante with `referencia="TRF-001"`, `monto=1500.00`, `fecha_deposito=2026-05-01`
- WHEN `find_exact_match(referencia="TRF-001", monto=1500.00, fecha="2026-05-02")` is called (different date)
- THEN the function returns `None`

**Constraints:**
- `monto` MUST use `Decimal` arithmetic — never `float` (established D-10 rule).
- Composite index `ix_comprobante_ref_monto_fecha` is required via Alembic migration before deploy.
- `id_comprobante_original UUID FK nullable` column MUST be added to `Validacion` in the same migration.
- The FK uses `ON DELETE SET NULL`.

---

## CAP-05: Capa 3 — Scoring Ponderado

### Requirement: Weighted Similarity Scoring for Near-Duplicate Detection

The system MUST implement `compute_score(nuevo: Comprobante, existente: Comprobante) -> float` using the weighted formula:

```
Score = 0.35×S_ref + 0.30×S_texto + 0.20×S_monto + 0.15×S_fecha
```

Where:
- `S_ref` = `Levenshtein.ratio(ref_nuevo, ref_existente)`
- `S_texto` = `cosine_similarity(tfidf(texto_nuevo), tfidf(texto_existente))` — or `0.0` if either `texto_extraido` is NULL
- `S_monto` = `1 - abs(a - b) / max(a, b)` using Decimal arithmetic
- `S_fecha` = `1 - min(abs(days_diff), 30) / 30`

The system MUST implement `classify(score: float) -> Literal["valido", "sospechoso", "duplicado"]`:
- `score >= 0.90` → `"duplicado"`
- `0.75 <= score < 0.90` → `"sospechoso"`
- `score < 0.75` → `"valido"`

The system MUST implement `find_candidates(nuevo: Comprobante) -> list[Comprobante]` that returns comprobantes from the same user/organization within a 30-day window of `fecha_deposito`.

On result, the system MUST create a `Validacion` record with `metodo_deteccion = "scoring_ponderado"`, the computed `score_similitud`, and the resulting `clasificacion`.

#### Scenario: Both comprobantes have texto — full score computed

- GIVEN `nuevo` and `existente` both have non-NULL `texto_extraido` and identical `referencia`, `monto`, `fecha_deposito`
- WHEN `compute_score(nuevo, existente)` is called
- THEN the score is `1.0` (all components are `1.0`)
- AND `classify(1.0)` returns `"duplicado"`

#### Scenario: texto_extraido is NULL — S_texto is 0.0

- GIVEN `nuevo.texto_extraido = NULL` (or `existente.texto_extraido = NULL`)
- WHEN `compute_score(nuevo, existente)` is called
- THEN `S_texto` contributes `0.0` to the score
- AND the maximum possible score is `0.70`

#### Scenario: Score in sospechoso range triggers sospechoso classification

- GIVEN `compute_score` returns `0.82`
- WHEN `classify(0.82)` is called
- THEN the result is `"sospechoso"`

#### Scenario: Score below valido threshold returns valido

- GIVEN `compute_score` returns `0.60`
- WHEN `classify(0.60)` is called
- THEN the result is `"valido"`

#### Scenario: find_candidates limits window to 30 days

- GIVEN a nuevo comprobante with `fecha_deposito = 2026-05-01`
- WHEN `find_candidates(nuevo)` is called
- THEN only comprobantes with `fecha_deposito` between `2026-04-01` and `2026-05-31` are returned
- AND comprobantes outside this window are excluded

#### Scenario: scoring_ponderado Validacion record is created on any result

- GIVEN `compute_score` returns `0.85` (sospechoso)
- WHEN the scoring layer processes the result
- THEN a `Validacion` record is created with `metodo_deteccion="scoring_ponderado"`, `score_similitud=0.85`, `clasificacion="sospechoso"`

**Constraints:**
- `S_monto` MUST use `Decimal` — never `float` (D-10).
- `S_texto = 0.0` when either text is NULL — no renormalization.
- `find_candidates` window is always exactly 30 days.
- Score is a `float` in `[0.0, 1.0]`.
- Acceptance gate: ≥90% correct classification on synthetic dataset of 40 comprobantes (2.7.1).

---

## CAP-06: Celery Task + Nuevos Endpoints

### Requirement: Async Pipeline Task

The system MUST provide a Celery task in `tasks/process_slip.py` that executes the full upload pipeline (OCR + 3-layer detection) asynchronously.

The task MUST store intermediate status in Redis under key `task:{task_id}` as JSON with TTL of 24 hours.

#### Scenario: Async upload enqueues task and returns 202

- GIVEN a valid image file
- WHEN `POST /upload-slip/async` is called
- THEN the response is HTTP 202
- AND the body contains `{task_id: "<uuid>", status: "queued"}`
- AND the task is enqueued without blocking the HTTP response

#### Scenario: Status endpoint returns current task state

- GIVEN a task with id `t1` that has been enqueued
- WHEN `GET /status/t1` is called
- THEN the response contains `{task_id: "t1", status: "<pending|processing|done|error>"}` with HTTP 200
- AND `result` is included in the body when `status = "done"`
- AND `error` is included in the body when `status = "error"`

#### Scenario: Status endpoint returns 404 for unknown task

- GIVEN no task exists with id `t-unknown`
- WHEN `GET /status/t-unknown` is called
- THEN the response is HTTP 404

### Requirement: Manual Validation Endpoint (CU-02)

The system MUST provide `POST /validate/{id}` that allows an operator to transition a comprobante from `en_revision` to either `valido` or `duplicado`.

The endpoint MUST reject the request with HTTP 422 if the comprobante's current state is not `en_revision`.

On success, the system MUST create a `Validacion` record with `metodo_deteccion = "manual"`.

#### Scenario: Operator confirms valid — estado transitions to valido

- GIVEN a comprobante with `estado_actual = "en_revision"`
- WHEN `POST /validate/{id}` is called with body `{"accion": "valido"}`
- THEN the comprobante's `estado_actual` becomes `"valido"`
- AND a `Validacion` record is created with `metodo_deteccion="manual"`, `clasificacion="valido"`
- AND the response returns the updated `ComprobanteResponse` with HTTP 200

#### Scenario: Operator rejects — estado transitions to duplicado

- GIVEN a comprobante with `estado_actual = "en_revision"`
- WHEN `POST /validate/{id}` is called with body `{"accion": "duplicado"}`
- THEN the comprobante's `estado_actual` becomes `"duplicado"`
- AND a `Validacion` record is created with `metodo_deteccion="manual"`, `clasificacion="duplicado"`

#### Scenario: Validate rejected when not in en_revision

- GIVEN a comprobante with `estado_actual = "valido"` (already terminal)
- WHEN `POST /validate/{id}` is called
- THEN the response is HTTP 422
- AND the comprobante's state is unchanged

### Requirement: Report Aggregation Endpoint

The system MUST provide `GET /report` that returns aggregate counts of comprobantes by estado and the average pipeline processing time in milliseconds.

#### Scenario: Report returns counts by estado and avg latency

- GIVEN the database contains comprobantes: 15 `valido`, 5 `sospechoso`, 3 `duplicado`, 2 `error`
- WHEN `GET /report` is called
- THEN the response contains `{validos: 15, sospechosos: 5, duplicados: 3, errores: 2, avg_latency_ms: <float>}`
- AND HTTP 200 is returned

#### Scenario: Report returns zeros when no comprobantes exist

- GIVEN the database has no comprobantes
- WHEN `GET /report` is called
- THEN all counts are `0` and `avg_latency_ms` is `null` or `0.0`

**Constraints:**
- Celery tasks MUST run synchronously in tests via `CELERY_TASK_ALWAYS_EAGER = True` in `conftest.py` — no real broker needed in CI.
- Task Redis TTL for status keys: 24 hours.
- Celery task MUST complete in under 30 seconds (2.7.4).
- `POST /validate/{id}` MUST correctly update state in 100% of integration tests (2.7.5).
- `GET /report` does NOT support filtering by org or date range in Fase 2 (out of scope).
- All endpoints require operator-level auth except `GET /status/{task_id}` (public).
