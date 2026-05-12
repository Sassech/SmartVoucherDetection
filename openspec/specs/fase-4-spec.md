# Fase 4 — Plataforma Web de Pago — Delta Spec

**Change:** `fase-4-webapp`
**Date:** 2026-05-11
**Phase:** ARCHIVED — Verified 2026-05-12
**Mode:** openspec
**Continues from:** fase-3-spec.md (R-20 was last; Fase 4 starts at R-21)
**Test Results:** Python 425/426 ✅ | Vitest 90/90 ✅ | Playwright 10 specs ✅ | Total: 515 tests

---

## Capability: jwt-auth

### Requirements

#### R-21: Login Endpoint Issues JWT Token Pair

`POST /web/auth/login` MUST accept `{ correo, contrasena }`, validate the user exists and `bcrypt.checkpw` passes, and return `{ access_token, token_type: "bearer", expires_in }` in the response body plus a `Set-Cookie: refresh_token=<jti>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800` header. The access token MUST be a signed JWT (HS256) with claims `{ sub, org, rol, jti, exp }` and a 15-minute TTL.

#### R-22: Refresh Endpoint Rotates Token Pair

`POST /web/auth/refresh` MUST read the `refresh_token` HttpOnly cookie, validate the JTI exists in Redis (key `jti:<uuid>`, TTL = 7d), issue a new access token and a new refresh JTI, atomically delete the old JTI and write the new one, and return a new access token. Used or expired JTIs MUST return 401.

#### R-23: Logout Endpoint Invalidates JTI

`POST /web/auth/logout` MUST delete the `jti:<uuid>` key from Redis and clear the `refresh_token` cookie by setting `Max-Age=0`. The endpoint MUST require a valid `Authorization: Bearer <access_token>` header and return 200 on success.

#### R-24: Me Endpoint Returns Authenticated User

`GET /web/auth/me` MUST be protected by `require_jwt` and return `{ id_usuario, correo, nombre, rol, id_organizacion }` for the authenticated user. Deleted or suspended users MUST return 401.

#### R-25: require_jwt Dependency

`api/dependencies/auth_jwt.py` MUST expose a FastAPI dependency `require_jwt` that reads `Authorization: Bearer <token>`, decodes and verifies the JWT signature using `JWT_SECRET`, checks `exp`, and returns the decoded payload. It MUST NOT touch `require_api_key` or any plugin route. Missing, malformed, or expired tokens MUST raise `HTTPException(401)`.

#### R-26: Redis JTI Store

Refresh tokens MUST be stored in Redis as `jti:<uuid> → id_usuario` with TTL = 604800 seconds (7 days). The store MUST be the sole source of truth for refresh token validity. A JTI MUST be consumed (deleted) on first use during refresh.

#### R-27: /web/ Route Namespace Protection

All routes under the `/web/` prefix (except `/web/auth/login` and `/web/auth/refresh`) MUST declare `Depends(require_jwt)`. Existing plugin routes (`/upload-slip`, `/history`, `/validate`, `/report`, `/health`) MUST remain under `require_api_key` with zero changes.

### Scenarios

#### S-01: Valid credentials return access token and set refresh cookie

- GIVEN a `Usuario` with `correo=test@example.com` and a valid `contrasena_hash` exists
- WHEN `POST /web/auth/login` is called with `{ correo, contrasena }` matching the hash
- THEN the response is HTTP 200 with `{ access_token, token_type: "bearer", expires_in: 900 }`
- AND the response sets an `HttpOnly; Secure; SameSite=Strict` cookie named `refresh_token`

#### S-02: Wrong password returns 401

- GIVEN a `Usuario` exists with `correo=test@example.com`
- WHEN `POST /web/auth/login` is called with the correct email but wrong password
- THEN the response is HTTP 401 with `{"detail": "Invalid credentials"}`
- AND no cookie is set

#### S-03: Non-existent email returns 401 (timing-safe)

- GIVEN no `Usuario` exists with `correo=ghost@example.com`
- WHEN `POST /web/auth/login` is called with that email
- THEN the response is HTTP 401 with `{"detail": "Invalid credentials"}`
- AND the response time is indistinguishable from the wrong-password case

#### S-04: Valid refresh cookie issues new access token and rotates JTI

