# Exploration: Fase 4 — Plataforma Web de Pago

**Change:** `fase-4-webapp`
**Date:** 2026-05-11
**Status:** COMPLETE

---

## Executive Summary

The backend is **more ready than expected** for Fase 4. The DB schema already has `organizaciones` + `usuarios` tables with multi-tenant FKs, `contrasena_hash` for password auth, and `python-jose[cryptography]` already installed (JWT library, zero new deps needed). There is **no JWT code** anywhere in the application logic yet — that's the primary backend gap.

The `webapp/` directory has **5 production-quality HTML mockups** using the full M3 design token palette (already expressed as a Tailwind config extension). These mockups are **directly reusable as component references** for Next.js — they use Inter, Material Symbols, and the exact color/spacing tokens from `DESIGN.md`. No Next.js scaffold exists yet; `webapp/` is currently just `DESIGN.md` + design folder with HTML files.

The biggest architectural gap is the auth layer: from API-key-only auth to JWT with access/refresh tokens + multi-tenant scoping. Every router already has `# Note Fase 4: Replace SYSTEM_USER_ID / SYSTEM_USER_ID filter with JWT` comments — the migration path is well-defined.

---

## 1. Backend Analysis

### 1.1 What Already Exists

| Component | Status | Notes |
|-----------|--------|-------|
| `models/organizacion.py` | ✅ Complete | `plan_suscripcion` CHECK: `basico/profesional/empresarial`. Soft delete. UUID v7 PK. |
| `models/usuario.py` | ✅ Complete | `correo` UNIQUE, `contrasena_hash` bcrypt, `rol` CHECK (`admin/operador/auditor`), `token_api_hash` nullable |
| `models/comprobante.py` | ✅ Complete | `id_usuario` FK, full state machine, all filters for history UI |
| `models/validacion.py` | ✅ Complete | `id_usuario` nullable (manual auditor), `id_comprobante_original` for side-by-side |
| `dependencies/auth_api_key.py` | ✅ Works | bcrypt scan over `token_api_hash`, LIMIT 50 — **stays for WP plugin; JWT for webapp** |
| `python-jose[cryptography]` | ✅ Installed | In `pyproject.toml` — JWT signing library ready, zero new backend dep |
| `passlib[bcrypt]` | ✅ Installed | bcrypt for password verification in login endpoint |
| CORS | ✅ Present | `allow_origins=["*"]` in dev — tighten for Next.js origin in Fase 4 |
| `GET /history` | ✅ Works | Pagination + date/estado/banco filters. Comment: "Replace with JWT user" |
| `POST /upload-slip` | ✅ Works | Uses `require_api_key` dep — stays for WP plugin |
| `POST /validate/{id}` | ✅ Works | Manual validation with user attribution — needs JWT tenant scoping |
| `GET /report` | ✅ Works | Aggregate stats per user — needs JWT org scope |

### 1.2 What Needs to Be Added (Backend Gaps)

#### CRITICAL — JWT Auth Layer (new `api/routers/auth.py` + `api/dependencies/auth_jwt.py`)

```
POST /auth/login
  Body: { correo: str, contrasena: str }
  Returns: { access_token: str, refresh_token: str, token_type: "bearer", expires_in: 3600 }

POST /auth/refresh
  Body: { refresh_token: str }
  Returns: { access_token: str, token_type: "bearer", expires_in: 3600 }

POST /auth/logout  [optional Fase 4]
  Invalidates refresh token (requires refresh token blacklist in Redis or DB)
```

**JWT claims needed:**
```json
{
  "sub": "user_uuid",
  "org": "org_uuid",
  "rol": "admin|operador|auditor",
  "jti": "unique_token_id",
  "exp": 1234567890
}
```

#### IMPORTANT — New `require_jwt` dependency

A new `api/dependencies/auth_jwt.py` must be created alongside the existing `auth_api_key.py` (which stays for WP plugin). The webapp uses JWT; the plugin uses API key. Both coexist.

