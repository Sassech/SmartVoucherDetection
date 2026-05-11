# Design: Fase 3 — Plugin WordPress `comprobantes-ocr`

**Change:** `fase-3-plugin-wp`
**Date:** 2026-05-10
**Status:** Ready for Tasks

---

## Technical Approach

Deliver a WP.org-publishable PHP plugin backed by the FastAPI OCR service, using WordPress native APIs throughout (Settings API, `wp_remote_*`, `admin-ajax.php`, nonces) and a minimal FastAPI API-key dependency (`require_api_key`) that replaces the `SYSTEM_USER_ID` hardcode. Multipart upload uses manual MIME boundary construction in PHP because `wp_remote_post()` encodes `array` bodies as `application/x-www-form-urlencoded`, not `multipart/form-data`. The Gutenberg block ships with pre-built assets checked into Git (`block/build/`) so end-users never need Node.js.

---

## Architecture Decisions

### Decision 1: Multipart file upload transport

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `wp_remote_post()` with `array` body | WP encodes as `x-www-form-urlencoded` — **binary files corrupted** | ❌ |
| Manual MIME boundary in `body` string + `Content-Type: multipart/form-data; boundary=…` header passed to `wp_remote_post()` | Correct binary transport; ~40 LOC helper in `COCR_API_Client`; well-tested pattern | ✅ |
| Base64 JSON | +33% payload; requires FastAPI endpoint change to decode | ❌ |

**Implementation:** `COCR_API_Client::_build_multipart(string $boundary, array $fields, array $file): string` returns the raw multipart body. `wp_remote_post()` receives `body` as this string and `headers` with the correct `Content-Type`.

### Decision 2: FastAPI auth — full bcrypt check now, prefix column deferred

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Iterate all active users with `bcrypt.checkpw()` | O(n) per request; acceptable for Fase 3 (≤ 50 users) | ✅ |
| Add `token_api_prefix VARCHAR(8)` indexed column | Eliminates full scan; migration + seed changes needed | Defer to Fase 4 |
| Hardcoded key in `.env` | Insecure; ships a broken product | ❌ |

**Scalability note documented in code:** when user count > 200, add `token_api_prefix` (first 8 chars of plain token) as indexed column and pre-filter `WHERE token_api_prefix = :prefix AND deleted_at IS NULL` before bcrypt. Deferred per proposal.

### Decision 3: Gutenberg block build artifacts in Git

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `block/build/` in `.gitignore` | CI must build before every ZIP — adds Node.js to runtime deploy path | ❌ |
| `block/build/` committed to Git | Reviewers see compiled output; CI just zips | ✅ |
| Write block without JSX (`wp.element.createElement`) | No build step; less maintainable; harder to read | ❌ |

**Rationale:** `@wordpress/scripts` build output is stable and deterministic. CI still runs `npm ci && npm run build` to validate, then ZIPs from the working tree. `block/src/` is excluded from the plugin ZIP.

### Decision 4: PHP class naming — `COCR_` prefix (not `Comprobantes_OCR_`)

The explore doc suggested `Comprobantes_OCR_` but the proposal and project standards mandate `COCR_` / `cocr_`. `COCR_` is shorter, already established, and passes Plugin Check.

### Decision 5: `id_usuario` injection via dependency return value

`require_api_key` returns the full `Usuario` ORM object. Routers declare `usuario: Usuario = Depends(require_api_key)` and use `usuario.id_usuario` directly. No `request.state` mutation.

---

## Plugin Directory Structure

```
plugin-wp/comprobantes-ocr/
├── comprobantes-ocr.php          # Entry point: GPL header, autoloader, hook registration
├── uninstall.php                 # Drops all wp_options on uninstall
├── readme.txt                    # WP.org SVN format
├── includes/
│   ├── class-api-client.php      # COCR_API_Client — all wp_remote_* calls + multipart helper
│   ├── class-settings.php        # COCR_Settings — Settings API registration + AJAX test-connection
│   ├── class-shortcode.php       # COCR_Shortcode — [comprobante_upload] + AJAX handler
│   ├── class-history-widget.php  # COCR_History_Widget — admin history page (GET /history)
│   ├── class-gutenberg.php       # COCR_Gutenberg — block registration + asset enqueue
│   └── class-woo-hook.php        # COCR_Woo_Hook — woocommerce_order_status_completed
├── admin/
│   ├── settings-page.php         # Template: settings form, nonces, "Test Connection" button
│   └── history-widget.php        # Template: history table with esc_html() on every cell
├── public/
│   ├── upload-handler.js         # ES6: fetch to admin-ajax.php, drag-and-drop, progress
│   ├── result-display.js         # ES6: traffic-light semaphore DOM manipulation
│   └── style.css                 # Upload area + semaphore styles (no framework)
├── block/
│   ├── block.json                # apiVersion:3, name, title, category, attributes
│   ├── package.json              # @wordpress/scripts ^30.x, build script
│   ├── src/
│   │   ├── index.js              # registerBlockType entry point
│   │   └── edit.js               # Edit component with InspectorControls + ServerSideRender
│   └── build/                    # Committed to Git (index.js + index.asset.php)
├── languages/
│   ├── comprobantes-ocr.pot
│   ├── comprobantes-ocr-es_MX.po
│   ├── comprobantes-ocr-es_MX.mo
│   ├── comprobantes-ocr-en_US.po
│   └── comprobantes-ocr-en_US.mo
├── assets/                       # WP.org directory assets — NOT included in plugin ZIP
│   ├── banner-1544x500.png
│   ├── icon-256x256.png
│   └── screenshot-1.png
```

