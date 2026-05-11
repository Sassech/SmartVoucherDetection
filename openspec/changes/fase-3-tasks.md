# Tasks: Fase 3 — Plugin WordPress `comprobantes-ocr`

**Change:** `fase-3-plugin-wp`
**Date:** 2026-05-10
**Status:** Ready for Apply

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,460 (PHP + JS + Python + YAML) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR-A → PR-B → PR-C → PR-D (each targets `develop`) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-develop |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-develop
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| A | Scaffolding + API Client + FastAPI auth | PR-A | Base: `develop`; foundation for all PHP work |
| B | Shortcode + JS + CSS + Settings + History | PR-B | Base: `develop` (stacked on PR-A) |
| C | Gutenberg block (JSX + PHP class) | PR-C | Base: `develop` (stacked on PR-B) |
| D | WooCommerce + i18n + WP.org + CI + docs | PR-D | Base: `develop` (stacked on PR-C); final gate |

---

## PR-A: Scaffolding + API Client + FastAPI Auth (~380 LOC)

- [x] **A1** — Plugin scaffold
  - Files: `plugin-wp/comprobantes-ocr/comprobantes-ocr.php`, `uninstall.php`
  - Create GPL-2.0-or-later header with `Plugin Name: Comprobantes OCR`, `Requires at least: 6.5`, `Requires PHP: 8.0`, `Version: 1.0.0`, `Text Domain: comprobantes-ocr`; PSR-4 autoloader; activation/deactivation hooks (register hooks, no DB changes); load `COCR_Settings`, `COCR_Shortcode`, `COCR_Gutenberg`, `COCR_Woo_Hook` (guarded) on `plugins_loaded`
  - `uninstall.php`: check `defined('WP_UNINSTALL_PLUGIN')`; `delete_option()` for `comprobantes_api_url`, `comprobantes_api_key`, `comprobantes_timeout`
  - AC: Plugin activates on WP 6.5 + PHP 8.0 without fatal errors; all three options deleted on uninstall
  - Deps: none
  - Est: ~80 LOC

- [x] **A2** — `COCR_API_Client`
  - Files: `plugin-wp/comprobantes-ocr/includes/class-api-client.php`
  - Implement `upload_slip()`, `get_history()`, `test_connection()`, private `_build_multipart()`, private `_make_request()`; use `wp_remote_post()` / `wp_remote_get()` exclusively; send `X-API-Key` header; apply configurable `timeout` (default 30s, range 5–120); WP_Error taxonomy: `cocr_network_error`, `cocr_client_error` (4xx + HTTP status in data), `cocr_server_error` (5xx + retry hint), `cocr_invalid_response` (null json_decode), `cocr_file_unreadable`; `upload_slip()` returns `array{status, hash, id, message}` on success
  - AC: Calling with unreachable host → `WP_Error('cocr_network_error')`; HTTP 401 → `WP_Error('cocr_client_error')` with status in data; HTTP 500 → `WP_Error('cocr_server_error')` with retry hint; non-JSON body → `WP_Error('cocr_invalid_response')`; no direct `curl_*` calls anywhere in file
  - Deps: A1
  - Est: ~130 LOC

- [x] **A3** — `require_api_key` FastAPI dependency
  - Files: `api/dependencies/auth_api_key.py`
  - Async dependency; reads `X-API-Key` header via `Annotated[str, Header()]`; `SELECT * FROM usuarios WHERE deleted_at IS NULL LIMIT 50`; iterate with `bcrypt.checkpw(plain.encode(), hash.encode())`; return `Usuario` on match; raise `HTTPException(401, "API key required")` on missing/empty header; raise `HTTPException(401, "Invalid API key")` on no match — same message for "not found" and "wrong key" (timing-safe, no early exit distinction); add scalability comment: prefix column deferred to Fase 4
  - AC: Valid key → returns `Usuario`; no header → 401 "API key required"; wrong key → 401 "Invalid API key"; `detail` body is indistinguishable for not-found vs. mismatch
  - Deps: A1
  - Est: ~50 LOC

