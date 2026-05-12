# Fase 4 — Technical Design

**Change:** `fase-4-webapp`
**Date:** 2026-05-11
**Status:** Ready for Tasks
**Covers:** R-21–R-46 (28 requirements, 43 scenarios)

---

## Architecture Overview

```
                      ┌──────────────────────────────────────────────┐
                      │              Next.js 15  (webapp/)            │
                      │  /login   /   /historial/[id]  /revision/[id] │
                      │  AuthProvider  →  fetchApi<T>  →  mutex       │
                      └───────────────────┬──────────────────────────┘
                                          │ HTTPS  (rewrites /api → :8000)
                      ┌───────────────────▼──────────────────────────┐
                      │              FastAPI  (api/)                   │
                      │                                                │
                      │  /web/auth/*   → require_jwt   (NEW)          │
                      │  /web/comprobantes/*  → require_jwt   (NEW)   │
                      │  /web/stats/   → require_jwt   (NEW)          │
                      │  ─────────────────────────────────────        │
                      │  /upload-slip  → require_api_key  (KEEP)      │
                      │  /history      → require_api_key  (KEEP)      │
                      │  /validate/*   → require_api_key  (KEEP)      │
                      │  /report       → require_api_key  (KEEP)      │
                      └───────┬──────────────────────┬───────────────┘
                               │                      │
                      ┌────────▼──────┐      ┌────────▼──────┐
                      │  PostgreSQL   │      │   Redis 7      │
                      │  usuarios +   │      │  jti:<uuid>    │
                      │  token_api_   │      │  TTL=7d        │
                      │  prefix col   │      └───────────────┘
                      └───────────────┘
```

---

## 1. FastAPI JWT Auth

### File Map

| File | Action | Description |
|------|--------|-------------|
| `api/routers/web_auth.py` | Create | Router prefix `/web/auth`: login, refresh, logout, me |
| `api/dependencies/auth_jwt.py` | Create | `require_jwt` FastAPI dependency |
| `api/services/jwt_service.py` | Create | Token creation, verification, Redis JTI ops |
| `api/schemas/auth.py` | Create | `LoginRequest`, `TokenResponse`, `UsuarioPublic` |
| `api/core/config.py` | Note | Config lives at `api/config.py` (no `core/` subdir exists) |
| `api/config.py` | Modify | Add `JWT_SECRET_KEY`, `JWT_ALGORITHM`, expiry settings, `WEBAPP_ORIGIN` |
| `api/main.py` | Modify | Register web_auth + web routers; tighten CORS to `WEBAPP_ORIGIN` |
| `api/tests/test_jwt_auth.py` | Create | Tests for S-01–S-10 |

> **Config correction:** The project uses `api/config.py` directly (no `api/core/` subdirectory). All `Settings` additions go there.

### Key Algorithms

**`api/services/jwt_service.py` — function signatures:**

```python
from datetime import timedelta
from uuid import UUID
import redis.asyncio as aioredis
from jose import JWTError, jwt
from config import settings

def create_access_token(sub: str, org: str, rol: str, jti: str) -> str:
    """Sign HS256 JWT with claims {sub, org, rol, jti, exp}. TTL=15m."""

def create_refresh_token() -> str:
    """Return a new UUID4 string to use as JTI."""

async def store_jti(redis: aioredis.Redis, jti: str, user_id: str) -> None:
    """SET jti:<jti> user_id EX 604800"""

async def rotate_jti(redis: aioredis.Redis, old_jti: str, new_jti: str, user_id: str) -> bool:
    """Atomic GETDEL old_jti → if found, SET new_jti. Returns False if old JTI missing."""

async def revoke_jti(redis: aioredis.Redis, jti: str) -> None:
    """DEL jti:<jti>"""

async def is_jti_valid(redis: aioredis.Redis, jti: str) -> bool:
    """EXISTS jti:<jti> → bool"""

def verify_token(token: str) -> dict:
    """Decode + verify HS256 signature and exp. Raises JWTError on failure."""
```

**`api/dependencies/auth_jwt.py` — signature:**

```python
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_session
from models.usuario import Usuario
from services.jwt_service import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/web/auth/login", auto_error=False)

async def require_jwt(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Validate Bearer token → return Usuario. Raises 401 on any failure."""
```

**`api/routers/web_auth.py` — endpoint signatures:**

