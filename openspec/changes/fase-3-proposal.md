# Proposal: Fase 3 — Plugin WordPress Gratuito (`comprobantes-ocr`)

**Date:** 2026-05-10
**Change:** `fase-3-plugin-wp`
**Status:** Ready for Spec

---

## Intent

Build a WP.org-publishable WordPress plugin (`comprobantes-ocr`) that exposes the FastAPI OCR/duplicate-detection backend to any WordPress site. Simultaneously harden the FastAPI layer with a minimal API-key middleware so the plugin ships as a secure product from day one.

This closes the gap between a working backend (Fase 2 complete) and the first real user-facing deliverable of the freemium model.

---

## Scope

### In Scope

- **Plugin PHP scaffold** — entry point (`comprobantes-ocr.php`), `uninstall.php`, GPL header, WP.org `readme.txt`, `Requires PHP: 8.0`
- **`COCR_API_Client`** — `wp_remote_post()` / `wp_remote_get()`, `X-API-Key` header, `WP_Error` taxonomy (network / 4xx / 5xx / invalid-json)
- **Admin settings page** — `COCR_Settings` via Settings API; fields: `comprobantes_api_url`, `comprobantes_api_key`, `comprobantes_timeout`; AJAX "Test Connection" button
- **Shortcode `[comprobante_upload]`** — `COCR_Shortcode` (PHP class) + `upload-handler.js` (AJAX fetch to `admin-ajax.php`) + `result-display.js` (traffic-light semaphore)
- **Gutenberg block** — `COCR_Gutenberg`, `block/block.json`, JSX source in `block/src/`, built via `@wordpress/scripts ^30.x`
- **History widget** — `admin/history-widget.php`, calls `GET /history?limit=20`
- **WooCommerce hook** — `COCR_Woo_Hook`, `woocommerce_order_status_completed`, async upload, `task_id` stored in order meta; loads only if `class_exists('WooCommerce')`
- **Security** — nonces (`wp_create_nonce` / `check_ajax_referer`), `sanitize_text_field()`, `esc_html()` / `esc_attr()` / `esc_url()`, `current_user_can()` — embedded in every component, NOT a final sweep task
- **i18n** — `load_plugin_textdomain()` on `plugins_loaded`; `.pot` + `es_MX` / `en_US` `.po/.mo` (~30–40 strings)
- **WP.org assets** — `assets/banner-1544x500.png`, `icon-256x256.png`, `screenshot-1.png`
- **GitHub Actions ZIP** — `build-plugin.yml`, triggers on `v*` tags, attaches ZIP to Release
- **FastAPI API-key middleware** — `api/dependencies/auth_api_key.py` (~80 LOC); validates `X-API-Key` via `bcrypt.checkpw` against `usuarios.token_api_hash`; replaces `SYSTEM_USER_ID` hardcode

### Out of Scope

- JWT authentication (Fase 4)
- `POST /auth/generate-key` endpoint (Fase 4 — key provisioning UI)
- Multi-tenant / `organization_id` filtering (Fase 4)
- Stripe / payments (Fase 4)
- Polling UI for Celery `task_id` status (Fase 4 webhooks)
- WooCommerce admin panel integration (future extension)

---

## Capabilities

> Contract for sdd-spec.

### New Capabilities

- `wp-plugin-comprobantes-ocr`: Full plugin: scaffold, API client, settings, shortcode, Gutenberg block, history widget, WooCommerce hook, i18n, WP.org assets
- `fastapi-api-key-auth`: Minimal `X-API-Key` middleware; bcrypt validation against `usuarios.token_api_hash`
- `github-actions-plugin-zip`: CI job that builds and releases the plugin ZIP on version tags

### Modified Capabilities

- `upload-slip` (`openspec/specs/fase-2-spec.md`): All upload/validate/history endpoints now require `X-API-Key` header validated by the new middleware; `SYSTEM_USER_ID` hardcode is removed

---

## Approach