- [x] **A4** — Wire `require_api_key` into protected routers
  - Files: `api/routers/upload.py`, `api/routers/history.py`, `api/routers/validate.py`, `api/routers/report.py`
  - Add `usuario: Usuario = Depends(require_api_key)` to `POST /upload-slip`, `POST /upload-slip/async`, `GET /history`, `POST /validate/{id}`, `GET /report`; replace all `SYSTEM_USER_ID` references with `usuario.id_usuario`; `GET /health` receives NO auth dependency
  - AC: `GET /health` without key → 200; `GET /history` without key → 401; `POST /upload-slip` with valid key creates `Comprobante.id_usuario = usuario.id_usuario` (not `SYSTEM_USER_ID`)
  - Deps: A3
  - Est: ~40 LOC (modifications)

- [x] **A5** — Dev seed script
  - Files: `infra/scripts/seed_api_key.py`
  - Generates a `secrets.token_urlsafe(32)` key; bcrypt-hashes it; connects to DB via env vars (`DATABASE_URL`); `UPDATE usuarios SET token_api_hash = :hash WHERE email = 'system@local'`; prints plaintext key once to stdout with warning; exits non-zero if no row updated
  - AC: Running `uv run python infra/scripts/seed_api_key.py` prints a plaintext key; querying `usuarios` shows a non-null `token_api_hash`; script never stores plaintext anywhere
  - Deps: A3
  - Est: ~40 LOC

- [x] **A6** — Regression test gate (post-auth wiring)
  - Files: `api/tests/conftest.py`, `api/tests/test_auth_api_key.py`
  - In `conftest.py`: add `app.dependency_overrides[require_api_key] = lambda: mock_usuario` (where `mock_usuario.id_usuario = SYSTEM_USER_ID`) alongside existing `get_session` override; create `mock_usuario` fixture
  - In `test_auth_api_key.py`: test valid key → 200 (using real bcrypt hash in test DB); test missing header → 401 "API key required"; test wrong key → 401 "Invalid API key"; test `GET /health` no key → 200; test `POST /upload-slip` no override no key → 401 (proves auth is active)
  - AC: `cd api && uv run pytest tests/` passes all 352+ existing tests plus new auth tests; no regression failures
  - Deps: A4, A5
  - Est: ~70 LOC

---

## PR-B: Shortcode + JS + CSS (~400 LOC)

- [x] **B1** — `COCR_Settings`
  - Files: `plugin-wp/comprobantes-ocr/includes/class-settings.php`, `plugin-wp/comprobantes-ocr/admin/settings-page.php`
  - Register settings page at `Settings > Comprobantes OCR`; capability gate `current_user_can('manage_options')`; Settings API with group `cocr_options`; `register_setting()` for `comprobantes_api_url` (`esc_url_raw()`), `comprobantes_api_key` (`sanitize_text_field()`, render masked), `comprobantes_timeout` (`absint()`, clamp 5–120); render via `admin/settings-page.php` template with nonce via `settings_fields()`; optional HTTPS warning if `api_url` not starting with `https://`
  - AC: Admin sees settings page with 3 fields; non-admin gets WP permissions error; SQL injection in `api_url` stripped by `esc_url_raw()`; forged POST without nonce triggers `check_admin_referer` failure
  - Deps: A1, A2
  - Est: ~90 LOC

- [x] **B2** — "Test Connection" AJAX handler
  - Files: `plugin-wp/comprobantes-ocr/includes/class-settings.php` (addition)
  - Register `wp_ajax_cocr_ajax_test_connection`; verify nonce `cocr_test_connection`; `current_user_can('manage_options')`; call `COCR_API_Client::test_connection()`; return `wp_send_json_success(['ok' => true, 'detail' => __('Connected', 'comprobantes-ocr')])` or `wp_send_json_error(['ok' => false, 'detail' => $error->get_error_message()])`
  - AC: Valid credentials + reachable API → JSON `{ok: true}`; unreachable API → JSON `{ok: false}` with detail; missing nonce → WP AJAX `-1`
  - Deps: B1
  - Est: ~30 LOC