```python
router = APIRouter(prefix="/web/auth", tags=["web-auth"])

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db, redis) -> TokenResponse:
    ...

@router.post("/refresh", response_model=TokenResponse)
async def refresh(response: Response, refresh_token: str = Cookie(None), db, redis) -> TokenResponse:
    ...

@router.post("/logout", status_code=200)
async def logout(response: Response, usuario: Usuario = Depends(require_jwt), redis) -> dict:
    ...

@router.get("/me", response_model=UsuarioPublic)
async def me(usuario: Usuario = Depends(require_jwt)) -> UsuarioPublic:
    ...
```

**`api/schemas/auth.py`:**

```python
class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes in seconds

class UsuarioPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_usuario: UUID
    correo: str
    nombre: str
    rol: str
    id_organizacion: UUID
```

### Redis JTI Pattern

```
Key:   jti:{uuid4}
Value: {id_usuario}          (string)
TTL:   604800 seconds (7d)

Operations:
  login   → SET jti:{new}  id_usuario  EX 604800
  refresh → GETDEL jti:{old} → if None: 401
            SET jti:{new} id_usuario EX 604800
  logout  → DEL jti:{access_jti}
```

`rotate_jti` uses a Lua script or pipeline to make GETDEL+SET atomic — prevents replay on concurrent refresh.

### Security Decisions

| Decision | Option A | Option B | Choice |
|----------|----------|----------|--------|
| Access token storage | localStorage (simple) | React context / memory (XSS-safe) | **Memory** (R-34) |
| Refresh token storage | localStorage | HttpOnly Secure SameSite=Strict cookie | **HttpOnly cookie** (R-22) |
| Token algorithm | RS256 (asymmetric) | HS256 (symmetric, simpler) | **HS256** — single backend, no key distribution needed |
| S-03 timing-safe | Return immediately on user not found | Run dummy bcrypt | **Dummy bcrypt** — prevents user enumeration via response-time oracle |
| `require_jwt` placement | Shared dep on all `/web/` | Per-route `Depends()` | **Router-level** via `dependencies=[Depends(require_jwt)]` on the `APIRouter` — except login/refresh which skip it explicitly |

**CORS tightening in `main.py`:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.webapp_origin],   # e.g. "http://localhost:3000"
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 2. token_api_prefix Migration

### Migration Plan

**File:** `api/alembic/versions/XXXX_add_token_api_prefix.py`

Revision chain: after `34b207551c82` (last applied fase-2 migration).

```python
# upgrade()
op.add_column("usuarios",
    sa.Column("token_api_prefix", sa.String(8), nullable=True))
op.create_index("ix_usuarios_token_api_prefix",
    "usuarios", ["token_api_prefix"])
op.execute("""
    UPDATE usuarios
    SET token_api_prefix = LEFT(token_api_hash, 8)
    WHERE token_api_hash IS NOT NULL
""")

# downgrade()
op.drop_index("ix_usuarios_token_api_prefix", "usuarios")
op.drop_column("usuarios", "token_api_prefix")
```

**Model update (`api/models/usuario.py`):**

```python
token_api_prefix: Mapped[str | None] = mapped_column(
    String(8), nullable=True, index=True
)
```

**`api/dependencies/auth_api_key.py` update** — replace the current LIMIT 50 full scan:

```python
prefix = x_api_key[:8]
stmt = (
    select(Usuario)
    .where(
        Usuario.token_api_prefix == prefix,
        Usuario.deleted_at.is_(None),
    )
)
# then bcrypt.checkpw on the narrowed set (typically 1 row)
```

### Performance Impact

| Scenario | Before (Fase 3) | After (Fase 4) |
|----------|-----------------|----------------|
| 50 users | 50 bcrypt ops | 1 bcrypt op |
| 500 users | 500 bcrypt ops | 1 bcrypt op |
| Prefix miss | 50 bcrypt ops | 0 bcrypt ops (index short-circuits) |

S-14 (NULL prefix rows excluded): the `WHERE token_api_prefix = prefix` naturally excludes NULL rows — no extra filter needed.

---

## 3. Web Routes

### Router Map

