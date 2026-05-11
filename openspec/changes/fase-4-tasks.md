# Tasks: Fase 4 — Plataforma Web de Pago

**Change:** `fase-4-webapp`
**Date:** 2026-05-11
**Status:** Ready for Apply
**Covers:** R-21–R-46 (28 requirements, 43 scenarios)

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated new files | ~50 (13 backend + 37+ frontend) |
| Estimated changed lines | 2,500–3,500 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | PR-A → PR-B → PR-C → PR-D |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-develop |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-develop
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base branch | Notes |
|------|------|-----------|-------------|-------|
| PR-A | Backend JWT auth + token_api_prefix | PR-A | develop | ~15 files, ~650 lines |
| PR-B | Backend web routes (comprobantes + stats) | PR-B | PR-A branch | ~8 files, ~400 lines |
| PR-C | Frontend scaffold + auth + shell | PR-C | develop (parallel) | ~20 files, ~800 lines |
| PR-D | Frontend dashboard + historial + revision | PR-D | PR-C branch | ~20 files, ~900 lines |

> **PR-A and PR-C can land in parallel** (no cross-dependency). PR-B requires PR-A. PR-D requires PR-C (and PR-B for real API calls, but mocks suffice for unit tests).

---

## PR-A — Backend: JWT Auth + token_api_prefix

### Phase A.1: Foundation (config + schemas + migration)

- [x] **4.A.1** Add `fakeredis[aioredis]` to `pyproject.toml` dev deps (group `[tool.poetry.dev-dependencies]`). Verify no conflict with existing `redis` pin.
  - Files: `pyproject.toml`
  - Covers: OQ-3 (resolved)
  - Acceptance: `poetry install` succeeds; `import fakeredis.aioredis` works in test shell

- [x] **4.A.2** Extend `api/config.py` with JWT and CORS env vars: `jwt_secret_key`, `jwt_algorithm="HS256"`, `access_token_expire_minutes=15`, `refresh_token_expire_days=7`, `webapp_origin="http://localhost:3000"`.
  - Files: `api/config.py`, `.env.example`
  - Covers: R-21, R-22, R-25 (JWT_SECRET), CORS tightening
  - Acceptance: `Settings()` instantiates with defaults; no existing test breaks

- [x] **4.A.3** Create Alembic migration `api/alembic/versions/XXXX_add_token_api_prefix.py`: add `token_api_prefix VARCHAR(8) NULL`, create `ix_usuarios_token_api_prefix`, backfill `LEFT(token_api_hash, 8)` for non-NULL rows. Include reversible `downgrade()`.
  - Files: `api/alembic/versions/f3a8e2d1c094_add_token_api_prefix.py`
  - Covers: R-28, R-29
  - Acceptance: `alembic upgrade head` then `alembic downgrade -1` both succeed on a copy of the dev DB

- [x] **4.A.4** Add `token_api_prefix` column to `api/models/usuario.py` ORM model.
  - Files: `api/models/usuario.py`
  - Covers: R-28
  - Acceptance: `Usuario.token_api_prefix` attribute accessible; existing model tests pass

- [x] **4.A.5** Create `api/schemas/auth.py` with `LoginRequest`, `TokenResponse`, `UsuarioPublic` Pydantic models.
  - Files: `api/schemas/auth.py`
  - Covers: R-21, R-24
  - Acceptance: Models import cleanly; `TokenResponse(access_token="x").expires_in == 900`

### Phase A.2: Core Implementation

- [x] **4.A.6** Add `get_redis()` async dependency to `api/database.py`. Returns `aioredis.Redis` from connection pool configured via `settings.redis_url`.
  - Files: `api/database.py`
  - Covers: OQ-2 (resolved), R-26
  - Acceptance: `get_redis()` yields a connected client; no existing `get_session` tests break