```python
async def require_jwt(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_session),
) -> Usuario: ...
```

#### IMPORTANT — Multi-tenant scoping on existing routers

When `require_jwt` replaces `require_api_key` on the webapp-facing endpoints:
- `GET /history` → filter by `usuario.id_organizacion` (not just `usuario.id_usuario`) if admin role
- `GET /report` → scope to org, not single user
- `POST /validate/{id}` → verify comprobante belongs to org before allowing validation

#### DEFERRED FROM FASE 3 — `token_api_prefix` column

As documented in `auth_api_key.py`:
> When user count exceeds ~200, add `token_api_prefix VARCHAR(8)` as an indexed column

This is a performance optimization for API key lookup. Should be in Fase 4 migration alongside JWT work.

#### NEW — Stripe integration (Fase 4 target)

- `stripe` Python SDK (not yet in `pyproject.toml`)
- `stripe_customer_id VARCHAR(50)` on `organizaciones` table (new column)
- `stripe_subscription_id VARCHAR(50)` on `organizaciones` table (new column)
- Webhook endpoint: `POST /billing/webhook`
- Plan update endpoint: `POST /billing/create-checkout-session`

#### NEW — `JWT_SECRET` + `JWT_ALGORITHM` in Settings

```python
# api/config.py additions
jwt_secret: str
jwt_algorithm: str = "HS256"
jwt_access_expire_minutes: int = 60
jwt_refresh_expire_days: int = 30
```

These need new entries in `.env.example`.

#### NEW — Refresh token storage

Two options (decision needed):
- **Redis** (already available): store `jti → user_id` with TTL = refresh expiry. No DB migration. Fast.
- **DB column** `refresh_token_hash` on `usuarios`: adds migration but survives Redis restart.

Recommendation: **Redis** for Fase 4 (simpler, no migration). Add DB storage in Fase 5 if resilience needed.

---

## 2. DB Schema Analysis

### 2.1 Current Schema (all 4 migrations applied)

```
organizaciones
  id_organizacion  UUID PK (v7)
  nombre           VARCHAR(150)
  plan_suscripcion VARCHAR(50)  CHECK: basico|profesional|empresarial
  fecha_registro   TIMESTAMPTZ  server_default=now()
  deleted_at       TIMESTAMPTZ  (soft delete)
  ix_organizaciones_deleted_at

usuarios
  id_usuario       UUID PK (v7)
  id_organizacion  UUID FK → organizaciones (RESTRICT)
  nombre           VARCHAR(150)
  correo           VARCHAR(254)  UNIQUE, indexed
  contrasena_hash  VARCHAR(255)  bcrypt
  rol              VARCHAR(20)   CHECK: admin|operador|auditor
  token_api_hash   VARCHAR(255)  nullable (API key for WP plugin)
  fecha_registro   TIMESTAMPTZ
  deleted_at       TIMESTAMPTZ
  ix_usuarios_correo (UNIQUE), ix_usuarios_id_organizacion, ix_usuarios_deleted_at

comprobantes
  id_comprobante   UUID PK (v7)
  id_usuario       UUID FK → usuarios (RESTRICT)
  imagen_path      VARCHAR(500)
  texto_extraido   TEXT
  referencia       VARCHAR(100)
  monto            NUMERIC(15,2)
  fecha_deposito   DATE          indexed
  numero_operacion VARCHAR(100)
  banco            VARCHAR(50)
  hash_documento   VARCHAR(64)   UNIQUE (SHA-256)
  estado_actual    VARCHAR(20)   indexed, CHECK (8 states)
  fecha_registro   TIMESTAMPTZ
  deleted_at       TIMESTAMPTZ
  + ix_comprobantes_id_usuario, ix_comprobantes_estado_actual
  + ix_comprobantes_fecha_deposito (Fase 2: composite index on referencia+monto+fecha)

validaciones
  id_validacion            UUID PK (v7)
  id_comprobante           UUID FK → comprobantes (CASCADE)
  id_usuario               UUID FK → usuarios (SET NULL)  nullable — auto-detection has no author
  id_comprobante_original  UUID FK → comprobantes (SET NULL)  nullable — for side-by-side
  score_similitud          FLOAT  nullable
  clasificacion            VARCHAR(20)  CHECK: valido|sospechoso|duplicado
  metodo_deteccion         VARCHAR(30)  CHECK: hash_exacto|campos_exactos|scoring_ponderado|manual
  fecha_validacion         TIMESTAMPTZ
  deleted_at               TIMESTAMPTZ

log_procesamiento
  id_log           UUID PK
  id_comprobante   UUID FK
  id_usuario       UUID FK (SET NULL) nullable
  etapa            VARCHAR(50)
  mensaje          TEXT
  nivel            VARCHAR(10)  CHECK: INFO|WARN|ERROR
  fecha_evento     TIMESTAMPTZ
```