- [x] **B3** — `COCR_Shortcode`
  - Files: `plugin-wp/comprobantes-ocr/includes/class-shortcode.php`
  - Register `[comprobante_upload]` via `add_shortcode()`; `render()`: if `!current_user_can('upload_files')` return `''`; `wp_enqueue_script('cocr-upload-handler', ...)`, `wp_enqueue_script('cocr-result-display', ...)`, `wp_enqueue_style('cocr-style', ...)`; `wp_localize_script('cocr-upload-handler', 'COCR', ['ajaxUrl' => admin_url('admin-ajax.php'), 'nonce' => wp_create_nonce('cocr_upload_nonce')])`; return upload form HTML with drag-and-drop area, `accept="image/jpeg,image/png,application/pdf"`, `data-max-size="10485760"`; register `wp_ajax_cocr_upload_slip` (logged-in only — no `wp_ajax_nopriv_`); AJAX handler: `check_ajax_referer('cocr_upload_nonce')`, `current_user_can('upload_files')`, `wp_check_filetype_and_ext()` whitelist `['jpg','jpeg','png','pdf']`, call `COCR_API_Client::upload_slip()`, return `wp_send_json_success/error()`
  - AC: Non-logged-in user → shortcode renders empty string; valid JPEG ≤10MB → AJAX fires; forged nonce → 403/-1; `.exe` file → rejected by accept filter
  - Deps: B1, A2
  - Est: ~100 LOC

- [x] **B4** — `upload-handler.js`
  - Files: `plugin-wp/comprobantes-ocr/public/upload-handler.js`
  - ES6; drag-and-drop events (`dragover`, `drop`), `<input type="file">` change handler; client-side validation: reject if `file.size > 10 * 1024 * 1024` with error message; reject if `file.type` not in `['image/jpeg','image/png','application/pdf']`; build `FormData(file, action='cocr_upload_slip', nonce=COCR.nonce)`; `fetch(COCR.ajaxUrl, {method:'POST', body: formData})`; on success pass JSON to `result-display.js`; show/hide progress indicator
  - AC: File >10MB → client-side error before fetch; `image/jpeg` file triggers fetch to `admin-ajax.php`; nonce value from `COCR.nonce` is included in FormData
  - Deps: B3
  - Est: ~60 LOC

- [x] **B5** — `result-display.js`
  - Files: `plugin-wp/comprobantes-ocr/public/result-display.js`
  - ES6; exports/exposes `renderResult(response)` function; maps `status: 'valid'` → verde state, `status: 'sospechoso'` → amarillo state, `status: 'duplicado' | 'error'` → rojo state; toggle CSS classes on semaphore DOM element; `transition` property min 300ms via added class; display `response.message` text below semaphore
  - AC: `{status:'valid'}` → verde class active; `{status:'duplicado'}` → rojo class active; DOM transition property ≥ 300ms (verifiable via CSS)
  - Deps: B4
  - Est: ~40 LOC

- [x] **B6** — `style.css`
  - Files: `plugin-wp/comprobantes-ocr/public/style.css`
  - Drag-and-drop upload area (dashed border, hover state, active state); semaphore container (3 circles: verde/amarillo/rojo); active state adds brightness, inactive circles dimmed; `transition: all 300ms ease` on semaphore lights; responsive (max-width: 100%); no external framework, no `!important` abuse
  - AC: CSS file has `.cocr-semaphore`, `.cocr-light-verde`, `.cocr-light-amarillo`, `.cocr-light-rojo` with `transition` ≥ 300ms; upload area has dashed border on hover
  - Deps: B3
  - Est: ~50 LOC