- [x] **4.A.7** Create `api/services/jwt_service.py` with all six function signatures from the design: `create_access_token`, `create_refresh_token`, `store_jti`, `rotate_jti`, `revoke_jti`, `is_jti_valid`, `verify_token`. `rotate_jti` MUST use `GETDEL + SET` pipeline for atomicity.
  - Files: `api/services/jwt_service.py`
  - Covers: R-21, R-22, R-23, R-26
  - Acceptance: Unit tests for all 7 functions pass with `FakeRedis()`

- [x] **4.A.8** Create `api/dependencies/auth_jwt.py` exposing `require_jwt` FastAPI dependency. Reads `Authorization: Bearer`, decodes via `jwt_service.verify_token`, loads `Usuario` from DB, raises `HTTPException(401)` on any failure.
  - Files: `api/dependencies/auth_jwt.py`
  - Covers: R-25, R-27
  - Acceptance: Valid token → returns `Usuario`; expired token → 401; missing token → 401

- [x] **4.A.9** Create `api/routers/web_auth.py` with four endpoints: `POST /web/auth/login`, `POST /web/auth/refresh`, `POST /web/auth/logout`, `GET /web/auth/me`. Login sets BOTH `access_token` (httpOnly, 15min) and `refresh_token` (httpOnly, 7d) cookies (OQ-1 resolved). Login MUST run dummy bcrypt on user-not-found for timing safety (S-03).
  - Files: `api/routers/web_auth.py`
  - Covers: R-21, R-22, R-23, R-24, S-01–S-09
  - Acceptance: All S-01–S-09 scenarios pass; S-10 confirms no interference with plugin routes

- [x] **4.A.10** Update `api/dependencies/auth_api_key.py` to use prefix pre-filter: `WHERE token_api_prefix = submitted_key[:8]` before calling `bcrypt.checkpw`. NULL-prefix rows are excluded naturally by the WHERE clause.
  - Files: `api/dependencies/auth_api_key.py`
  - Covers: R-30, S-13, S-14, S-15
  - Acceptance: All 174 existing tests pass; S-13 prefix match works; S-14 NULL row excluded

- [x] **4.A.11** Update `api/main.py`: register `web_auth` router; add `CORSMiddleware` tightened to `settings.webapp_origin` with `allow_credentials=True`.
  - Files: `api/main.py`
  - Covers: R-27 (route namespace), CORS security
  - Acceptance: `/web/auth/login` reachable; CORS preflight returns correct `Allow-Origin`; existing routes unaffected

### Phase A.3: Tests

- [x] **4.A.12** Update `api/tests/conftest.py`: add `redis_client` fixture using `FakeRedis()` (async); add `client_jwt` fixture using `app.dependency_overrides[require_jwt]` pattern parallel to existing `client` fixture.
  - Files: `api/tests/conftest.py`
  - Covers: test infrastructure for all web routes
  - Acceptance: Both fixtures available; no existing fixture broken

- [x] **4.A.13** Create `api/tests/test_jwt_auth.py` covering S-01–S-10 (10 scenarios, ~30 assertions). Must test: valid login, wrong password, non-existent email (timing-safe), valid refresh + JTI rotation, reused JTI → 401, missing cookie → 401, logout + JTI deletion + cookie clear, `GET /me` valid, `GET /me` expired token, plugin route unaffected.
  - Files: `api/tests/test_jwt_auth.py`
  - Covers: S-01–S-10
  - Acceptance: All tests GREEN; 174 + new tests all pass

- [x] **4.A.14** Create `api/tests/test_token_api_prefix.py` covering S-11–S-15 (5 scenarios). Must test: migration idempotency (simulate via model), prefix lookup returns correct user, NULL prefix excluded, all 174 existing tests still pass.
  - Files: `api/tests/test_token_api_prefix.py`
  - Covers: S-11–S-15
  - Acceptance: All tests GREEN; regression gate: 174 tests still pass

**PR-A gate:** `pytest api/tests/` → ALL passing (361 existing + ~40 new)

---

## PR-B — Backend: Web Routes

*Depends on: PR-A merged*