### 2.2 Missing Columns for Fase 4

| Table | Column | Type | Purpose |
|-------|--------|------|---------|
| `usuarios` | `token_api_prefix` | `VARCHAR(8) NULLABLE` | Indexed prefix for O(1) API key lookup |
| `organizaciones` | `stripe_customer_id` | `VARCHAR(50) NULLABLE` | Stripe billing integration |
| `organizaciones` | `stripe_subscription_id` | `VARCHAR(50) NULLABLE` | Active subscription ID |

### 2.3 Schema Verdict

The schema is **well-designed for Fase 4**. Multi-tenancy is pre-wired:
- `organizaciones.id_organizacion` cascades through `usuarios.id_organizacion` → `comprobantes.id_usuario`
- `plan_suscripcion` CHECK constraint aligns with Stripe's 3-tier plan model
- `rol` CHECK constraint (`admin/operador/auditor`) maps to RBAC for the webapp
- The `validaciones.id_comprobante_original` FK is the exact data needed for the side-by-side review UI

**No breaking changes needed.** Fase 4 adds columns, not restructures.

---

## 3. Design System Token Extraction

### 3.1 Tailwind 4 CSS Custom Properties Format

The `DESIGN.md` + HTML mockup already has the full token set in Tailwind config extension format. For Tailwind 4 (CSS-first, no `tailwind.config.js`), these translate to `globals.css`:

```css
/* webapp/src/app/globals.css */
@import "tailwindcss";

@theme {
  /* ── Colors (M3 palette) ── */
  --color-surface:                    #f9f9ff;
  --color-surface-dim:                #d3daef;
  --color-surface-bright:             #f9f9ff;
  --color-surface-container-lowest:   #ffffff;
  --color-surface-container-low:      #f1f3ff;
  --color-surface-container:          #e9edff;
  --color-surface-container-high:     #e1e8fd;
  --color-surface-container-highest:  #dce2f7;
  --color-on-surface:                 #141b2b;
  --color-on-surface-variant:         #434654;
  --color-inverse-surface:            #293040;
  --color-inverse-on-surface:         #edf0ff;
  --color-outline:                    #737685;
  --color-outline-variant:            #c3c6d6;
  --color-surface-tint:               #0c56d0;

  /* Primary */
  --color-primary:                    #003d9b;
  --color-on-primary:                 #ffffff;
  --color-primary-container:          #0052cc;
  --color-on-primary-container:       #c4d2ff;
  --color-inverse-primary:            #b2c5ff;
  --color-primary-fixed:              #dae2ff;
  --color-primary-fixed-dim:          #b2c5ff;
  --color-on-primary-fixed:           #001848;
  --color-on-primary-fixed-variant:   #0040a2;

  /* Secondary */
  --color-secondary:                  #585f6c;
  --color-on-secondary:               #ffffff;
  --color-secondary-container:        #dce2f3;
  --color-on-secondary-container:     #5e6572;
  --color-secondary-fixed:            #dce2f3;
  --color-secondary-fixed-dim:        #c0c7d6;
  --color-on-secondary-fixed:         #151c27;
  --color-on-secondary-fixed-variant: #404754;

  /* Tertiary */
  --color-tertiary:                   #404447;
  --color-on-tertiary:                #ffffff;
  --color-tertiary-container:         #585b5f;
  --color-on-tertiary-container:      #d1d3d7;
  --color-tertiary-fixed:             #e0e2e6;
  --color-tertiary-fixed-dim:         #c4c7ca;
  --color-on-tertiary-fixed:          #191c1f;
  --color-on-tertiary-fixed-variant:  #44474a;

  /* Error */
  --color-error:                      #ba1a1a;
  --color-on-error:                   #ffffff;
  --color-error-container:            #ffdad6;
  --color-on-error-container:         #93000a;

  /* Background (alias of surface) */
  --color-background:                 #f9f9ff;
  --color-on-background:              #141b2b;
  --color-surface-variant:            #dce2f7;

  /* ── Typography ── */
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;

  /* h1: 24/32 -0.02em 600 */
  --text-h1:          1.5rem;
  --text-h1--line-height: 2rem;
  --text-h1--letter-spacing: -0.02em;
  --text-h1--font-weight: 600;

  /* h2: 20/28 -0.01em 600 */
  --text-h2:          1.25rem;
  --text-h2--line-height: 1.75rem;
  --text-h2--letter-spacing: -0.01em;
  --text-h2--font-weight: 600;

  /* h3: 16/24 600 */
  --text-h3:          1rem;
  --text-h3--line-height: 1.5rem;
  --text-h3--font-weight: 600;

  /* body-lg: 16/24 400 */
  --text-body-lg:     1rem;
  --text-body-lg--line-height: 1.5rem;

  /* body-md: 14/20 400 */
  --text-body-md:     0.875rem;
  --text-body-md--line-height: 1.25rem;

  /* label-sm: 12/16 500 +0.02em */
  --text-label-sm:    0.75rem;
  --text-label-sm--line-height: 1rem;
  --text-label-sm--letter-spacing: 0.02em;
  --text-label-sm--font-weight: 500;

  /* code: 13/20 400 monospace */
  --text-code:        0.8125rem;
  --text-code--line-height: 1.25rem;
  --font-mono: ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, Consolas, monospace;

  /* ── Spacing (8px base rhythm) ── */
  --spacing-xs:       0.25rem;   /* 4px */
  --spacing-sm:       0.5rem;    /* 8px */
  --spacing-md:       1rem;      /* 16px */
  --spacing-lg:       1.5rem;    /* 24px */
  --spacing-xl:       2rem;      /* 32px */
  --spacing-gutter:   1.25rem;   /* 20px */

  /* ── Border Radius ── */
  --radius-sm:        0.125rem;  /* 2px */
  --radius:           0.25rem;   /* 4px — buttons, badges, inputs */
  --radius-md:        0.375rem;  /* 6px */
  --radius-lg:        0.5rem;    /* 8px — cards */
  --radius-xl:        0.75rem;   /* 12px — sidebar items, modals */
  --radius-full:      9999px;    /* pills */

  /* ── Container ── */
  --container-max:    80rem;     /* 1280px */
}
```

### 3.2 Semantic Status Colors (Tailwind 4 native — no config)

Status badge colors are standard Tailwind green/red/orange — use utility classes directly:
- `valido` → `bg-green-100 text-green-700`
- `duplicado` → `bg-red-100 text-red-700`
- `sospechoso` → `bg-orange-100 text-orange-700`
- `en_revision` → `bg-yellow-100 text-yellow-700`

---

## 4. Fase 4 Scope Recommendation