- GIVEN a valid `refresh_token` cookie with JTI `abc-123` exists in Redis
- WHEN `POST /web/auth/refresh` is called
- THEN the response is HTTP 200 with a new `access_token`
- AND Redis key `jti:abc-123` is deleted
- AND a new `jti:<new-uuid>` key is written to Redis

#### S-05: Reused refresh JTI returns 401

- GIVEN JTI `abc-123` was already consumed (deleted from Redis)
- WHEN `POST /web/auth/refresh` is called with cookie containing `abc-123`
- THEN the response is HTTP 401 with `{"detail": "Invalid or expired refresh token"}`

#### S-06: Missing refresh cookie returns 401

- GIVEN no `refresh_token` cookie is present in the request
- WHEN `POST /web/auth/refresh` is called
- THEN the response is HTTP 401

#### S-07: Logout invalidates JTI and clears cookie

- GIVEN a valid access token with JTI `xyz-789` and corresponding Redis key `jti:xyz-789`
- WHEN `POST /web/auth/logout` is called with `Authorization: Bearer <access_token>`
- THEN the response is HTTP 200
- AND Redis key `jti:xyz-789` is deleted
- AND the response sets `Set-Cookie: refresh_token=; Max-Age=0`

#### S-08: GET /web/auth/me returns user info for valid JWT

- GIVEN a valid access token with `sub=user-uuid`, `org=org-uuid`, `rol=operador`
- WHEN `GET /web/auth/me` is called with `Authorization: Bearer <token>`
- THEN the response is HTTP 200 with `{ id_usuario, correo, nombre, rol, id_organizacion }`

#### S-09: GET /web/auth/me with expired token returns 401

- GIVEN an access token whose `exp` claim is in the past
- WHEN `GET /web/auth/me` is called
- THEN the response is HTTP 401 with `{"detail": "Token expired"}`

#### S-10: Plugin route unaffected by JWT changes

- GIVEN a request to `POST /upload-slip` with a valid `X-API-Key` and no JWT
- WHEN the endpoint is called after Fase 4 is deployed
- THEN the response is HTTP 200 (or the expected pipeline response)
- AND `require_jwt` is never invoked for this route

---

## Capability: token_api_prefix

### Requirements

#### R-28: token_api_prefix Column Migration

The `usuarios` table MUST gain a nullable `VARCHAR(8)` column `token_api_prefix` via an Alembic migration. The migration MUST include a UNIQUE-supporting B-tree index `ix_usuarios_token_api_prefix`. The migration MUST be reversible (`downgrade` drops the column and index).

#### R-29: Backfill Existing Rows

The migration's `upgrade()` MUST backfill `token_api_prefix` for all existing `usuarios` rows where `token_api_hash IS NOT NULL` by setting `token_api_prefix = LEFT(token_api_hash, 8)`. Rows with `token_api_hash IS NULL` MUST remain `NULL`.

#### R-30: require_api_key Uses Prefix for Narrowed Lookup

`require_api_key` MUST use `token_api_prefix` to pre-filter candidates: query `usuarios WHERE token_api_prefix = submitted_key[:8]` before running `bcrypt.checkpw`. The full O(n) bcrypt scan over all users MUST NOT be performed when `token_api_prefix` is populated.

### Scenarios

#### S-11: Migration applies cleanly on existing DB

- GIVEN the database has all Fase 1–3 migrations applied and has existing `usuarios` rows with `token_api_hash` populated
- WHEN `alembic upgrade head` is run
- THEN `token_api_prefix` column exists on `usuarios`
- AND `ix_usuarios_token_api_prefix` index exists
- AND all rows with `token_api_hash IS NOT NULL` have `token_api_prefix = token_api_hash[:8]`

#### S-12: Migration rollback drops column cleanly

- GIVEN the Fase 4 migration is applied
- WHEN `alembic downgrade -1` is run
- THEN the `token_api_prefix` column is removed
- AND the `ix_usuarios_token_api_prefix` index is removed
- AND all other columns on `usuarios` are unchanged

#### S-13: Prefix-narrowed lookup returns correct Usuario