| File | Action | Endpoints |
|------|--------|-----------|
| `api/routers/web_comprobantes.py` | Create | `GET /web/comprobantes/`, `GET /web/comprobantes/{id}`, `POST /web/comprobantes/{id}/decision` |
| `api/routers/web_stats.py` | Create | `GET /web/stats/` |
| `api/schemas/web.py` | Create | `WebComprobanteResponse`, `WebComprobanteDetail`, `WebListResponse`, `DecisionRequest`, `StatsResponse` |
| `api/tests/test_web_comprobantes.py` | Create | Tests for R-39–R-46 scenarios |
| `api/tests/test_web_stats.py` | Create | Tests for R-37–R-38 scenarios |

**`api/schemas/web.py` contracts:**

```python
class WebComprobanteResponse(BaseModel):
    # Same fields as ComprobanteResponse + texto_extraido + banco + referencia
    # (ComprobanteResponse hides texto_extraido; web detail exposes it)
    id_comprobante: UUID
    monto: Decimal | None
    fecha_deposito: date | None
    banco: str
    referencia: str | None
    numero_operacion: str | None
    texto_extraido: str | None
    imagen_path: str
    estado_actual: str
    fecha_registro: datetime

class WebListResponse(BaseModel):
    items: list[WebComprobanteResponse]
    total: int
    page: int
    page_size: int
    has_more: bool

class DecisionRequest(BaseModel):
    accion: Literal["aceptar", "rechazar"]
    motivo: str | None = None

class StatsResponse(BaseModel):
    total_mes: int
    duplicados_mes: int
    tasa_error: float   # percentage 0.0–100.0
```

### Org-Scoping Pattern

All `/web/` routes scope by `id_organizacion` from the JWT claims. The pattern follows the existing `history.py` approach but joins through `usuarios`:

```python
# web_comprobantes.py — org-scoped list
stmt = (
    select(Comprobante)
    .join(Usuario, Comprobante.id_usuario == Usuario.id_usuario)
    .where(
        Usuario.id_organizacion == usuario.id_organizacion,
        Comprobante.deleted_at.is_(None),
    )
)

# web_comprobantes.py — org-ownership check for detail/decision
if comp.usuario.id_organizacion != usuario.id_organizacion:
    raise HTTPException(status_code=403, detail="Access denied")
```

**`GET /web/comprobantes/` query params:** `status: str | None`, `date_from: date | None`, `date_to: date | None`, `page: int = 1`, `page_size: int = 20` (max 100).

**`POST /web/comprobantes/{id}/decision` logic:** validates org ownership → calls `apply_transition(comp, "valido" if accion=="aceptar" else "duplicado")` → creates `Validacion(metodo_deteccion="manual")` — reuses existing state machine.

**`GET /web/stats/`** — org-scoped aggregate: month-to-date `COUNT(*)`, `COUNT(*) WHERE estado_actual='duplicado'`, error rate `= duplicados/total * 100`.

### conftest.py Extension

New `client_jwt` fixture using `app.dependency_overrides[require_jwt]` (parallel to existing `require_api_key` override) — avoids touching existing 361 tests.

---

## 4. Next.js 15 Scaffold

### Directory Structure

```
webapp/
├── package.json              — next@15, typescript, tailwindcss@^4, @shadcn/ui
├── tsconfig.json             — strict: true, paths: {"@/*": ["./src/*"]}
├── next.config.ts            — rewrites: /api/:path* → http://localhost:8000/:path*
├── src/
│   ├── app/
│   │   ├── globals.css             — @import "tailwindcss"; @theme { …all M3 tokens… }
│   │   ├── layout.tsx              — root layout: Inter font, AuthProvider wrapper
│   │   ├── page.tsx                — dashboard (RSC): fetches /web/stats/ + /web/comprobantes/?limit=10
│   │   ├── login/
│   │   │   └── page.tsx            — Client Component: login form
│   │   ├── historial/
│   │   │   ├── page.tsx            — Client Component: HistorialTable + FilterBar
│   │   │   └── [id]/page.tsx       — RSC: comprobante detail view
│   │   └── revision/
│   │       └── [id]/page.tsx       — Client Component: side-by-side review + decision
│   ├── components/
│   │   ├── ui/                     — shadcn/ui primitives (Button, Badge, Table, Card, Input)
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx         — navigation links, active state
│   │   │   └── Topbar.tsx          — tenant nombre display, logout button
│   │   ├── dashboard/
│   │   │   ├── KpiCard.tsx         — single stat card (label + value + icon)
│   │   │   └── RecentActivity.tsx  — last-10 comprobantes table with status badges
│   │   ├── historial/
│   │   │   ├── HistorialTable.tsx  — paginated table, row click → router.push
│   │   │   └── FilterBar.tsx       — status pills + date range picker
│   │   └── revision/
│   │       ├── VoucherViewer.tsx   — <img> + OCR fields parsed from texto_extraido
│   │       ├── OcrFields.tsx       — labeled key-value rows (monto, banco, referencia, fecha)
│   │       └── DuplicatePanel.tsx  — candidates table + Aceptar/Rechazar buttons
│   ├── lib/
│   │   ├── api.ts                  — fetchApi<T>: Bearer attach + 401 mutex refresh
│   │   └── auth-context.tsx        — AuthProvider + useAuth hook: {user, token, login, logout}
│   └── middleware.ts               — matcher: /((?!login|_next|favicon).*)
```