- [x] **B7** — `COCR_History_Widget` + template
  - Files: `plugin-wp/comprobantes-ocr/includes/class-history-widget.php`, `plugin-wp/comprobantes-ocr/admin/history-widget.php`
  - Register admin submenu page `comprobantes-ocr-history`; capability `current_user_can('manage_options')`; call `COCR_API_Client::get_history($api_url, $api_key, 20)`; on `WP_Error` show user-friendly message (no PHP stack trace); pass data to `admin/history-widget.php` template; template renders `<table>` with columns: `fecha`, `banco`, `monto`, `estado` (colored `<span>` badge), `hash` (substr 0–8 + `…`); ALL cells wrapped in `esc_html()`
  - AC: 20 rows rendered with all 5 columns; API WP_Error → friendly message displayed; `banco = "<script>alert(1)</script>"` → rendered as `&lt;script&gt;`; non-admin → WP permissions error
  - Deps: B1, A2
  - Est: ~80 LOC (combined)

---

## PR-C: Gutenberg Block (~200 LOC)

- [ ] **C1** — `block/package.json` + `block/block.json`
  - Files: `plugin-wp/comprobantes-ocr/block/package.json`, `plugin-wp/comprobantes-ocr/block/block.json`
  - `package.json`: `name: "comprobantes-ocr-block"`, `scripts: {build: "wp-scripts build", start: "wp-scripts start"}`, `devDependencies: {"@wordpress/scripts": "^30.x"}`
  - `block.json`: `apiVersion: 3`, `name: "comprobantes-ocr/upload"`, `title: "Comprobante Upload"`, `category: "widgets"`, `icon: "media-document"`, `textdomain: "comprobantes-ocr"`, `editorScript: "file:./build/index.js"`, `attributes: {apiUrlOverride: {type: "string", default: ""}}`, `supports: {html: false}`
  - AC: `npm ci && npm run build` in `block/` exits 0; `block.json` passes `@wordpress/scripts` block.json validation; `apiVersion` is `3`
  - Deps: A1
  - Est: ~30 LOC

- [ ] **C2** — `block/src/index.js`
  - Files: `plugin-wp/comprobantes-ocr/block/src/index.js`
  - `import { registerBlockType } from '@wordpress/blocks'`; import `Edit` from `./edit`; import `save` from `./save`; `registerBlockType('comprobantes-ocr/upload', { edit: Edit, save })` — metadata read from `block.json`
  - AC: Block registers without console errors; `wp.blocks.getBlockType('comprobantes-ocr/upload')` returns non-null in editor console
  - Deps: C1
  - Est: ~20 LOC

- [ ] **C3** — `block/src/edit.js`
  - Files: `plugin-wp/comprobantes-ocr/block/src/edit.js`
  - React functional component `Edit({ attributes, setAttributes })`; `InspectorControls` panel with `TextControl` for `apiUrlOverride` attribute; main canvas renders equivalent drag-and-drop upload area UI (mirrors shortcode output); uses `useBlockProps()`; strings wrapped in `__()` with domain `comprobantes-ocr`
  - AC: Block inserter shows `Comprobante Upload`; InspectorControls panel visible in sidebar with API URL Override field; canvas shows upload area preview
  - Deps: C2
  - Est: ~70 LOC

- [ ] **C4** — `block/src/save.js`
  - Files: `plugin-wp/comprobantes-ocr/block/src/save.js`
  - Export `save` function that returns `null` — dynamic block rendered server-side via `render_callback`
  - AC: `save()` returns `null`; block validates without "Block validation failed" error on frontend
  - Deps: C2
  - Est: ~10 LOC

