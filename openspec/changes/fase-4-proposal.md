# Proposal: Fase 4 — Plataforma Web de Pago

**Change:** `fase-4-webapp`
**Date:** 2026-05-11
**Status:** DRAFT

---

## Intent

Phases 1–3 delivered a complete backend + WP plugin for automated voucher detection. However, operators and auditors have no native web interface — they must use the WordPress admin panel or raw API calls. Fase 4 delivers the first user-facing web platform: JWT-authenticated, multi-tenant, with dashboard, history, and side-by-side review. This transforms SmartVoucherDetection from a headless API into a product operators can actually use.

---

## Scope

### In Scope

- **JWT auth endpoints** — `POST /auth/login` + `POST /auth/refresh` on FastAPI; access token (15 min) + refresh token (7d, HttpOnly cookie)
- **`require_jwt` dependency** — new FastAPI dep coexisting with `require_api_key` (plugin routes untouched)
- **`/web/` route namespace** — JWT-protected mirrors of history/report/validate; plugin routes stay as-is
- **`token_api_prefix` migration** — deferred from Fase 3; indexed `VARCHAR(8)` column on `usuarios`
- **Next.js 15 scaffold** — App Router, TypeScript strict, Tailwind 4 (CSS-first, no `tailwind.config.js`)
- **Tailwind 4 design system** — M3 tokens from `DESIGN.md` → `@theme` block in `globals.css`
- **Login page** — credential form + token refresh interceptor + route protection middleware
- **Dashboard page** — KPI cards + recent activity (RSC, org-scoped)
- **Historial page** — table with date range / status filters, pagination (Client Component)
- **Side-by-side duplicate review** — 7/5 col layout, OCR fields vs image, decision actions (approve / flag / reject)
- **Multi-tenant scoping** — `/web/history`, `/web/report`, `/web/validate/{id}` filter by `id_organizacion`
- **CORS tighten** — explicit `allow_origins` + `allow_credentials=True` for Next.js origin

### Out of Scope (deferred to Fase 5)

- Stripe subscriptions / billing webhooks
- Upload page in webapp (WP plugin covers production uploads)
- User management (invite, role change)
- Export CSV / XLSX
- Refresh token blacklist (DB-backed; Redis JTI sufficient for Fase 4)
- Nginx / TLS / prod infra config
- PHPUnit for plugin

---

## Capabilities

### New Capabilities

- `jwt-auth`: FastAPI JWT auth layer — login, refresh, `require_jwt` dep, JTI store in Redis
- `webapp-shell`: Next.js 15 project scaffold — layout, auth middleware, design system, shared components
- `webapp-dashboard`: Dashboard page — org-scoped KPI cards + recent activity (RSC)
- `webapp-historial`: History page — filterable/paginated comprobantes table (Client Component)
- `webapp-revision`: Side-by-side duplicate review page — OCR diff + decision actions

### Modified Capabilities

- `api-key-auth` (existing, `fase-3-spec.md`): adds `token_api_prefix` indexed column via new Alembic migration — no behavior change, pure performance optimization

---

## Approach

### FastAPI — Dual Auth, No Breaking Changes

- Add `api/routers/auth.py` (`/auth/login`, `/auth/refresh`) and `api/dependencies/auth_jwt.py`
- All new webapp routes live under `/web/` prefix with `require_jwt`; existing routes (plugin) stay with `require_api_key`
- JWT claims: `{ sub, org, rol, jti, exp }` — signed HS256, secret from `JWT_SECRET` env var
- Refresh tokens stored in Redis as `jti → user_id` with TTL = 7d (no DB migration needed)
- `python-jose[cryptography]` + `passlib[bcrypt]` already installed — zero new backend deps

### Next.js 15 — App Router + RSC Strategy

- Static shell pages (dashboard KPIs, revision pane) → React Server Components — data fetched server-side with access token from server cookie
- Interactive pages (historial filters, pagination) → Client Components with `"use client"`
- `src/middleware.ts` → intercepts all `/(dashboard)/**` routes, verifies token presence, redirects to `/login`
- `src/lib/api.ts` → typed fetch client, attaches `Authorization: Bearer <access>`, intercepts 401 to trigger refresh; refresh mutex prevents race condition on concurrent expiry

### Token Storage

- **Access token**: memory only (React context / module variable) — never persisted
- **Refresh token**: HttpOnly `Secure` cookie set by FastAPI — JS cannot read it, XSS-safe
- Trade-off: requires explicit CORS `allow_credentials=True` and named origins (not `*`)

### Tailwind 4