---

## Data Flow

### Shortcode Upload (primary user path)

```
[Browser drag-drop / file input]
  └─ FormData(file, nonce, action=cocr_upload)
      └─ POST wp-admin/admin-ajax.php
          └─ COCR_Shortcode::handle_ajax()
              ├─ check_ajax_referer('cocr_upload_nonce')
              ├─ current_user_can('upload_files')
              ├─ sanitize: file ext/mime whitelist
              └─ COCR_API_Client::upload_slip($tmp_path)
                  ├─ _build_multipart(boundary, [], [file])
                  └─ wp_remote_post(API_URL/upload-slip, [
                        headers: [X-API-Key, Content-Type: multipart/...; boundary=...],
                        body:    <raw multipart string>,
                        timeout: get_option('comprobantes_timeout', 30)
                     ])
                     └─ JSON → wp_send_json_success/error()
                         └─ result-display.js renders semaphore
```

### FastAPI Auth Flow

```
POST /upload-slip  (with X-API-Key header)
  └─ require_api_key(x_api_key, db)
      ├─ SELECT * FROM usuarios WHERE deleted_at IS NULL LIMIT 50
      ├─ for each row: bcrypt.checkpw(x_api_key.encode(), row.token_api_hash.encode())
      ├─ match found → return Usuario ORM object
      └─ no match → raise HTTP 401
```

---

## Interfaces / Contracts

### `COCR_API_Client` (PHP)

```php
class COCR_API_Client {
    public function upload_slip(string $file_path, string $api_url, string $api_key, int $timeout): array|\WP_Error;
    public function get_history(string $api_url, string $api_key, int $limit = 20): array|\WP_Error;
    public function test_connection(string $api_url, string $api_key): bool|\WP_Error;
    private function _build_multipart(string $boundary, array $fields, string $file_path, string $field_name = 'file'): string;
    private function _make_request(string $method, string $endpoint, array $wp_args): array|\WP_Error;
}
```

**WP_Error taxonomy:**

| Code | Trigger |
|------|---------|
| `cocr_network_error` | `is_wp_error($response)` — DNS / timeout / TLS |
| `cocr_client_error` | HTTP 4xx — message from JSON body |
| `cocr_server_error` | HTTP 5xx |
| `cocr_invalid_response` | `json_decode` returns `null` |
| `cocr_file_unreadable` | `!is_readable($file_path)` before building multipart |

### `require_api_key` (Python)

```python
# api/dependencies/auth_api_key.py
from typing import Annotated
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
from database import get_session
from models.usuario import Usuario

async def require_api_key(
    x_api_key: Annotated[str, Header()],
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    result = await db.execute(
        select(Usuario)
        .where(Usuario.deleted_at.is_(None))
        .limit(50)
    )
    users = result.scalars().all()
    for user in users:
        if user.token_api_hash and bcrypt.checkpw(
            x_api_key.encode(), user.token_api_hash.encode()
        ):
            return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")
```

### `block.json` structure

```json
{
  "apiVersion": 3,
  "name": "comprobantes-ocr/upload",
  "title": "Comprobante Upload",
  "category": "widgets",
  "icon": "media-document",
  "textdomain": "comprobantes-ocr",
  "editorScript": "file:./build/index.js",
  "attributes": {
    "apiUrlOverride": { "type": "string", "default": "" }
  },
  "supports": { "html": false }
}
```

### Nonce Flow