- [ ] **C5** — `COCR_Gutenberg` PHP class
  - Files: `plugin-wp/comprobantes-ocr/includes/class-gutenberg.php`
  - `register_block_type()` with `plugin_dir_path(__FILE__) . '../block/'`; set `render_callback` to `[COCR_Shortcode::class, 'render']` (reuses shortcode output for frontend); enqueue `block/build/index.js` in editor via block registration (auto from `block.json` `editorScript`); verify `block/build/index.asset.php` exists before enqueue
  - AC: Block appears in block inserter on WP 6.5; frontend renders identical HTML to `[comprobante_upload]` shortcode; no `wp_enqueue_script` calls duplicate the block's asset
  - Deps: C1, B3
  - Est: ~40 LOC

- [ ] **C6** — Build and commit `block/build/`
  - Files: `plugin-wp/comprobantes-ocr/block/build/index.js`, `plugin-wp/comprobantes-ocr/block/build/index.asset.php`
  - Run `cd plugin-wp/comprobantes-ocr/block && npm ci && npm run build`; verify `build/index.js` and `build/index.asset.php` generated; add to Git (not in `.gitignore`); commit as part of PR-C
  - AC: `block/build/index.js` and `block/build/index.asset.php` present in repository; `git status` shows them tracked; `COCR_Gutenberg` can `require` `index.asset.php` without file-not-found error
  - Deps: C5
  - Est: ~0 LOC (build output; ~30 LOC generated)

---

## PR-D: WooCommerce + i18n + WP.org + CI (~480 LOC)

- [ ] **D1** — `COCR_Woo_Hook`
  - Files: `plugin-wp/comprobantes-ocr/includes/class-woo-hook.php`
  - Guard entire class file with `if (!class_exists('WooCommerce')) return;`; hook `woocommerce_order_status_completed` with priority 10; callback receives `$order_id`; get `WC_Order`; check for comprobante attachment in order meta or attached media; if found: call `COCR_API_Client::upload_slip_async()` (via `POST /upload-slip/async`); on success: `update_post_meta($order_id, '_cocr_task_id', $response['task_id'])`; on no attachment: no API call; on WP_Error: log via `error_log()`, no fatal
  - AC: WooCommerce active + order completed + attachment → `_cocr_task_id` meta stored; WooCommerce absent → class never instantiated, no error; order without attachment → no API call
  - Deps: A2, A1
  - Est: ~70 LOC

- [ ] **D2** — i18n strings + language files
  - Files: `plugin-wp/comprobantes-ocr/languages/comprobantes-ocr.pot`, `languages/comprobantes-ocr-es_MX.po`, `languages/comprobantes-ocr-es_MX.mo`, `languages/comprobantes-ocr-en_US.po`, `languages/comprobantes-ocr-en_US.mo`; all PHP source files (string wrapping pass)
  - Wrap all ~30–40 user-visible PHP strings in `__('…', 'comprobantes-ocr')` or `_e('…', 'comprobantes-ocr')`; ensure `load_plugin_textdomain('comprobantes-ocr', false, dirname(plugin_basename(__FILE__)) . '/languages/')` is called on `plugins_loaded` in entry point; run `wp i18n make-pot plugin-wp/comprobantes-ocr/ plugin-wp/comprobantes-ocr/languages/comprobantes-ocr.pot`; create `es_MX.po` with Spanish translations; compile `.mo` via `wp i18n make-mo`; create `en_US.po/.mo` as identity (source = translation)
  - AC: `.pot` file contains ≥30 translatable strings; WP locale `es_MX` renders Spanish labels on settings page; `en_US` `.mo` compiles without errors; no hardcoded untranslated UI string in rendered output
  - Deps: B1, B2, B3, B7, D1
  - Est: ~150 LOC (po/pot files)