- GIVEN a `Usuario` with `token_api_hash = bcrypt("mykey123...")` and `token_api_prefix = "mykey123"`
- WHEN `require_api_key` processes `X-API-Key: mykey123...`
- THEN only the row(s) with `token_api_prefix = "mykey123"` are queried
- AND `bcrypt.checkpw` returns `True` for the matching row

#### S-14: NULL prefix rows are not returned by prefix query

- GIVEN a `Usuario` row where `token_api_hash IS NULL` (webapp-only user) and `token_api_prefix IS NULL`
- WHEN `require_api_key` processes any API key
- THEN that row is excluded from bcrypt comparison candidates

#### S-15: MODIFIED — R-14 behavior preserved with prefix optimization

- GIVEN `require_api_key` now uses prefix filtering
- WHEN called with a valid `X-API-Key` whose prefix matches
- THEN the `Usuario` is resolved and returned exactly as before
- AND all 361 Fase 1–3 tests continue passing

---

## Capability: webapp-shell

### Requirements

#### R-31: Next.js 15 Project Scaffold

The `webapp/` directory MUST contain a Next.js 15 App Router project with TypeScript strict mode (`"strict": true` in `tsconfig.json`), Tailwind 4 CSS-first config (no `tailwind.config.js`), and `shadcn/ui` as component base. The project MUST build with `next build` producing zero TypeScript errors.

#### R-32: Design System Tokens in globals.css

`webapp/src/app/globals.css` MUST contain a `@theme {}` block with all M3 color, typography, spacing, border-radius, and container tokens from `DESIGN.md`. The file MUST start with `@import "tailwindcss";`.

#### R-33: Route Protection Middleware

`webapp/src/middleware.ts` MUST intercept all routes matching `/(dashboard)/(.*)` and redirect to `/login` if no valid access token is present in memory or no refresh cookie is available. The middleware MUST allow public access to `/login` and `/web/auth/(.*)` without interception.

#### R-34: Auth Context and Token Storage

The webapp MUST store the access token exclusively in React context (module-level memory variable) — never in `localStorage` or non-HttpOnly cookies. The refresh token MUST be stored only in the HttpOnly `Secure` cookie set by FastAPI. An `AuthProvider` component MUST expose `{ user, login, logout, token }` to the component tree.

#### R-35: Typed Fetch Client with Refresh Mutex

`webapp/src/lib/api.ts` MUST export a `fetchApi<T>` function that: attaches `Authorization: Bearer <access_token>` to all requests; on receiving HTTP 401, acquires a Promise-based mutex, calls `POST /web/auth/refresh` once, releases the mutex, and retries the original request. Concurrent 401s MUST share a single in-flight refresh call (not trigger N parallel refreshes).

#### R-36: Shell Layout with Sidebar and Topbar

`webapp/src/app/(dashboard)/layout.tsx` MUST render a persistent sidebar with navigation links (Dashboard, Historial, Revisión) and a topbar displaying the authenticated tenant's `nombre`. The layout MUST be a React Server Component.

### Scenarios

#### S-16: next build completes with zero TypeScript errors

- GIVEN the `webapp/` scaffold is created per R-31
- WHEN `next build` is run
- THEN the build exits with code 0
- AND no TypeScript compilation errors appear in stdout

#### S-17: Unauthenticated request to /dashboard redirects to /login

- GIVEN no refresh cookie and no access token in memory
- WHEN a browser navigates to `/` (dashboard root)
- THEN middleware redirects to `/login`
- AND the dashboard page is not rendered

#### S-18: Authenticated request to /dashboard passes middleware

- GIVEN a valid refresh cookie is present
- WHEN a browser navigates to `/`
- THEN middleware allows the request through
- AND the dashboard page renders

#### S-19: /login page is publicly accessible

- GIVEN no authentication
- WHEN a browser navigates to `/login`
- THEN the login page renders without redirect

#### S-20: api.ts refresh mutex prevents parallel refresh calls

- GIVEN an expired access token and 3 concurrent requests that all receive HTTP 401
- WHEN all 3 requests trigger the refresh logic
- THEN `POST /web/auth/refresh` is called exactly once
- AND all 3 original requests are retried with the new access token

#### S-21: Access token is never written to localStorage

- GIVEN a user logs in successfully
- WHEN the login flow completes
- THEN `localStorage.getItem("access_token")` returns `null`
- AND the access token exists only in React context