- CSS-first: no `tailwind.config.js`. All M3 tokens in `globals.css` `@theme {}` block (already extracted in explore report)
- Status badge colors use Tailwind utility classes directly (`bg-green-100 text-green-700`, etc.) — no config needed

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `api/routers/auth.py` | New | Login + refresh endpoints |
| `api/dependencies/auth_jwt.py` | New | `require_jwt` dependency |
| `api/schemas/auth.py` | New | `LoginRequest`, `TokenResponse`, `RefreshRequest` |
| `api/services/auth_service.py` | New | bcrypt verify, JWT encode/decode, JTI Redis ops |
| `api/routers/web_history.py` | New | `/web/history` — JWT-scoped history |
| `api/routers/web_report.py` | New | `/web/report` — JWT-scoped KPIs |
| `api/routers/web_validate.py` | New | `/web/validate/{id}` — JWT-scoped validation |
| `api/alembic/versions/XXXX_fase4.py` | New | `token_api_prefix` column migration |
| `api/config.py` | Modified | Add `jwt_secret`, `jwt_algorithm`, expiry settings |
| `api/main.py` | Modified | Register auth + web routers; tighten CORS |
| `.env.example` | Modified | Add `JWT_SECRET`, `JWT_ALGORITHM`, `WEBAPP_ORIGIN` |
| `webapp/` | New | Full Next.js 15 project (scaffold + all pages) |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **Plugin breakage** — webapp JWT changes accidentally affect `require_api_key` routes | Low | Strict route namespace separation (`/web/` vs existing). No shared deps. CI runs Fase 3 test suite (361 tests) as regression gate. |
| **CORS misconfiguration** — HttpOnly cookie requires `allow_credentials=True` + explicit origins; `*` + credentials is rejected by browsers | Medium | Set `WEBAPP_ORIGIN` env var, inject into CORS allow-list. Document in `.env.example`. Test with Playwright against dev origin before merge. |
| **Token refresh race condition** — multiple concurrent 401s trigger duplicate refresh calls, invalidating each other's JTIs | Low | Implement refresh mutex (Promise-based lock) in `api.ts`. Standard SPA pattern — reference implementation in explore report. |
| **Redis JTI persistence** — Redis restart invalidates all refresh tokens, force-logging all users out | Low | Acceptable for Fase 4 (dev/staging). Document known limitation; DB-backed fallback deferred to Fase 5. |
| **Next.js 15 async params breaking change** — `params` must be `await`-ed in dynamic routes | Low | `nextjs-15` skill loaded during apply phase; skill covers this pattern explicitly. |

---

## Rollback Plan

- **Backend**: JWT routers are additive (new files, new `/auth/` + `/web/` routes). Rollback = remove new router registrations in `main.py` + delete new files. Zero impact on existing `/upload-slip`, `/history`, `/validate` plugin routes.
- **Migration**: `token_api_prefix` is nullable with no NOT NULL constraint — rollback migration drops the column. No data loss.
- **Frontend**: `webapp/` is a new directory; no existing files are modified. Rollback = delete directory.
- **CORS**: reverting `main.py` CORS config to `allow_origins=["*"]` + `allow_credentials=False` restores plugin behavior.

---

## Dependencies

- `python-jose[cryptography]` — already in `pyproject.toml` ✅
- `passlib[bcrypt]` — already in `pyproject.toml` ✅
- Redis 7 — already running in Docker Compose ✅
- Node.js ≥ 20 + pnpm — required for `webapp/` scaffold (not yet verified in dev env)
- `JWT_SECRET` — must be generated and added to `.env` before any auth work

---

## Success Criteria

- [ ] `POST /auth/login` returns access + refresh tokens; invalid credentials return 401
- [ ] `POST /auth/refresh` issues new access token; used/expired refresh returns 401
- [ ] All `/web/` routes return 401 without valid JWT; 200 with valid JWT
- [ ] Plugin routes (`/upload-slip`, `/history`, `/validate`) pass all 361 existing tests — zero regression
- [ ] `token_api_prefix` migration applies cleanly forward and backward
- [ ] Next.js 15 `webapp/` builds with `next build` — zero TypeScript errors
- [ ] Login page → dashboard redirect flow works end-to-end in Playwright
- [ ] Dashboard KPIs display org-scoped data (not global)
- [ ] Historial filters (date range, status) produce correct results
- [ ] Side-by-side review page renders both vouchers; decision actions call `/web/validate/{id}`
- [ ] Refresh token stored in HttpOnly cookie; access token not in localStorage or cookies
- [ ] Test count grows from 361 to ≥ 500 (pytest + vitest combined)