### Phase B.1: Schemas + Routers

- [ ] **4.B.1** Create `api/schemas/web.py` with: `WebComprobanteResponse`, `WebComprobanteDetail`, `WebListResponse` (items, total, page, page_size, has_more), `DecisionRequest` (accion: Literal["aceptar","rechazar"], motivo), `StatsResponse` (total_mes, duplicados_mes, tasa_error).
  - Files: `api/schemas/web.py`
  - Covers: R-39 (list), R-42 (detail), R-44 (decision), R-37 (stats)
  - Acceptance: All Pydantic models instantiate; `WebListResponse.has_more` computed correctly

- [ ] **4.B.2** Create `api/routers/web_stats.py` with `GET /web/stats/` protected by `require_jwt`. Returns org-scoped month-to-date aggregates: `COUNT(*)`, `COUNT(*) WHERE estado_actual='duplicado'`, error rate. Uses org from `usuario.id_organizacion`.
  - Files: `api/routers/web_stats.py`
  - Covers: R-37, S-23, S-24, S-26
  - Acceptance: Returns `StatsResponse`; org-scoped; 500 handled gracefully (S-26)

- [ ] **4.B.3** Create `api/routers/web_comprobantes.py` with three endpoints:
  - `GET /web/comprobantes/` — paginated, org-scoped, accepts `status`, `date_from`, `date_to`, `page`, `page_size` (max 100). Returns `WebListResponse`.
  - `GET /web/comprobantes/{id}` — org-ownership check, raises 403 if foreign org (S-40). Returns full `WebComprobanteDetail` including `texto_extraido`, `imagen_path`.
  - `POST /web/comprobantes/{id}/decision` — org check, calls `apply_transition()` + creates `Validacion(metodo_deteccion="manual")`, returns updated estado.
  - Files: `api/routers/web_comprobantes.py`
  - Covers: R-38, R-39, R-41, R-42, R-44, R-46, S-27–S-32, S-39–S-40, S-38
  - Acceptance: All endpoint contracts satisfied; 403 on foreign org

- [ ] **4.B.4** Register `web_comprobantes` and `web_stats` routers in `api/main.py`.
  - Files: `api/main.py`
  - Covers: R-27 (all `/web/` under `require_jwt`)
  - Acceptance: All four new router groups reachable; existing routes still respond correctly

### Phase B.2: Tests

- [ ] **4.B.5** Create `api/tests/test_web_comprobantes.py` covering S-27–S-32, S-39–S-40, S-38 (~15 tests). Must test: status filter, date range filter, combined filters, pagination, empty results, row detail (S-39), foreign-org 403 (S-40), decision 403 foreign org (S-38).
  - Files: `api/tests/test_web_comprobantes.py`
  - Covers: S-27–S-32, S-38–S-40
  - Acceptance: All tests GREEN using `client_jwt` fixture

- [ ] **4.B.6** Create `api/tests/test_web_stats.py` covering S-23–S-26 (~8 tests). Must test: KPI aggregation by org, zero results (S-24), org isolation, 500 error handling (S-26).
  - Files: `api/tests/test_web_stats.py`
  - Covers: S-23–S-26
  - Acceptance: All tests GREEN; org-scoping verified

**PR-B gate:** `pytest api/tests/` → ALL passing (361 + ~40 PR-A + ~25 PR-B = ~426 tests)

---

## PR-C — Frontend: Scaffold + Auth + Shell

*Depends on: develop baseline (parallel to PR-A)*

### Phase C.1: Project Scaffold