- **PHP**: Native WP 6.5+, no frameworks. Prefix `COCR_` (constants), `cocr_` (functions), class prefix `COCR_`. Slug: `comprobantes-ocr`.
- **JS (vanilla)**: `upload-handler.js` and `result-display.js` are plain ES6, enqueued via `wp_enqueue_scripts`. No build step for public JS.
- **Gutenberg block**: JSX built with `wp-scripts build`. Build output (`block/build/`) versioned in Git; CI runs `npm ci && npm run build` before zipping.
- **Upload transport**: `multipart/form-data` via `wp_remote_post()`. Binary body constructed using WordPress's `WP_Http` boundary format.
- **FastAPI auth**: Single `Depends(require_api_key)` injected into all protected routers. No JWT, no sessions — stateless header check.
- **Delivery**: Chained PRs to keep reviews under 400 lines each.

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `plugin-wp/comprobantes-ocr/` | **New** | Full plugin directory (~23 files) |
| `plugin-wp/comprobantes-ocr/block/` | **New** | Gutenberg block + `package.json` + `block.json` + JSX src |
| `plugin-wp/comprobantes-ocr/languages/` | **New** | `.pot`, `.po`, `.mo` files |
| `plugin-wp/comprobantes-ocr/assets/` | **New** | WP.org directory assets (not in plugin ZIP) |
| `api/dependencies/auth_api_key.py` | **New** | `require_api_key` FastAPI dependency |
| `api/routers/upload.py` | **Modified** | Remove `SYSTEM_USER_ID` hardcode; inject `id_usuario` from API key |
| `api/routers/history.py` | **Modified** | Add `require_api_key` dependency |
| `api/routers/validate.py` | **Modified** | Add `require_api_key` dependency |
| `.github/workflows/build-plugin.yml` | **New** | ZIP build + GitHub Release on `v*` tags |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `wp_remote_post()` multipart binary encoding non-trivial | Med | Use WP_Http boundary format; test with actual binary file early (PR-A) |
| Plugin Check rejects unescaped output or missing nonce | Med | Apply escape + nonce from first line of code; run Plugin Check in PR-D before merge |
| Gutenberg `@wordpress/scripts` build step breaks CI | Med | Add `npm ci && npm run build` step in `build-plugin.yml`; pin `@wordpress/scripts ^30.x` |
| bcrypt validation adds latency per API request | Low | Single DB lookup; acceptable for API-key auth (not per-HTTP-request token rotation) |
| WooCommerce not present — class not found | Low | Guard with `class_exists('WooCommerce')` in entry point |

---

## Rollback Plan

- Plugin: deactivate and delete from WP admin — leaves no residue (`uninstall.php` drops all options).
- FastAPI middleware: revert `api/dependencies/auth_api_key.py` and restore `SYSTEM_USER_ID` hardcode in `upload.py` — single-commit revert on the API side.
- All changes are isolated to `plugin-wp/` and `api/dependencies/`; no core API logic is restructured.

---

## Dependencies

- WordPress 6.5+, PHP 8.0+ on target site
- Node.js 20+ with `npm` for Gutenberg build (CI only — not a runtime dependency)
- WP-CLI for generating `.pot` / `.mo` files (dev tooling)
- `passlib[bcrypt]` already in `api/requirements.txt` (Fase 2)
- WooCommerce optional — plugin degrades gracefully if absent

---

## Success Criteria

- [ ] Plugin installs from ZIP without PHP errors on WordPress 6.5+
- [ ] Shortcode `[comprobante_upload]` submits a real comprobante and renders the traffic-light result
- [ ] Gutenberg block appears in block editor and is functionally equivalent to the shortcode
- [ ] Plugin Check reports **0 critical errors**, ≤ 3 warnings
- [ ] WooCommerce hook fires on `order_status_completed` and stores `task_id` in order meta
- [ ] FastAPI rejects requests without a valid `X-API-Key` with HTTP 401
- [ ] GitHub Actions generates `comprobantes-ocr.zip` on a `v*` tag push and attaches to Release
- [ ] All existing `pytest` tests continue passing (regression gate)

---

## Delivery Plan (Chained PRs)

| PR | Contents | Est. LOC |
|----|----------|----------|
| **PR-A** | Scaffolding + `COCR_API_Client` + FastAPI auth middleware | ~380 |
| **PR-B** | Shortcode (PHP) + `upload-handler.js` + `result-display.js` + CSS | ~400 |
| **PR-C** | Gutenberg block (`block/`) + `COCR_Gutenberg` class | ~200 |
| **PR-D** | WooCommerce hook + i18n + WP.org assets + `readme.txt` + CI ZIP workflow | ~480 |

**Total estimated:** ~1,460 LOC across PHP, JS, Python, YAML