- [ ] **D3** — WP.org assets + `readme.txt`
  - Files: `plugin-wp/comprobantes-ocr/assets/banner-1544x500.png`, `assets/icon-256x256.png`, `assets/screenshot-1.png`, `plugin-wp/comprobantes-ocr/readme.txt`
  - `readme.txt`: WP.org SVN format; required sections: `=== Plugin Name ===` header block (`Tested up to: 6.5`, `Requires at least: 6.5`, `Stable tag: 1.0.0`, `License: GPL-2.0-or-later`), `== Description ==`, `== Installation ==`, `== Getting Started ==` (include note: "Run `seed_api_key.py` to generate and store the first API key before activating the plugin"), `== FAQ ==`, `== Screenshots ==`, `== Changelog ==`; placeholder PNG assets (solid color acceptable for Fase 3)
  - AC: `readme.txt` passes WP.org readme validator (https://wordpress.org/plugins/about/validator/) with no required-field errors; all 3 asset files present at correct pixel dimensions
  - Deps: A1
  - Est: ~80 LOC

- [ ] **D4** — Plugin Check compliance
  - Files: (fixes across plugin source files as needed)
  - Install WP Plugin Check (via WP admin or CLI); run against `comprobantes-ocr`; fix ALL critical errors (0 tolerance); document any remaining warnings in a comment block at top of `PROGRESO.md`; acceptable: block-related notices ≤ 3 warnings total
  - AC: Plugin Check report shows 0 critical errors; ≤ 3 warnings (block notices acceptable); no `esc_html()` / nonce / `current_user_can()` violations remain
  - Deps: D2, D3, C6
  - Est: ~20 LOC (fixes)

- [ ] **D5** — `.github/workflows/build-plugin.yml`
  - Files: `.github/workflows/build-plugin.yml`
  - Trigger: `on: push: tags: ['v*']`; job `build` on `ubuntu-latest`; steps: `actions/checkout@v4` → `actions/setup-node@v4` (node-version: `'20'`) → `npm ci` (working-directory: `plugin-wp/comprobantes-ocr/block`) → `npm run build` (same) → ZIP step: `cd plugin-wp && zip -r ../comprobantes-ocr.zip comprobantes-ocr/ --exclude "*/block/src/*" --exclude "*/block/node_modules/*" --exclude "*/assets/*" --exclude "*/.git*"` → `actions/upload-artifact@v4` → `softprops/action-gh-release@v2` with `files: comprobantes-ocr.zip`; workflow fails and skips release if `npm run build` exits non-zero
  - AC: Pushing `v1.0.0` tag triggers workflow and attaches `comprobantes-ocr.zip` to GitHub Release; ZIP contains `block/build/` but NOT `block/src/`, `block/node_modules/`, `assets/`; `npm run build` failure → workflow fails, no release created
  - Deps: C6
  - Est: ~60 LOC

- [ ] **D6** — PROGRESO.md update + tag
  - Files: `PROGRESO.md`
  - Mark all Fase 3 tasks `[x]`; document Plugin Check warning count (from D4); add git tag `fase-3-completa` after PR-D merges to `develop`
  - AC: All Fase 3 checkboxes are `[x]` in `PROGRESO.md`; `git tag fase-3-completa` exists in repository
  - Deps: D4, D5
  - Est: ~20 LOC

---

## Dependency Graph

```
A1 ──► A2 ──► B1 ──► B2
  │       │       └──► B3 ──► B4 ──► B5
  │       │       └──► B7
  │       └──► D1
  └──► A3 ──► A4 ──► A6
           └──► A5 ──► A6
               C1 ──► C2 ──► C3
                          └──► C4
               C1 ──► C5 (needs B3)
               C5 ──► C6
          B1+B2+B3+B7+D1 ──► D2
          A1 ──► D3
          D2+D3+C6 ──► D4 ──► D6
          C6 ──► D5 ──► D6
```

---

## LOC Summary by PR Block

| PR | Tasks | Est. LOC |
|----|-------|----------|
| PR-A | A1–A6 | ~410 |
| PR-B | B1–B7 | ~450 |
| PR-C | C1–C6 | ~200 |
| PR-D | D1–D6 | ~400 |
| **Total** | **23 tasks** | **~1,460** |

> PR-A and PR-B both exceed the 400-line budget individually — chained PRs already chosen as mitigation. Each PR is a reviewable, independently deployable unit.