- [ ] **4.C.1** Create `webapp/package.json` with deps: `next@15`, `typescript`, `tailwindcss@^4`, `@shadcn/ui`, `react`, `react-dom`. Dev deps: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@playwright/test`, `@vitejs/plugin-react`.
  - Files: `webapp/package.json`
  - Covers: R-31
  - Acceptance: `npm install` succeeds; no peer-dep warnings

- [ ] **4.C.2** Create `webapp/tsconfig.json` with `"strict": true`, `"paths": { "@/*": ["./src/*"] }`, Next.js defaults.
  - Files: `webapp/tsconfig.json`
  - Covers: R-31 (TypeScript strict)
  - Acceptance: `tsc --noEmit` exits 0 on empty project

- [ ] **4.C.3** Create `webapp/next.config.ts` with rewrites: `/api/:path*` → `http://localhost:8000/:path*`.
  - Files: `webapp/next.config.ts`
  - Covers: R-31 (scaffold), R-35 (API routing)
  - Acceptance: `next build` exits 0

- [ ] **4.C.4** Create `webapp/src/app/globals.css` starting with `@import "tailwindcss";` then `@theme {}` block with ALL M3 color, typography, spacing, radius, and container tokens from design (including `--color-primary`, `--font-sans`, `--spacing-md`, `--radius-lg`, `--spacing-gutter`).
  - Files: `webapp/src/app/globals.css`
  - Covers: R-32, S-22
  - Acceptance: CSS parses without errors; `@theme` block contains all required token variables (S-22)

- [ ] **4.C.5** Initialize shadcn/ui: run `npx shadcn@latest init`, add primitives: `Button`, `Badge`, `Table`, `Card`, `Input`, `Skeleton`. Commit generated files under `webapp/src/components/ui/`.
  - Files: `webapp/src/components/ui/` (generated)
  - Covers: R-31 (shadcn/ui as component base)
  - Acceptance: Each primitive renders in isolation test; no TS errors

### Phase C.2: Auth Layer

- [ ] **4.C.6** Create `webapp/src/lib/auth-context.tsx` with `AuthProvider` and `useAuth` hook. Stores access token in module-level memory variable ONLY — never `localStorage`, never non-HttpOnly cookie. Exposes `{ user, token, login, logout }`. `login()` calls `POST /api/web/auth/login`, stores token in context, reads `refresh_token` cookie implicitly (set by FastAPI). `logout()` calls `POST /api/web/auth/logout`, clears context.
  - Files: `webapp/src/lib/auth-context.tsx`
  - Covers: R-34, S-21
  - Acceptance: `localStorage.getItem("access_token")` returns null after login (S-21); token in context after login

- [ ] **4.C.7** Create `webapp/src/lib/api.ts` exporting `fetchApi<T>`. Attaches `Authorization: Bearer <token>`. On 401: acquires Promise mutex, calls `POST /api/web/auth/refresh` once, releases mutex, retries. Concurrent 401s share one in-flight refresh (S-20).
  - Files: `webapp/src/lib/api.ts`
  - Covers: R-35, S-20
  - Acceptance: Mutex test: 3 concurrent 401s → exactly 1 refresh call; all 3 retries succeed (S-20)

- [ ] **4.C.8** Create `webapp/src/middleware.ts` with matcher `/((?!login|_next|favicon|api).*)`. On unauthenticated (no `refresh_token` cookie): redirect to `/login`. Allow `/login` through unconditionally.
  - Files: `webapp/src/middleware.ts`
  - Covers: R-33, S-17, S-18, S-19
  - Acceptance: No-cookie → 307 `/login` (S-17); cookie present → pass-through (S-18); `/login` → 200 always (S-19)

### Phase C.3: Shell Layout + Login

- [ ] **4.C.9** Create `webapp/src/app/layout.tsx` as root RSC layout: imports Inter font, wraps children in `<AuthProvider>`, applies `globals.css`.
  - Files: `webapp/src/app/layout.tsx`
  - Covers: R-34 (AuthProvider), R-31 (scaffold)
  - Acceptance: `next build` exits 0; Inter font loads in browser

- [ ] **4.C.10** Create `webapp/src/components/layout/Sidebar.tsx` (RSC): navigation links for Dashboard `/`, Historial `/historial`, Revisión `/revision`. Active link highlighted using current path. Uses design tokens for active state.
  - Files: `webapp/src/components/layout/Sidebar.tsx`
  - Covers: R-36
  - Acceptance: Correct `href` on each link; active state class applied to current route