#### S-22: globals.css contains @theme block with M3 tokens

- GIVEN the webapp scaffold is created per R-32
- WHEN `globals.css` is parsed
- THEN a `@theme {}` block is present containing `--color-primary`, `--font-sans`, `--spacing-md`, and `--radius-lg`

---

## Capability: webapp-dashboard

### Requirements

#### R-37: Dashboard RSC Page with Org-Scoped KPI Cards

The `/` (dashboard root) page MUST be a React Server Component that fetches org-scoped data from `GET /web/stats/` using the authenticated user's JWT. It MUST render three KPI cards: comprobantes procesados (current month), duplicados detectados (current month), and tasa de error (%). Data MUST be scoped to `id_organizacion` from the JWT claims.

#### R-38: Recent Activity Table

The dashboard page MUST render a recent activity table showing the last 10 comprobantes fetched from `GET /web/comprobantes/?limit=10`. Each row MUST display: folio (truncated UUID), monto, fecha_deposito, and estado with a color-coded badge matching the status color system.

### Scenarios

#### S-23: Dashboard renders KPI cards with org-scoped data

- GIVEN a user with `id_organizacion = org-A` is authenticated
- WHEN `GET /` is loaded server-side
- THEN `GET /web/stats/` is called with `Authorization: Bearer <token>` scoped to `org-A`
- AND three KPI cards render with numeric values

#### S-24: KPI cards show zero when no data exists for the org

- GIVEN the org has no comprobantes this month
- WHEN the dashboard loads
- THEN all KPI cards show `0` (not an error or empty state crash)

#### S-25: Recent activity table shows last 10 rows with status badges

- GIVEN `GET /web/comprobantes/?limit=10` returns 10 comprobantes with mixed states
- WHEN the dashboard renders
- THEN a table with 10 rows is displayed
- AND each row has a status badge with the correct color class (`bg-green-100`, `bg-red-100`, etc.)

#### S-26: API error on stats fetch shows graceful error state

- GIVEN `GET /web/stats/` returns HTTP 500
- WHEN the dashboard page renders server-side
- THEN an error boundary or fallback UI is shown instead of an unhandled exception
- AND no stack trace is exposed to the browser

---

## Capability: webapp-historial

### Requirements

#### R-39: Paginated Comprobantes Table with Filters

`/historial` MUST be a Client Component (`"use client"`) that fetches `GET /web/comprobantes/` with query params `status`, `date_from`, `date_to`, and `page`. Results MUST be displayed in a paginated table with columns: folio, monto, fecha_deposito, estado (badge), acciones.

#### R-40: Status Filter Pills

The historial page MUST render filter pills for statuses: `pendiente`, `procesado`, `duplicado`, `error`. Selecting a pill MUST update the query and re-fetch without full page navigation. Multiple pills MAY be selected simultaneously.

#### R-41: Date Range Picker

The historial page MUST include a date range picker (date_from / date_to) that filters `fecha_deposito`. Clearing the date range MUST remove the filter and re-fetch all records.

#### R-42: Row Click Navigates to Detail View

Clicking any table row MUST navigate to `/historial/[id]` where `id` is the `id_comprobante`. The detail view MUST display all comprobante fields including `texto_extraido` and `imagen_path`.

#### R-46: Comprobante Detail Endpoint

`GET /web/comprobantes/{id}` MUST be protected by `require_jwt`, verify the comprobante belongs to the authenticated user's `id_organizacion`, and return the full comprobante record including `texto_extraido`, `imagen_path`, `referencia`, `monto`, `banco`, `fecha_deposito`, `numero_operacion`, and `estado_actual`. Comprobantes belonging to a different org MUST return 403.

### Scenarios

#### S-27: Status pill filter re-fetches with correct query param

- GIVEN the historial page is loaded with no active filters
- WHEN the user clicks the `duplicado` pill
- THEN `GET /web/comprobantes/?status=duplicado` is called
- AND only duplicado records appear in the table

#### S-28: Date range filter applies correctly

- GIVEN `date_from=2026-01-01` and `date_to=2026-01-31`
- WHEN the user sets the date range picker to January 2026
- THEN `GET /web/comprobantes/?date_from=2026-01-01&date_to=2026-01-31` is called
- AND only comprobantes with `fecha_deposito` in January appear