### Auth Flow (sequence)

```
Browser                    Next.js MW       FastAPI
  │                            │               │
  │── GET /  ─────────────────▶│               │
  │         (no cookie)        │               │
  │◀── 307 /login ────────────│               │
  │                            │               │
  │── POST /login ────────────────────────────▶│
  │      {correo, contrasena}  │           validate bcrypt
  │◀── {access_token} ──────────────────────── │
  │   Set-Cookie: refresh_token=<jti>; HttpOnly│
  │                            │               │
  │  [store access_token       │               │
  │   in AuthContext (memory)] │               │
  │                            │               │
  │── GET /  ─────────────────▶│               │
  │         (cookie present)   │               │
  │         MW: allow ────────▶│               │
  │              RSC: fetch ──────────────────▶│
  │              GET /web/stats/ Bearer <token>│
  │◀────────────────────────── {kpis} ─────────│
  │                            │               │
  │  [access_token expires]    │               │
  │── GET /web/comprobantes/ ─────────────────▶│
  │                            │           401 Unauthorized
  │◀─────────────────────────── 401 ───────────│
  │  [fetchApi mutex acquired] │               │
  │── POST /web/auth/refresh ─────────────────▶│
  │   Cookie: refresh_token=<old_jti>          │
  │◀─── {new access_token} ────────────────────│
  │   Set-Cookie: refresh_token=<new_jti>      │
  │  [retry original request]  │               │
  │── GET /web/comprobantes/ ─────────────────▶│
  │   Bearer <new access_token>│               │
  │◀─── {items} ───────────────────────────────│
```

### Tailwind 4 Token Map

All tokens come directly from `fase-4-explore.md` Section 3.1. Key mapping to components:

| Token | Component usage |
|-------|----------------|
| `--color-primary` | Primary buttons, active nav items |
| `--color-surface-container-low` | Card backgrounds |
| `--color-surface-container-highest` | Table header background |
| `--color-on-surface-variant` | Secondary text, labels |
| `--font-sans` | Global body font (Inter) |
| `--radius-lg` | Card border-radius |
| `--radius-xl` | Sidebar item hover state |
| `--spacing-gutter` | Page horizontal padding |

Status badges use Tailwind native utilities (no custom tokens needed): `bg-green-100 text-green-700` (valido), `bg-red-100 text-red-700` (duplicado), `bg-orange-100 text-orange-700` (sospechoso), `bg-yellow-100 text-yellow-700` (en_revision).

### Component Responsibility Map

| Component | RSC/Client | Data source | Key behavior |
|-----------|-----------|-------------|--------------|
| `page.tsx` (dashboard) | RSC | `/web/stats/` + `/web/comprobantes/?limit=10` | Server fetch with access token from cookie |
| `login/page.tsx` | Client | — | `useAuth().login()` → redirect `/` |
| `historial/page.tsx` | Client | `/web/comprobantes/` | URL state for filters, `useSearchParams` |
| `historial/[id]/page.tsx` | RSC | `/web/comprobantes/{id}` | Render all fields, error state on 403/404 |
| `revision/[id]/page.tsx` | Client | `/web/comprobantes/{id}` | Optimistic update on decision |
| `FilterBar.tsx` | Client | — | Controlled pills + date inputs, emits `onChange` |
| `DuplicatePanel.tsx` | Client | — | Optimistic state local var before API call |

**`api.ts` refresh mutex pattern:**