```
PHP render (COCR_Shortcode::render()):
  wp_localize_script('cocr-upload-handler', 'COCR', [
      'ajaxUrl' => admin_url('admin-ajax.php'),
      'nonce'   => wp_create_nonce('cocr_upload_nonce'),
  ])

JS (upload-handler.js):
  body.append('nonce', COCR.nonce)
  body.append('action', 'cocr_upload')
  fetch(COCR.ajaxUrl, { method: 'POST', body })

PHP AJAX handler:
  check_ajax_referer('cocr_upload_nonce')   // dies on fail — no WP_Error
  current_user_can('upload_files')
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `plugin-wp/comprobantes-ocr/` (23 files) | **Create** | Full plugin — see directory structure above |
| `api/dependencies/auth_api_key.py` | **Create** | `require_api_key` FastAPI dependency |
| `api/routers/upload.py` | **Modify** | Replace `SYSTEM_USER_ID` with `usuario.id_usuario`; add `Depends(require_api_key)` |
| `api/routers/history.py` | **Modify** | Replace `SYSTEM_USER_ID`; add `Depends(require_api_key)` |
| `api/routers/validate.py` | **Modify** | Add `Depends(require_api_key)` (SYSTEM_USER_ID unused here but audit trail uses auth user) |
| `.github/workflows/build-plugin.yml` | **Create** | ZIP + GitHub Release on `v*` tags |

---

## Security Architecture

### Output escaping map

| Context | Function |
|---------|----------|
| HTML text nodes | `esc_html()` |
| HTML attributes | `esc_attr()` |
| URLs in `href`/`src` | `esc_url()` |
| JS string literals | `esc_js()` |
| SQL | `$wpdb->prepare()` (not used in Fase 3 — no direct DB queries) |

### Input sanitization map

| Source | Function |
|--------|----------|
| `$_POST['api_url']` | `esc_url_raw()` |
| `$_POST['api_key']` | `sanitize_text_field()` |
| `$_POST['timeout']` | `absint()` |
| Uploaded file | `wp_check_filetype_and_ext()` + whitelist `['jpg','jpeg','png','pdf']` |

### API key storage

Stored as plaintext in `wp_options` (option name: `comprobantes_api_key`). Transmitted exclusively over HTTPS. Plugin enforces HTTPS for `api_url` via validation in `COCR_Settings::sanitize_options()` (`strpos($url, 'https://') === 0` or admin notice warning).

---

## CI/CD Workflow

```yaml
# .github/workflows/build-plugin.yml
name: Build Plugin ZIP
on:
  push:
    tags: ['v*']
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
        working-directory: plugin-wp/comprobantes-ocr/block
      - run: npm run build
        working-directory: plugin-wp/comprobantes-ocr/block
      - name: Create ZIP (exclude src, node_modules, assets, .git)
        run: |
          cd plugin-wp
          zip -r ../comprobantes-ocr.zip comprobantes-ocr/ \
            --exclude "*/block/src/*" \
            --exclude "*/block/node_modules/*" \
            --exclude "*/assets/*" \
            --exclude "*/.git*"
      - uses: softprops/action-gh-release@v2
        with:
          files: comprobantes-ocr.zip
```

---

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| PHP unit | None in Fase 3 | No PHPUnit runner configured (see `openspec/config.yaml`) — add in Fase 5 |
| PHP manual | Plugin activation/deactivation, shortcode render, AJAX handler, Plugin Check 0 critical errors | Run Plugin Check plugin in WP admin before PR-D merge |
| Python — new `require_api_key` | 401 on missing key, 401 on wrong key, 200 on valid key | New pytest test file `api/tests/test_auth_api_key.py` using `dependency_overrides` |
| Python — regression (352 existing tests) | All existing endpoints continue to pass | Override pattern: `app.dependency_overrides[require_api_key] = lambda: mock_usuario` in conftest; `mock_usuario` is a `Usuario` instance with `id_usuario=SYSTEM_USER_ID` to preserve existing assertions |

**Override pattern for existing tests:**

```python
# In conftest.py — add alongside existing get_session override
from dependencies.auth_api_key import require_api_key
from models.seed import SYSTEM_USER_ID

@pytest_asyncio.fixture
async def client(db_session):
    mock_user = Usuario(id_usuario=SYSTEM_USER_ID, ...)
    async def _override_get_session():
        yield db_session
    def _override_auth():
        return mock_user
    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[require_api_key] = _override_auth
    ...
```

---

## Migration / Rollout

No DB migration required for Fase 3. `token_api_hash` column already exists in `usuarios` table (nullable). A seed script or manual SQL sets `token_api_hash = bcrypt.hashpw(plain_key, bcrypt.gensalt())` for the user that will own the plugin's API key. Key provisioning UI (`POST /auth/generate-key`) is out of scope — Fase 4.

**Rollback:** Deactivate plugin from WP admin (zero residue after `uninstall.php`). Revert `api/dependencies/auth_api_key.py` deletion and restore `SYSTEM_USER_ID` imports in the three routers — single `git revert` on PR-A.

---

## Open Questions

- [ ] **Who runs the `bcrypt.hashpw` seed for the initial API key?** Fase 3 ships no key-generation endpoint — this must be done manually via `psql` or a one-off script. Document this in `readme.txt` → "Getting Started" section. Not a blocker for implementation.
- [ ] **`comprobantes_timeout` default 30s** — verify FastAPI/uvicorn worker timeout aligns (gunicorn default is 30s; if worker timeout < 30s, PHP will get a 504 before WP timeout fires). Confirm in Fase 3 deployment notes.