#### S-29: Pagination navigates to next page

- GIVEN 50 comprobantes exist and the default page size is 20
- WHEN the user clicks the "Next Page" control
- THEN `GET /web/comprobantes/?page=2` is called
- AND records 21–40 are displayed

#### S-30: Empty results show empty state (not error)

- GIVEN `GET /web/comprobantes/?status=duplicado` returns `{ items: [], total: 0 }`
- WHEN the historial page renders
- THEN an empty state message is shown (e.g., "Sin resultados")
- AND no table rows or pagination controls are rendered

#### S-31: Row click navigates to /historial/[id]

- GIVEN a comprobante row with `id_comprobante = "abc-123"` is displayed
- WHEN the user clicks the row
- THEN the browser navigates to `/historial/abc-123`

#### S-32: Combined status + date filter applies both params

- GIVEN active `status=procesado` pill and `date_from=2026-03-01`
- WHEN the page renders
- THEN `GET /web/comprobantes/?status=procesado&date_from=2026-03-01` is called
- AND results match both constraints

#### S-39: Detail view fetches comprobante by id

- GIVEN a user navigates to `/historial/abc-123` and the comprobante belongs to the user's org
- WHEN the page loads via `GET /web/comprobantes/abc-123`
- THEN the response is HTTP 200 with the full comprobante record
- AND all fields (texto_extraido, imagen_path, monto, banco, referencia, fecha_deposito) are rendered

#### S-40: Detail view for foreign-org comprobante returns 403

- GIVEN a user from `org-A` navigates to `/historial/xyz-789` where that comprobante belongs to `org-B`
- WHEN the page calls `GET /web/comprobantes/xyz-789`
- THEN the API returns HTTP 403 with `{"detail": "Access denied"}`
- AND the detail page renders an access-denied error state

---

## Capability: webapp-revision

### Requirements

#### R-43: Side-by-Side Review Layout

`/revision/[id]` MUST render a 7/5 column split layout. The left pane (7 cols) MUST display the original voucher image (`imagen_path`) and OCR extracted fields (`texto_extraido` parsed). The right pane (5 cols) MUST display a table of duplicate candidates from `validaciones` with `score_similitud` and the `id_comprobante_original` reference.

#### R-44: Decision Actions via POST /web/comprobantes/{id}/decision

The right pane MUST render two action buttons: **Aceptar** (marks comprobante as `valido`) and **Rechazar** (marks as `duplicado`). Clicking either MUST call `POST /web/comprobantes/{id}/decision` with `{ decision: "aceptar" | "rechazar" }` using the authenticated JWT. The backend endpoint MUST be protected by `require_jwt` and MUST verify the comprobante belongs to the authenticated user's org before applying the state change.

#### R-45: Optimistic UI on Decision

Upon clicking a decision button, the UI MUST optimistically update the status badge to the expected state (green for Aceptar, red for Rechazar) before the API response arrives. If the API call fails, the UI MUST revert to the previous state and display an error message.

### Scenarios

#### S-33: Review page renders voucher image and OCR fields

- GIVEN `/revision/abc-123` is loaded and `GET /web/comprobantes/abc-123` returns a comprobante with `imagen_path` and `texto_extraido`
- WHEN the page renders
- THEN the left pane displays an `<img>` with the voucher image URL
- AND OCR fields (monto, banco, referencia, fecha) are shown in labeled rows

#### S-34: Right pane lists duplicate candidates with similarity score

- GIVEN `validaciones` has 2 rows for `id_comprobante = abc-123` with `score_similitud = 0.97` and `0.85`
- WHEN the review page renders
- THEN the right pane table shows 2 candidate rows with similarity percentages
- AND each row links to the original comprobante

#### S-35: Aceptar triggers optimistic update then API call

- GIVEN the review page is loaded for comprobante `abc-123` in `sospechoso` state
- WHEN the user clicks **Aceptar**
- THEN the status badge immediately updates to `valido` (green)
- AND `POST /web/comprobantes/abc-123/decision` is called with `{ decision: "aceptar" }`

#### S-36: API failure on decision reverts optimistic update

- GIVEN the user clicks **Aceptar** and `POST /web/comprobantes/abc-123/decision` returns HTTP 500
- WHEN the API call completes
- THEN the status badge reverts to `sospechoso`
- AND an error message is displayed to the user

