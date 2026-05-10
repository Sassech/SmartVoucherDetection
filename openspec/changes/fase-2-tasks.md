# Tasks: fase-2-deteccion-duplicados

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~780–950 (20+ files, 7 new services/routers, 7 new test files) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR-A (Block A) → PR-B (Block B) → PR-C (Block C) → PR-D (Block D+E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| Block A | Bug fix + state machine + texto_extraido | PR-A | Base: main; self-contained, no new deps |
| Block B | Detection cascade (Redis + Postgres + scoring) | PR-B | Base: PR-A branch; requires migration from A0 |
| Block C | New sync endpoints (validate + report) | PR-C | Base: PR-B branch; depends on state_machine + duplicate_service |
| Block D+E | Celery async path + acceptance tests | PR-D | Base: PR-C branch; all prior layers must exist |

---

## Phase 1: Block A — Foundations (must complete first)

- [x] **A0.1** `api/models/comprobante.py`: Add `"sospechoso"` to `ESTADOS_VALIDOS` tuple (line 48, after `"comparando"`)
  - Files: `api/models/comprobante.py`
  - Tests: verify `"sospechoso" in ESTADOS_VALIDOS` (import check, 1 case)
  - Done when: `ESTADOS_VALIDOS` has all 8 states; existing tests still pass
  - Est. lines: 1 changed
  - Deps: none

- [x] **A0.2** Alembic migration `XXXX_fase2_schema.py`: Drop + recreate `ck_comprobantes_estado_actual` CHECK with all 8 states; add composite index `idx_comp_dedup` on `(referencia, monto, fecha_deposito)` WHERE referencia IS NOT NULL; add `id_comprobante_original UUID FK nullable` on `validaciones` (ON DELETE SET NULL). Use `op.execute()` outside transaction for `CREATE INDEX CONCURRENTLY`.
  - Files: `api/alembic/versions/XXXX_fase2_schema.py`
  - Tests: `alembic upgrade head` + `alembic downgrade -1` run clean (1 manual check)
  - Done when: migration applies cleanly on a fresh DB; all 3 changes present; rollback restores prior state
  - Est. lines: ~60
  - Deps: A0.1

- [x] **A1** `api/routers/upload.py` line 204: Change `texto_extraido=None` → `texto_extraido=crudos.get("content")`
  - Files: `api/routers/upload.py`
  - Tests: `test_upload_endpoint.py` — 2 cases: OCR returns content → persisted; OCR omits content → NULL, upload succeeds
  - Done when: both scenarios pass; existing upload tests unbroken
  - Est. lines: 1 changed + ~15 test lines
  - Deps: A0.2

- [x] **A2** Create `api/services/state_machine.py`: `TRANSITIONS` dict (10 valid edges), `InvalidTransitionError`, async `transition(comp, new_state, session)` — mutates `comp.estado_actual`; caller commits. Terminal states: `valido`, `duplicado`, `error`.
  - Files: `api/services/state_machine.py` (new), `api/tests/test_state_machine.py` (new)
  - Tests: 10 valid transitions + 5 invalid guards (self-loop, terminal-from, unknown-to) — no DB, no mocks; min 15 cases
  - Done when: all 15 tests pass; `InvalidTransitionError` propagates correctly; no I/O inside module
  - Est. lines: ~80 impl + ~90 tests
  - Deps: A0.1

---

## Phase 2: Block B — Synchronous Detection Layers

- [x] **B1** `api/services/cache_service.py`: Add `check_hash(sha256: str) -> UUID | None` (key `comp:hash:{sha256}`, falls through on RedisError) and `set_hash(sha256: str, comp_id: UUID, ttl_days: int = 7) -> None` (fire-and-forget).
  - Files: `api/services/cache_service.py`, `api/tests/test_cache_service.py`
  - Tests: `check_hash` hit / miss / RedisError (3); `set_hash` success / error (2); min 5 cases; `monkeypatch` Redis client
  - Done when: all 5 cases pass; neither function ever raises; key pattern is exactly `comp:hash:{sha256}`
  - Est. lines: ~45 impl + ~60 tests
  - Deps: A0.2

- [x] **B2** Alembic migration `34b207551c82_fase2_dedup_index_and_validacion_fk.py`: add `idx_comp_dedup` composite index + `id_comprobante_original` FK to validaciones; add `id_comprobante_original` to `Validacion` model; fix `Comprobante.validaciones` relationship `foreign_keys`.
  - Files: `api/alembic/versions/34b207551c82_fase2_dedup_index_and_validacion_fk.py`, `api/models/validacion.py`, `api/models/comprobante.py`
  - Tests: migration applied cleanly (`alembic upgrade head`)
  - Done: migration applied; model updated; SQLAlchemy relationship ambiguity resolved via `foreign_keys`
  - Note: deps were already in pyproject.toml (celery, levenshtein, scikit-learn pre-installed in PR-A context)

- [x] **B3** Create `api/services/duplicate_service.py`: `compute_score`, `classify`, `find_candidates`, `run_capa2`, `run_capa3`. `S_monto` uses `Decimal`; `S_texto = 0.0` when either texto is NULL; `find_candidates` window exactly ±30 days; `run_capa2` creates `Validacion(metodo_deteccion="campos_exactos")` on hit; `run_capa3` creates `Validacion(metodo_deteccion="scoring_ponderado")` always.
  - Files: `api/services/duplicate_service.py` (new), `api/tests/test_duplicate_service.py` (new)
  - Tests: 40 tests covering all components; pure functions + mock AsyncSession
  - Done when: all 40 tests pass; `S_monto` uses Decimal; no float money

- [x] **B4** `api/routers/upload.py`: Integrate 3-layer cascade — pre-OCR Capa 1 (`check_hash` → 409 on hit); post-OCR state transitions (`procesando` → `comparando`); Capa 2 (`run_capa2` → `duplicado` + return on hit); Capa 3 (`run_capa3` → transition to result state + auto `sospechoso → en_revision`); `set_hash` fire-and-forget post-commit.
  - Files: `api/routers/upload.py`, `api/tests/test_upload_endpoint.py`
  - Tests: 4 new cascade scenario tests + updated happy path; 11 total upload tests pass
  - Done: all cascade scenarios pass; Fase 1 upload tests updated for new estado_actual behavior

---

## Phase 3: Block C — New Sync Endpoints

- [x] **C1** Create `api/schemas/validacion.py` (`ValidacionResponse`, `TaskStatusResponse`) and `api/schemas/report.py` (`ReportResponse`).
  - Files: `api/schemas/validacion.py` (new), `api/schemas/report.py` (new)
  - Tests: Pydantic model instantiation smoke tests (2 cases — valid input, missing optional fields)
  - Done when: schemas import cleanly; all fields match design contracts; `TaskStatusResponse` has correct `Literal` status
  - Est. lines: ~40
  - Deps: none

- [x] **C2** Create `api/routers/validate.py`: `POST /validate/{id}` — guard `estado == en_revision` (else 422); apply `transition(comp, accion)`; insert `Validacion(metodo_deteccion="manual")`; return `ComprobanteResponse` 200.
  - Files: `api/routers/validate.py` (new), `api/tests/test_validate_endpoint.py` (new)
  - Tests: `en_revision → valido` (200); `en_revision → duplicado` (200); wrong state → 422; unknown id → 404; min 4 cases; ASGITransport `client` fixture
  - Done when: all 4 cases pass; `Validacion(metodo_deteccion="manual")` created on success; state unchanged on 422
  - Est. lines: ~45 impl + ~70 tests
  - Deps: A2, C1

- [x] **C3** Create `api/routers/report.py`: `GET /report` — aggregate counts by estado (`valido`, `sospechoso`, `duplicado`, `error`) + `avg_latency_ms` from `fecha_registro` delta. Global counts (no org filter in Fase 2).
  - Files: `api/routers/report.py` (new), `api/tests/test_report_endpoint.py` (new)
  - Tests: counts match seeded DB (15v+5s+3d+2e); empty DB → all zeros + null latency; min 2 cases; ASGITransport
  - Done when: both cases pass; response shape matches `ReportResponse`; no org filtering applied
  - Est. lines: ~40 impl + ~50 tests
  - Deps: C1

- [x] **C4** `api/main.py`: Register `validate`, `report` routers (+ `status`, `async_upload` from Block D).
  - Files: `api/main.py`
  - Tests: `GET /docs` returns 200 and lists all 4 new paths (smoke)
  - Done when: all 4 new routes visible in OpenAPI schema; existing routes unaffected
  - Est. lines: ~8
  - Deps: C2, C3 (partial; complete after D2)

---

## Phase 4: Block D — Celery Async Path

- [ ] **D1** Create `api/celery_app.py`: Celery app factory (`broker=redis_url, backend=redis_url`, key prefix `celery:`). Add `CELERY_TASK_ALWAYS_EAGER=True` to `conftest.py` via `monkeypatch`.
  - Files: `api/celery_app.py` (new), `api/tests/conftest.py`
  - Tests: `celery_app.conf.task_always_eager` is True in test env (1 case)
  - Done when: app imports without errors; no real broker needed in CI; eager mode confirmed
  - Est. lines: ~25 impl + ~10 conftest
  - Deps: B2

- [ ] **D2** Create `api/tasks/process_slip.py`: Celery task wrapping full upload pipeline (OCR + 3-layer cascade); stores status in Redis `task:{task_id}` as JSON (TTL 24h); completes in <30s.
  - Files: `api/tasks/process_slip.py` (new), `api/tests/test_process_slip_task.py` (new)
  - Tests: full pipeline via eager mode → `done` status; OCR failure → `error` status; status key TTL = 24h; min 3 cases; same OCR + cache mocks as upload tests
  - Done when: all 3 cases pass with `task_always_eager=True`; Redis status key present after task; no broker in CI
  - Est. lines: ~65 impl + ~70 tests
  - Deps: D1, B4

- [ ] **D3** Create `api/routers/async_upload.py` (`POST /upload-slip/async` → 202 + `{task_id, status: "queued"}`) and `api/routers/status.py` (`GET /status/{task_id}` → 200 with state; 404 on unknown; public, no auth).
  - Files: `api/routers/async_upload.py` (new), `api/routers/status.py` (new)
  - Tests: valid upload → 202 + task_id; `GET /status/{id}` pending/done/error; unknown task → 404; min 4 cases; ASGITransport
  - Done when: all 4 cases pass; `result` present when done; `error` present when error; async endpoint auth matches sync endpoint
  - Est. lines: ~50 impl + ~60 tests
  - Deps: D2, C1

- [ ] **D4** `infra/docker-compose.yml`: Add `celery-worker` service (`celery -A api.celery_app worker --loglevel=info --concurrency=4`), sharing same Redis + Postgres network.
  - Files: `infra/docker-compose.yml`
  - Tests: `docker compose config` validates without errors (1 manual check)
  - Done when: compose config valid; worker service uses same env vars as api service; no new infra needed
  - Est. lines: ~20
  - Deps: D1

---

## Phase 5: Block E — Acceptance

- [ ] **E1** Create synthetic dataset fixture (40 comprobantes: 20 unique + 10 exact duplicates + 10 near-duplicates/suspicious) as parametric pytest fixture in `api/tests/fixtures/synthetic_dataset.py`.
  - Files: `api/tests/fixtures/synthetic_dataset.py` (new)
  - Tests: dataset loads without error; 40 records present with correct label distribution
  - Done when: fixture importable; all 3 categories populated with known expected labels
  - Est. lines: ~60
  - Deps: B3

- [ ] **E2** Acceptance smoke tests `api/tests/test_acceptance_2_7.py`: 2.7.1 ≥90% classification accuracy on synthetic dataset; 2.7.2 Capa 1 hit <100ms; 2.7.3 sync pipeline ≤5s; 2.7.4 Celery task <30s; 2.7.5 `POST /validate/{id}` 100% correct in test suite.
  - Files: `api/tests/test_acceptance_2_7.py` (new)
  - Tests: 5 acceptance gates (one per 2.7.x criterion); parametric for 2.7.1
  - Done when: all 5 gates green; coverage does not drop below 70%; `ruff check` passes
  - Est. lines: ~80
  - Deps: E1, D3, C2, C3, B4

- [ ] **E3** Update `PROGRESO.md` (Fase 2 section: status → Completado, link migration + new modules) and create git tag `v0.2.0`.
  - Files: `PROGRESO.md`
  - Tests: `git tag v0.2.0` exists; `alembic upgrade head` + `alembic downgrade -1` run clean on CI
  - Done when: PROGRESO reflects Fase 2 completion; tag pushed; CI green
  - Est. lines: ~15
  - Deps: E2

---

## New Risks Found During Breakdown

1. **`CREATE INDEX CONCURRENTLY` in Alembic** (A0.2): Cannot run inside a transaction. Must verify `alembic.ini` for `transaction_per_migration=false` or use raw `op.execute()` in non-transactional context — confirm before implementing A0.2.
2. **`GET /report` scope** (C3): Design says global counts, but `comprobantes` has `id_usuario`. Confirm with team before implementing — adding a filter later is a breaking API change.
3. **`/status/{task_id}` result shape** (D3): Confirmed as full `ComprobanteResponse` per `TaskStatusResponse` schema, but verify with team before D3 — changes the test contract.
4. **TF-IDF on CI with `scikit-learn`** (B3): First run may be slow due to vectorizer fitting. Pin `scikit-learn>=1.4` and assert fit happens lazily or per-call, not at import time.