```typescript
let refreshPromise: Promise<string> | null = null;

async function fetchApi<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...options, headers: { Authorization: `Bearer ${getToken()}` } });
  if (res.status === 401 && !refreshPromise) {
    refreshPromise = refreshToken().finally(() => { refreshPromise = null; });
  }
  if (res.status === 401) {
    await refreshPromise;
    return fetchApi<T>(url, options); // retry once
  }
  return res.json();
}
```

---

## 5. Testing Strategy

### Python layer (pytest + pytest-asyncio)

| File | Fixtures | Mocks | Scenarios |
|------|----------|-------|-----------|
| `test_jwt_auth.py` | `db_session`, new `redis_client` fixture (fakeredis) | `jose.jwt.decode`, bcrypt | S-01–S-10 |
| `test_token_api_prefix.py` | `db_session`, `client` | — (uses real prefix logic) | S-11–S-15 |
| `test_web_comprobantes.py` | `db_session`, new `client_jwt` fixture | `require_jwt` override | S-27–S-32, S-39–S-40 |
| `test_web_stats.py` | `db_session`, `client_jwt` | `require_jwt` override | S-23–S-26 |

**`redis_client` fixture** uses `fakeredis.aioredis.FakeRedis()` — no real Redis needed in unit tests.

**`client_jwt` fixture** parallel to existing `client`:

```python
@pytest_asyncio.fixture
async def client_jwt(db_session):
    mock_user = MagicMock()
    mock_user.id_usuario = SYSTEM_USER_ID
    mock_user.id_organizacion = SYSTEM_ORG_ID
    mock_user.rol = "admin"
    app.dependency_overrides[require_jwt] = lambda: mock_user
    app.dependency_overrides[get_session] = lambda: db_session
    ...
```

**Test count projection:**
- S-01–S-10: 10 scenarios × ~3 assertions = ~30 tests
- S-11–S-15: 5 scenarios × ~2 assertions = ~10 tests
- web_comprobantes + web_stats: ~20 tests
- Total new Python: ~40 tests → Python total: 361 + 40 = **401 tests**

### Next.js layer (vitest + testing-library)

| Component/Module | What to test | Count |
|-----------------|-------------|-------|
| `auth-context.tsx` | `login()` stores token in memory, `logout()` clears, never writes localStorage | 5 |
| `api.ts` | Mutex: 3 concurrent 401s → single refresh call (S-20) | 8 |
| `FilterBar.tsx` | Pill click updates URL params, date range clears correctly | 10 |
| `HistorialTable.tsx` | Row renders correct badge color per status, empty state | 8 |
| `KpiCard.tsx` | Renders 0 without crash (S-24), renders numeric value | 4 |
| `DuplicatePanel.tsx` | Optimistic update (S-35), revert on API failure (S-36) | 10 |
| `OcrFields.tsx` | Renders all OCR fields, handles null gracefully | 5 |
| `VoucherViewer.tsx` | Renders `<img>` with correct src | 3 |
| `login/page.tsx` | Form submission, error state, redirect on success | 8 |
| `middleware.ts` | Redirect unauthenticated, allow /login, allow cookie-present | 6 |
| Schema/util unit tests | Token decode helpers, date format utils | 10 |

**Target: ~77–100 vitest tests**

### E2E layer (Playwright)

| Flow | Steps | Scenarios covered |
|------|-------|------------------|
| Login → Dashboard | Navigate /login, fill form, assert redirect, assert KPI cards render | S-17, S-18, S-19, S-23 |
| Dashboard load | Assert 3 KPI cards, assert recent activity table has rows | S-25 |
| Historial filter | Click duplicado pill → assert URL param, assert table filtered | S-27, S-28 |
| Pagination | Click Next → assert page=2, assert different rows | S-29 |
| Revision decision | Navigate to /revision/[id], click Aceptar, assert badge green | S-35 |

**Target: 10–15 Playwright tests**

### Total test count

| Layer | Existing | New | Total |
|-------|---------|-----|-------|
| Python (pytest) | 361 | ~40 | ~401 |
| Next.js (vitest) | 0 | ~90 | ~90 |
| E2E (Playwright) | 0 | ~10 | ~10 |
| **Combined** | **361** | **~140** | **~501** ✅ |

---

## 6. Environment Variables