#### S-37: Unauthorized user cannot access /revision/[id]

- GIVEN a request to `/revision/abc-123` with no valid session
- WHEN the middleware evaluates the request
- THEN the user is redirected to `/login`
- AND the review page is not rendered

#### S-38: Decision for comprobante belonging to different org returns 403

- GIVEN a user from `org-A` attempts to POST `/web/comprobantes/xyz-789/decision` where `xyz-789` belongs to `org-B`
- WHEN the request reaches the API
- THEN the response is HTTP 403 with `{"detail": "Access denied"}`
- AND no state change is applied to the comprobante

---

## MODIFIED Capability: api-key-auth

> **Reference:** `openspec/specs/fase-3-spec.md` — CAP-2: fastapi-api-key-auth, Requirements R-14 to R-18

### Requirement R-14: require_api_key FastAPI Dependency (Updated)

`api/dependencies/auth_api_key.py` MUST expose a FastAPI dependency `require_api_key` that reads the `X-API-Key` request header, uses `token_api_prefix = submitted_key[:8]` to query only `usuarios WHERE token_api_prefix = <prefix>`, then runs `bcrypt.checkpw(plain_key, token_api_hash)` on the narrowed candidate set, and returns the `Usuario` object.
(Previously: queried ALL usuarios and ran bcrypt.checkpw over all rows — O(n) full scan)

#### Scenario: Valid API key resolves to Usuario object

- GIVEN a request with `X-API-Key: <valid_plain_key>` where a `Usuario` row has matching `token_api_prefix` and `bcrypt.checkpw(plain_key, token_api_hash) == True`
- WHEN `require_api_key` is resolved by FastAPI
- THEN the dependency returns the `Usuario` object
- AND the endpoint receives `id_usuario = usuario.id_usuario`

#### Scenario: Authenticated upload uses resolved id_usuario not SYSTEM_USER_ID

- GIVEN a valid API key resolves to `usuario.id_usuario = uuid-X`
- WHEN `POST /upload-slip` is called
- THEN the created `Comprobante` row has `id_usuario = uuid-X`
- AND `SYSTEM_USER_ID` is never used

#### Scenario: Prefix mismatch skips bcrypt entirely

- GIVEN `submitted_key[:8] = "XXXXXXXX"` and no `usuarios` row has `token_api_prefix = "XXXXXXXX"`
- WHEN `require_api_key` is resolved
- THEN the response is HTTP 401 with `{"detail": "Invalid API key"}`
- AND `bcrypt.checkpw` is never called (zero bcrypt overhead)

---

## Summary

| Capability | Requirements | R Range | Scenarios |
|------------|-------------|---------|-----------|
| jwt-auth | 7 | R-21 – R-27 | S-01 – S-10 (10) |
| token_api_prefix | 3 | R-28 – R-30 | S-11 – S-15 (5) |
| webapp-shell | 6 | R-31 – R-36 | S-16 – S-22 (7) |
| webapp-dashboard | 2 | R-37 – R-38 | S-23 – S-26 (4) |
| webapp-historial | 5 | R-39 – R-42, R-46 | S-27 – S-32, S-39 – S-40 (8) |
| webapp-revision | 3 | R-43 – R-45 | S-33 – S-38 (6) |
| api-key-auth (MODIFIED) | 1 delta | R-14 updated | 3 (1 new, 2 carried) |
| **Total** | **27 new + 1 modified = 28** | **R-21 – R-46** | **43 scenarios** |

### Applied Spec Decisions

| Decision | Resolution |
|----------|-----------|
| SD-1 | Fase 4 starts at R-21 (R-19/R-20 belong to fase-3 github-actions). Gap: R-43–R-45 skip R-46 for revision; R-46 assigned to historial detail per SD-4. |
| SD-2 | All web routes use `/web/comprobantes/` and `/web/stats/`. Plugin routes (`/history`, `/report`) remain unchanged under `require_api_key`. |
| SD-3 | `POST /web/comprobantes/{id}/decision` explicitly covered in R-44 (decision actions), including backend protection requirements. |
| SD-4 | `GET /web/comprobantes/{id}` added as R-46 under webapp-historial with org-scoping and 403 guard. |