### 4.1 INCLUDE in Fase 4 (critical path for usable webapp)

| # | Feature | Backend work | Frontend work |
|---|---------|-------------|---------------|
| F4-1 | JWT auth endpoints (`/auth/login`, `/auth/refresh`) | New router + dependency + Redis JTI store | Login page + token refresh interceptor |
| F4-2 | Next.js 14 App Router scaffold with Tailwind 4 | — | `webapp/` init, `globals.css`, layout, auth middleware |
| F4-3 | Dashboard page (KPI cards + recent activity) | `GET /report` scoped to org (add `require_jwt`) | Dashboard component from mockup |
| F4-4 | History page with filters | `GET /history` with `require_jwt` | Historial page, date pickers, status pills |
| F4-5 | Side-by-side duplicate review | `POST /validate/{id}` with `require_jwt` | Split-pane review UI from mockup |
| F4-6 | `token_api_prefix` column + migration | New Alembic migration | — |
| F4-7 | CORS tighten to Next.js origin | `config.py` + `.env` var | — |
| F4-8 | Multi-tenant scoping in routers | History/Report filtered by `id_organizacion` | Tenant switcher UI (if multi-org user) |

### 4.2 DEFER to Fase 5

| # | Feature | Reason |
|---|---------|--------|
| F5-1 | Stripe subscriptions | Requires Stripe account, webhook infra, plan enforcement logic. High complexity. Deliver after webapp is live and testable. |
| F5-2 | Refresh token blacklist resilience (DB-backed) | Redis-backed JTI is sufficient for Fase 4. DB migration adds scope. |
| F5-3 | Upload page (webapp UI) | WP plugin covers uploads in production. Webapp upload is secondary. |
| F5-4 | User management (invite, change role) | Admin-only feature. Not in critical path. |
| F5-5 | Export endpoint (streaming CSV/XLSX) | `/report` summary sufficient for Fase 4. |
| F5-6 | Nginx prod config + TLS | Infrastructure phase. |

---

## 5. Affected Files

### Backend — New Files

```
api/routers/auth.py             ← POST /auth/login, /auth/refresh
api/dependencies/auth_jwt.py    ← require_jwt dependency (JWT bearer)
api/schemas/auth.py             ← LoginRequest, TokenResponse, RefreshRequest
api/services/auth_service.py    ← bcrypt verify, JWT encode/decode, JTI Redis ops
api/alembic/versions/XXXX_fase4_jwt_and_prefix.py  ← token_api_prefix column
```

### Backend — Modified Files

```
api/config.py                   ← jwt_secret, jwt_algorithm, jwt_access_expire_minutes, jwt_refresh_expire_days
api/main.py                     ← include_router(auth.router), tighten CORS
api/routers/history.py          ← add require_jwt dep, scope by org if admin
api/routers/report.py           ← add require_jwt dep, scope by org
api/routers/validate.py         ← add require_jwt dep, verify org ownership
.env.example                    ← JWT_SECRET, JWT_ALGORITHM vars
```

### Frontend — New Directory

```
webapp/
├── src/
│   ├── app/
│   │   ├── layout.tsx          ← root layout, Inter font, metadata
│   │   ├── globals.css         ← Tailwind 4 @theme tokens
│   │   ├── (auth)/
│   │   │   └── login/page.tsx
│   │   └── (dashboard)/
│   │       ├── layout.tsx      ← sidebar + header shell
│   │       ├── page.tsx        ← dashboard KPIs
│   │       ├── historial/page.tsx
│   │       └── revision/[id]/page.tsx
│   ├── components/
│   │   ├── ui/                 ← status-badge, kpi-card, pagination
│   │   ├── layout/             ← sidebar, top-nav, tenant-switcher
│   │   └── review/             ← side-by-side pane, validate-buttons
│   ├── lib/
│   │   ├── api.ts              ← typed fetch client (access token attach + refresh)
│   │   └── auth.ts             ← token storage, decode, logout
│   └── middleware.ts           ← Next.js route protection
├── package.json
├── tsconfig.json
└── next.config.ts
```