- [ ] **4.C.11** Create `webapp/src/components/layout/Topbar.tsx` (RSC): displays authenticated tenant `nombre`, renders logout button that calls `useAuth().logout()`.
  - Files: `webapp/src/components/layout/Topbar.tsx`
  - Covers: R-36
  - Acceptance: Renders `nombre` from `useAuth().user`; logout button visible

- [ ] **4.C.12** Create `webapp/src/app/(dashboard)/layout.tsx` RSC layout: renders persistent `<Sidebar>` + `<Topbar>` + `{children}`.
  - Files: `webapp/src/app/(dashboard)/layout.tsx`
  - Covers: R-36
  - Acceptance: Layout wraps all dashboard-group pages; Sidebar and Topbar visible

- [ ] **4.C.13** Create `webapp/src/app/login/page.tsx` Client Component: form with `correo` + `contrasena` fields. On submit: calls `useAuth().login()`, shows error message on failure, redirects to `/` on success.
  - Files: `webapp/src/app/login/page.tsx`
  - Covers: S-19 (public access), S-01 (login success triggers redirect)
  - Acceptance: Form renders without auth; submit calls `login()`; error state on 401

### Phase C.4: Tests

- [ ] **4.C.14** Create `webapp/src/lib/__tests__/auth-context.test.tsx` (~5 tests): `login()` stores token in context, `logout()` clears token, `localStorage` never written (S-21), initial state is unauthenticated, context updates trigger re-render.
  - Files: `webapp/src/lib/__tests__/auth-context.test.tsx`
  - Covers: R-34, S-21
  - Test tool: vitest + testing-library

- [ ] **4.C.15** Create `webapp/src/lib/__tests__/api.test.ts` (~8 tests): happy path fetch, 401 → single refresh → retry (S-20), concurrent 401s → one refresh call, non-401 error propagates, post-logout 401 redirects to login.
  - Files: `webapp/src/lib/__tests__/api.test.ts`
  - Covers: R-35, S-20
  - Test tool: vitest with `vi.fn()` mocking `fetch`

- [ ] **4.C.16** Create `webapp/src/__tests__/middleware.test.ts` (~6 tests): no cookie → redirect (S-17), cookie present → pass-through (S-18), `/login` always passes (S-19), `/api/*` bypass, `/_next/*` bypass.
  - Files: `webapp/src/__tests__/middleware.test.ts`
  - Covers: R-33, S-17–S-19
  - Test tool: vitest with Next.js middleware test utilities

- [ ] **4.C.17** Create `webapp/src/components/layout/__tests__/` for `Sidebar.test.tsx` (~5 tests) and `Topbar.test.tsx` (~4 tests): link hrefs, active state, nombre display, logout click handler.
  - Files: `webapp/src/components/layout/__tests__/Sidebar.test.tsx`, `Topbar.test.tsx`
  - Covers: R-36
  - Test tool: vitest + testing-library

- [ ] **4.C.18** Create `webapp/src/app/login/__tests__/page.test.tsx` (~8 tests): renders without auth, form fields present, submit calls `login()`, error state on rejection, redirect on success, no localStorage written.
  - Files: `webapp/src/app/login/__tests__/page.test.tsx`
  - Covers: S-19, S-01 (login form behavior)
  - Test tool: vitest + testing-library

**PR-C gate:** `npm run build` → 0 errors; `npm run test` → ~40 vitest tests GREEN; `tsc --noEmit` → 0 errors; S-16, S-17, S-18, S-19, S-20, S-21, S-22 all covered

---

## PR-D — Frontend: Dashboard + Historial + Revision

*Depends on: PR-C merged; PR-B merged for live API (mocks sufficient for unit tests)*

### Phase D.1: Dashboard