```bash
# .env additions for Fase 4

# JWT Auth
JWT_SECRET_KEY=<generate: openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS — explicit origin required when allow_credentials=True
WEBAPP_ORIGIN=http://localhost:3000
```

**`api/config.py` additions:**

```python
# JWT
jwt_secret_key: str
jwt_algorithm: str = "HS256"
access_token_expire_minutes: int = 15
refresh_token_expire_days: int = 7

# CORS
webapp_origin: str = "http://localhost:3000"
```

---

## 7. Dependency Graph

```
[R-26 Redis JTI Store]
    └── required by R-22 (refresh), R-23 (logout)
    └── required by jwt_service.py

[R-25 require_jwt dependency]
    └── required by R-24 (me), R-27 (web/ namespace)
    └── required by all /web/ routes

[R-28–R-30 token_api_prefix migration]
    └── independent of JWT (parallel track)
    └── migration must run before auth_api_key.py update lands

[R-31 Next.js scaffold]
    └── required by ALL webapp capabilities

[R-34 AuthProvider + api.ts]
    └── required by R-33 (middleware), R-37 (dashboard RSC), R-39 (historial)

[R-37 web/stats endpoint]
    └── required by dashboard page (R-37/R-38)
    └── requires R-25 (require_jwt)

[R-39–R-42 historial endpoints]
    └── requires R-25, R-46 (detail endpoint)

[R-43–R-45 revision page]
    └── requires R-44 (decision endpoint)
    └── requires R-25
```

**Implementation order (unblocked first):**

1. `config.py` additions + `.env` (no deps)
2. `jwt_service.py` + `auth.py` schemas (no deps)
3. `web_auth.py` router + `auth_jwt.py` dep (depends on 1+2)
4. `token_api_prefix` migration + model update (independent)
5. `auth_api_key.py` update (depends on 4)
6. `web_comprobantes.py` + `web_stats.py` + `web.py` schemas (depends on 3)
7. `main.py` CORS tightening + router registration (depends on 3+6)
8. Next.js scaffold + globals.css (depends on nothing)
9. `AuthProvider` + `api.ts` + `middleware.ts` (depends on 8)
10. Page components (depends on 8+9)

---

## File Changes Summary

| File | Action | Layer |
|------|--------|-------|
| `api/config.py` | Modify | Backend |
| `api/main.py` | Modify | Backend |
| `api/models/usuario.py` | Modify | Backend |
| `api/dependencies/auth_api_key.py` | Modify | Backend |
| `api/dependencies/auth_jwt.py` | Create | Backend |
| `api/routers/web_auth.py` | Create | Backend |
| `api/routers/web_comprobantes.py` | Create | Backend |
| `api/routers/web_stats.py` | Create | Backend |
| `api/schemas/auth.py` | Create | Backend |
| `api/schemas/web.py` | Create | Backend |
| `api/services/jwt_service.py` | Create | Backend |
| `api/alembic/versions/XXXX_add_token_api_prefix.py` | Create | Backend |
| `api/tests/test_jwt_auth.py` | Create | Backend |
| `api/tests/test_token_api_prefix.py` | Create | Backend |
| `api/tests/test_web_comprobantes.py` | Create | Backend |
| `api/tests/test_web_stats.py` | Create | Backend |
| `api/tests/conftest.py` | Modify | Backend |
| `.env.example` | Modify | Config |
| `webapp/` (37+ files) | Create | Frontend |

**New files: 13 backend + 37+ frontend | Modified: 4 backend + 1 config**

---

## Open Questions

- [ ] **Redis injection into routers:** The existing `database.py` pattern uses `Depends(get_session)`. A parallel `get_redis()` dependency returning `aioredis.Redis` needs to be added to `database.py` (or a new `api/dependencies/redis.py`). Confirm placement before apply phase.
- [ ] **Dashboard RSC token access:** Next.js RSC cannot read React context. The access token must be passed as a server-side cookie (or re-read from the HttpOnly refresh cookie + refresh on server). Recommend: on login, also set a short-lived `access_token` cookie (non-HttpOnly, readable by server) OR use Next.js route handlers as BFF. **Decision needed before webapp-dashboard apply.**
- [ ] **`fakeredis` in test deps:** Verify `fakeredis[aioredis]` can be added to `pyproject.toml` dev deps without conflict with existing `redis` pin.