---

## 6. Risks

### R-1: Dual auth system complexity (MEDIUM)
Two auth mechanisms coexist: `require_api_key` (WP plugin) and `require_jwt` (webapp). Both hit the same `/upload-slip`, `/history`, `/validate` endpoints via different dependencies. Solution: **do NOT share endpoints** — add JWT-protected aliases under `/api/v1/` namespace, keep legacy endpoints for plugin. Or gate by header presence.

**Recommended approach:** Keep existing endpoints with `require_api_key` for plugin. Add `/web/` prefixed routes (or route group) with `require_jwt` for webapp. Eliminates any risk of breaking the Fase 3 plugin.

### R-2: CORS must allow credentials (MEDIUM)
When using HTTP-only cookies for token storage (safer for webapp), `CORSMiddleware` needs:
- `allow_origins=["http://localhost:3000", "https://yourdomain.com"]` (explicit, not `*`)
- `allow_credentials=True`

With localStorage tokens (simpler), `allow_credentials=False` is fine but XSS-vulnerable.

**Decision needed:** HttpOnly cookie vs. localStorage for token storage.

### R-3: `sospechoso` state missing from initial migration CHECK (LOW)
The initial migration (607b4c53997b) has the CHECK without `'sospechoso'` — it was added in migration `a1b2c3d4e5f6`. The model source is correct. This is already resolved but worth noting for any manual schema reconstruction.

### R-4: Next.js 14 vs 15 (LOW)
The task spec says Next.js 14 App Router. Latest stable is Next.js 15. The `nextjs-15` skill is available. **Recommend Next.js 15** — RSC patterns are the same, minor API differences (async `params`), avoids going EOL mid-development.

### R-5: Stripe webhook verification requires raw body (MEDIUM)
FastAPI with `Request.body()` returns decoded bytes, but Stripe requires the raw request body for signature verification. Need to use `Request` directly (not Pydantic model) for the webhook route. This is a known gotcha.

### R-6: Token refresh race condition (LOW)
If the webapp makes multiple concurrent requests with an expired access token, multiple refresh requests can fire simultaneously. Need a refresh mutex (in-memory lock or queue) in the API client. Standard pattern — mention in design.

---

## 7. Approaches

### Auth approach comparison

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A: /web/ route namespace** (recommended) | Zero risk to WP plugin; clean separation; easy to test both | Slightly more code (duplicate route registrations) | Low |
| **B: Same routes, check header type** | Fewer files | Fragile; hard to test; mixing concerns | Low code, High risk |
| **C: Deprecate API key, migrate plugin to JWT** | Single auth system | Breaks Fase 3 plugin; out of scope | High |

**Recommendation: Approach A** — `/web/` prefixed routes with `require_jwt`, existing routes stay with `require_api_key`.

### Token storage comparison

| Approach | Security | Complexity | CORS |
|----------|----------|------------|------|
| **HttpOnly cookie** (recommended) | XSS-safe | Server must set cookie; CORS needs credentials | Need explicit origins |
| **localStorage** | XSS-vulnerable | Simple JS | No credentials needed |
| **Memory + refresh cookie** | Best practice | Most complex | Explicit origins |

**Recommendation: HttpOnly cookie for refresh token, memory (React context) for access token.** This is the industry standard for SPAs.

---

## Ready for Proposal

**Yes.** The exploration is complete. Key decisions for the proposal phase:

1. Route namespace strategy (recommend: `/web/` routes with `require_jwt`)
2. Token storage strategy (recommend: HttpOnly refresh cookie + memory access token)
3. Next.js 14 vs 15 (recommend: 15)
4. Stripe scope: Fase 4 vs Fase 5 (recommend: defer Stripe to Fase 5)