- [ ] **4.D.1** Create `webapp/src/components/dashboard/KpiCard.tsx` (RSC): renders label, numeric value, optional icon. Handles `0` without crash (S-24). Uses `--color-surface-container-low` token for background.
  - Files: `webapp/src/components/dashboard/KpiCard.tsx`
  - Covers: R-37, S-23, S-24
  - Acceptance: Renders `0` without error; renders numeric value with label

- [ ] **4.D.2** Create `webapp/src/components/dashboard/RecentActivity.tsx` (RSC): table with columns folio (truncated UUID), monto, fecha_deposito, estado badge. Status badge uses Tailwind utilities: `bg-green-100/text-green-700` (valido), `bg-red-100/text-red-700` (duplicado), `bg-orange-100/text-orange-700` (sospechoso), `bg-yellow-100/text-yellow-700` (en_revision).
  - Files: `webapp/src/components/dashboard/RecentActivity.tsx`
  - Covers: R-38, S-25
  - Acceptance: Each status maps to correct badge color (S-25); folio truncated to 8 chars

- [ ] **4.D.3** Create `webapp/src/app/(dashboard)/page.tsx` RSC: server-fetches `GET /api/web/stats/` + `GET /api/web/comprobantes/?limit=10` using `access_token` cookie (OQ-1 resolved: cookie readable server-side). Renders three `<KpiCard>` + `<RecentActivity>`. Wraps in error boundary for S-26.
  - Files: `webapp/src/app/(dashboard)/page.tsx`
  - Covers: R-37, R-38, S-23, S-24, S-25, S-26
  - Acceptance: SSR fetch succeeds with cookie; error boundary catches 500 (S-26); 0 values render without crash (S-24)

### Phase D.2: Historial

- [ ] **4.D.4** Create `webapp/src/components/historial/FilterBar.tsx` Client Component: status pills (`pendiente`, `procesado`, `duplicado`, `error`) with multi-select support; date range inputs (date_from / date_to); clearing date removes filter. Emits `onChange({ status[], date_from, date_to })`.
  - Files: `webapp/src/components/historial/FilterBar.tsx`
  - Covers: R-40, R-41, S-27, S-28, S-32
  - Acceptance: Pill toggle updates state; date clear removes param; multiple pills selectable (R-40)

- [ ] **4.D.5** Create `webapp/src/components/historial/HistorialTable.tsx` Client Component: paginated table with columns folio, monto, fecha_deposito, estado badge, acciones. Row click → `router.push('/historial/{id}')`. Renders empty state "Sin resultados" when `items.length === 0` (S-30). Shows pagination controls when `has_more`.
  - Files: `webapp/src/components/historial/HistorialTable.tsx`
  - Covers: R-39, R-42, S-29, S-30, S-31
  - Acceptance: Row click navigates (S-31); empty state renders (S-30); next-page button calls correct URL (S-29)

- [ ] **4.D.6** Create `webapp/src/app/(dashboard)/historial/page.tsx` Client Component: reads `useSearchParams()`, passes `status`, `date_from`, `date_to`, `page` to `fetchApi`. Renders `<FilterBar>` + `<HistorialTable>`. Filter changes update URL params without full navigation.
  - Files: `webapp/src/app/(dashboard)/historial/page.tsx`
  - Covers: R-39, R-40, R-41, S-27, S-28, S-29, S-30, S-31, S-32
  - Acceptance: Filter pill click → URL updates → re-fetch (S-27); combined filters work (S-32)

- [ ] **4.D.7** Create `webapp/src/app/(dashboard)/historial/[id]/page.tsx` RSC: fetches `GET /api/web/comprobantes/{id}` server-side. Renders all comprobante fields (texto_extraido, imagen_path, monto, banco, referencia, fecha_deposito). Shows 403 error state ("Acceso denegado") when API returns 403 (S-40).
  - Files: `webapp/src/app/(dashboard)/historial/[id]/page.tsx`
  - Covers: R-42, R-46, S-39, S-40
  - Acceptance: All fields rendered (S-39); 403 shows error state not crash (S-40)

### Phase D.3: Revision

- [ ] **4.D.8** Create `webapp/src/components/revision/OcrFields.tsx`: labeled key-value rows for monto, banco, referencia, fecha_deposito parsed from `texto_extraido`. Renders `—` for null values gracefully.
  - Files: `webapp/src/components/revision/OcrFields.tsx`
  - Covers: R-43, S-33
  - Acceptance: All four fields rendered; null handled without crash

- [ ] **4.D.9** Create `webapp/src/components/revision/VoucherViewer.tsx`: renders `<img src={imagen_path} alt="comprobante">` with correct URL. Includes loading skeleton while image loads.
  - Files: `webapp/src/components/revision/VoucherViewer.tsx`
  - Covers: R-43, S-33
  - Acceptance: `<img>` present with correct `src` (S-33); skeleton shown during load

- [ ] **4.D.10** Create `webapp/src/components/revision/DuplicatePanel.tsx` Client Component: renders candidates table with `score_similitud` as percentage and link to `id_comprobante_original`. Renders **Aceptar** and **Rechazar** buttons. On click: optimistically updates status badge to `valido`/`duplicado` (S-35), calls `POST /api/web/comprobantes/{id}/decision`, reverts badge + shows error message on failure (S-36).
  - Files: `webapp/src/components/revision/DuplicatePanel.tsx`
  - Covers: R-44, R-45, S-34, S-35, S-36
  - Acceptance: Optimistic update immediate (S-35); API failure reverts state (S-36); candidates table shows 2 rows in S-34 scenario

- [ ] **4.D.11** Create `webapp/src/app/(dashboard)/revision/[id]/page.tsx` Client Component: fetches comprobante data, renders 7/5 column split — left pane `<VoucherViewer>` + `<OcrFields>`, right pane `<DuplicatePanel>`. Auth guard: middleware already covers this (S-37).
  - Files: `webapp/src/app/(dashboard)/revision/[id]/page.tsx`
  - Covers: R-43, R-44, R-45, S-33, S-34, S-35, S-36, S-37
  - Acceptance: 7/5 grid layout; both panes render; S-37 covered by middleware (not duplicated here)

### Phase D.4: Tests + E2E

- [ ] **4.D.12** Create vitest component tests for dashboard components (~14 tests total):
  - `KpiCard.test.tsx`: renders 0 (S-24), renders value, renders label (3 tests)
  - `RecentActivity.test.tsx`: badge colors per status (S-25), all 4 status variants, truncated folio (6 tests)
  - `page.test.tsx` (dashboard): error boundary on 500 (S-26), KPI cards render, recent activity renders (5 tests)
  - Files: `webapp/src/components/dashboard/__tests__/`, `webapp/src/app/(dashboard)/__tests__/`
  - Covers: S-23, S-24, S-25, S-26

- [ ] **4.D.13** Create vitest component tests for historial components (~24 tests total):
  - `FilterBar.test.tsx`: pill toggle (S-27), date range (S-28), combined (S-32), date clear, multi-select (10 tests)
  - `HistorialTable.test.tsx`: row click (S-31), empty state (S-30), badge colors, pagination next (8 tests)
  - `historial/page.test.tsx`: URL params sync, re-fetch on filter (6 tests)
  - Files: `webapp/src/components/historial/__tests__/`, `webapp/src/app/(dashboard)/historial/__tests__/`
  - Covers: S-27–S-32

- [ ] **4.D.14** Create vitest component tests for revision components (~18 tests total):
  - `OcrFields.test.tsx`: all fields rendered, null graceful (5 tests)
  - `VoucherViewer.test.tsx`: img src correct, skeleton shown (3 tests)
  - `DuplicatePanel.test.tsx`: optimistic update (S-35), revert on failure (S-36), candidates table (S-34), 2 rows shown (10 tests)
  - Files: `webapp/src/components/revision/__tests__/`
  - Covers: S-33, S-34, S-35, S-36

- [ ] **4.D.15** Create Playwright E2E tests in `webapp/e2e/` (~10 tests):
  - `auth.spec.ts`: login → dashboard redirect (S-17, S-18, S-19), unauthenticated → /login (S-17)
  - `dashboard.spec.ts`: 3 KPI cards visible (S-23), recent activity table has rows (S-25)
  - `historial.spec.ts`: pill click → URL param + filtered results (S-27), date range filter (S-28), next page (S-29)
  - `revision.spec.ts`: navigate to /revision/[id], click Aceptar, badge turns green (S-35)
  - Files: `webapp/e2e/auth.spec.ts`, `webapp/e2e/dashboard.spec.ts`, `webapp/e2e/historial.spec.ts`, `webapp/e2e/revision.spec.ts`
  - Covers: S-17–S-19, S-23, S-25, S-27–S-29, S-35
  - Acceptance: All 10 Playwright tests pass against running backend + frontend

**PR-D gate:** `npm run test` → ~90+ vitest GREEN; `npx playwright test` → ~10 E2E GREEN; `next build` → 0 errors; combined test total ≥ 500

---

## Task Summary by PR

| PR | Tasks | New Files | Scenarios | Test target |
|----|-------|-----------|-----------|-------------|
| PR-A | 14 (4.A.1–4.A.14) | 7 backend | S-01–S-15 | +~40 Python |
| PR-B | 6 (4.B.1–4.B.6) | 5 backend | S-23–S-32, S-38–S-40 | +~25 Python |
| PR-C | 18 (4.C.1–4.C.18) | ~20 frontend | S-16–S-22 | ~40 vitest |
| PR-D | 15 (4.D.1–4.D.15) | ~17 frontend | S-23–S-40 (FE) | ~50 vitest + 10 E2E |
| **Total** | **53** | **~49** | **43** | **~501 combined** |

## Requirement Coverage Matrix

| Requirement | PR | Tasks |
|------------|-----|-------|
| R-21 Login JWT | A | 4.A.2, 4.A.5, 4.A.7, 4.A.9, 4.A.13 |
| R-22 Refresh rotation | A | 4.A.7, 4.A.9, 4.A.13 |
| R-23 Logout + JTI revoke | A | 4.A.7, 4.A.9, 4.A.13 |
| R-24 /me endpoint | A | 4.A.8, 4.A.9, 4.A.13 |
| R-25 require_jwt dep | A | 4.A.8 |
| R-26 Redis JTI store | A | 4.A.6, 4.A.7 |
| R-27 /web/ namespace | A | 4.A.11 |
| R-28 token_api_prefix col | A | 4.A.3, 4.A.4 |
| R-29 Backfill migration | A | 4.A.3 |
| R-30 Prefix pre-filter | A | 4.A.10 |
| R-31 Next.js scaffold | C | 4.C.1–4.C.3 |
| R-32 globals.css tokens | C | 4.C.4 |
| R-33 Middleware | C | 4.C.8 |
| R-34 AuthProvider + memory | C | 4.C.6 |
| R-35 fetchApi + mutex | C | 4.C.7 |
| R-36 Shell layout | C | 4.C.10–4.C.12 |
| R-37 Dashboard KPIs | D | 4.D.1, 4.D.3 |
| R-38 Recent activity | D | 4.D.2, 4.D.3 |
| R-39 Paginated historial | D | 4.D.5, 4.D.6 |
| R-40 Status filter pills | D | 4.D.4 |
| R-41 Date range picker | D | 4.D.4 |
| R-42 Row click + detail | D | 4.D.5, 4.D.7 |
| R-43 Review layout 7/5 | D | 4.D.8, 4.D.9, 4.D.11 |
| R-44 Decision endpoint | B | 4.B.3 |
| R-44 Decision UI | D | 4.D.10 |
| R-45 Optimistic UI | D | 4.D.10 |
| R-46 Comprobante detail | B | 4.B.3 |
| R-14 (updated) prefix | A | 4.A.10 |
