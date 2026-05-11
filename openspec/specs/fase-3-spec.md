# Fase 3 — Plugin WordPress + API Key Auth: Especificación

**Change:** `fase-3-plugin-wp`
**Date:** 2026-05-10
**Phase:** Spec
**Mode:** openspec

---

## CAP-1: wp-plugin-comprobantes-ocr

### Requirement R-01: Plugin Entry Point and Scaffold

The plugin entry point `comprobantes-ocr.php` MUST include a valid GPL-2.0-or-later header declaring `Plugin Name: Comprobantes OCR`, `Requires at least: 6.5`, `Requires PHP: 8.0`, `Version: 1.0.0`, and `Text Domain: comprobantes-ocr`.

`uninstall.php` MUST call `delete_option()` for `comprobantes_api_url`, `comprobantes_api_key`, and `comprobantes_timeout` when the plugin is uninstalled.

All PHP functions MUST be prefixed `cocr_`, all classes `COCR_`, all constants `COCR_`.

#### Scenario: Plugin activates without PHP errors on WP 6.5+

- GIVEN WordPress 6.5+ with PHP 8.0+ and the plugin ZIP installed
- WHEN the plugin is activated
- THEN no PHP fatal errors or warnings appear
- AND the plugin appears in the active plugins list

#### Scenario: Uninstall removes all options

- GIVEN the plugin is installed and options `comprobantes_api_url`, `comprobantes_api_key`, `comprobantes_timeout` are stored
- WHEN the plugin is deleted via WP admin (triggering `uninstall.php`)
- THEN all three options are removed from the database
- AND no residue remains in `wp_options`

---

### Requirement R-02: COCR_API_Client::upload_slip Return Contract

`COCR_API_Client::upload_slip(file_path, api_url, api_key, timeout)` MUST return a structured PHP array with keys: `status` (one of `valid`, `sospechoso`, `duplicado`, `error`), `hash` (string), `id` (string), `message` (string).

On any failure the method MUST return `WP_Error` (MUST NOT return raw PHP errors or die/exit).

#### Scenario: Successful upload returns structured array

- GIVEN a valid JPEG file at `file_path` and a reachable API at `api_url`
- WHEN `COCR_API_Client::upload_slip()` is called
- THEN the return value is a PHP array with `status`, `hash`, `id`, and `message` keys populated
- AND `status` is one of `valid`, `sospechoso`, `duplicado`

---

### Requirement R-03: COCR_API_Client HTTP Transport and Error Taxonomy

`COCR_API_Client` MUST use `wp_remote_post()` with `multipart/form-data`, send `X-API-Key` as a request header, and apply a configurable `timeout` (default 30 seconds, range 5–120).

Error mapping MUST be:

| Condition | Result |
|-----------|--------|
| Network/DNS failure | `WP_Error` code `cocr_network_error` |
| HTTP 4xx response | `WP_Error` code `cocr_client_error` + HTTP status in data |
| HTTP 5xx response | `WP_Error` code `cocr_server_error` + retry hint in message |
| Non-JSON or malformed JSON body | `WP_Error` code `cocr_invalid_response` |

The client MUST NEVER use direct `cURL` calls.

#### Scenario: Network error returns WP_Error cocr_network_error

- GIVEN `api_url` points to an unreachable host
- WHEN `upload_slip()` is called
- THEN a `WP_Error` is returned with code `cocr_network_error`

#### Scenario: HTTP 401 from API returns WP_Error cocr_client_error

- GIVEN the API responds with HTTP 401
- WHEN `upload_slip()` is called
- THEN a `WP_Error` is returned with code `cocr_client_error`
- AND the WP_Error data includes the HTTP status code

#### Scenario: HTTP 500 returns WP_Error with retry hint

- GIVEN the API responds with HTTP 500
- WHEN `upload_slip()` is called
- THEN a `WP_Error` is returned with code `cocr_server_error`
- AND the message includes a retry hint

#### Scenario: API returns malformed JSON returns WP_Error cocr_invalid_response

- GIVEN the API responds with HTTP 200 but a non-JSON body
- WHEN `upload_slip()` is called
- THEN a `WP_Error` is returned with code `cocr_invalid_response`

---

### Requirement R-04: Admin Settings Page

The plugin MUST register a settings page at `Settings > Comprobantes OCR` using the WordPress Settings API.

Fields: `comprobantes_api_url` (sanitized via `esc_url_raw()`), `comprobantes_api_key` (sanitized via `sanitize_text_field()`, displayed masked), `comprobantes_timeout` (sanitized via `absint()`, valid range 5–120).

A "Test Connection" button MUST trigger an AJAX call that performs `GET /health` and displays the inline result (success/failure).

Access to the page MUST require `current_user_can('manage_options')`.

#### Scenario: Settings page renders for admin

- GIVEN a logged-in user with `manage_options` capability
- WHEN they navigate to `Settings > Comprobantes OCR`
- THEN the settings page renders with API URL, API Key, and Timeout fields

#### Scenario: Non-admin cannot access settings page

- GIVEN a logged-in user WITHOUT `manage_options` capability
- WHEN they navigate to the settings page URL
- THEN WordPress returns a permissions error (no settings rendered)

#### Scenario: SQL injection in API URL field is sanitized

- GIVEN an attacker submits `api_url = "https://evil.com' OR '1'='1"`
- WHEN the settings form is saved
- THEN `esc_url_raw()` strips the injection and stores a valid URL only

#### Scenario: Test Connection AJAX returns success result inline

- GIVEN valid `api_url` and `api_key` are saved, API `/health` returns 200
- WHEN the admin clicks "Test Connection"
- THEN the AJAX response shows an inline success message without page reload

#### Scenario: Missing nonce on settings form returns 403

- GIVEN a forged POST request to save settings without a valid nonce
- WHEN the request reaches the settings handler
- THEN WordPress rejects with a 403 / `check_admin_referer` failure

---

### Requirement R-05: Shortcode [comprobante_upload]

The shortcode `[comprobante_upload]` MUST render a drag-and-drop file upload area that accepts `image/jpeg`, `image/png`, and `application/pdf` with a max size of 10 MB.

On submit the form MUST send the file via `admin-ajax.php` to the `cocr_upload_slip` action.

The AJAX handler MUST call `check_ajax_referer('cocr_upload_slip')` and `current_user_can('upload_files')` before processing.

#### Scenario: Valid JPEG upload via shortcode triggers AJAX action

- GIVEN the shortcode is rendered on a page and a user uploads a valid JPEG ≤ 10 MB
- WHEN the form is submitted
- THEN a POST request is sent to `admin-ajax.php?action=cocr_upload_slip` with the file and nonce
- AND the semaphore result is displayed

#### Scenario: File exceeding 10 MB is rejected client-side

- GIVEN a user selects a file larger than 10 MB
- WHEN the upload is attempted
- THEN client-side validation rejects the file before sending
- AND an error message is displayed to the user

#### Scenario: Wrong MIME type is rejected

- GIVEN a user selects a `.exe` file
- WHEN the upload is submitted
- THEN the file is rejected (client-side accept filter and/or server-side validation)

#### Scenario: Missing nonce on AJAX request returns 403

- GIVEN a forged POST to `admin-ajax.php?action=cocr_upload_slip` without a valid nonce
- WHEN the request reaches the AJAX handler
- THEN `check_ajax_referer` fails and the response is a 403 / `-1` WP AJAX error

---

### Requirement R-06: Traffic-Light Semaphore

`result-display.js` MUST render a traffic-light semaphore using CSS transitions:

| API `status` | Color | State |
|---|---|---|
| `valid` | Verde | Approved |
| `sospechoso` | Amarillo | Under review |
| `duplicado` or `error` | Rojo | Rejected |

The transition MUST be animated (CSS `transition` property, minimum 300ms).

#### Scenario: valid status shows green semaphore

- GIVEN the AJAX response contains `status: "valid"`
- WHEN `result-display.js` processes the response
- THEN the semaphore DOM element displays the verde state with CSS transition

#### Scenario: duplicado status shows red semaphore

- GIVEN the AJAX response contains `status: "duplicado"`
- WHEN `result-display.js` processes the response
- THEN the semaphore DOM element displays the rojo state

---

### Requirement R-07: Gutenberg Block

The Gutenberg block `comprobantes-ocr/upload` MUST be declared in `block/block.json` with `apiVersion: 3` and MUST be functionally equivalent to the shortcode `[comprobante_upload]`.

The block MUST be built using `@wordpress/scripts ^30.x` with source in `block/src/` and output in `block/build/`.

#### Scenario: Block appears in block inserter

- GIVEN WordPress 6.5+ with the plugin active
- WHEN the block editor is opened
- THEN the `comprobantes-ocr/upload` block is available in the inserter

#### Scenario: Block renders the same upload UI as the shortcode

- GIVEN the block is inserted into a post and saved
- WHEN a visitor views the post frontend
- THEN the rendered HTML contains the same drag-and-drop upload form as the shortcode output

---

### Requirement R-08: Admin History Widget

The history widget in wp-admin MUST call `GET /history?limit=20` and display the last 20 comprobantes in a table with columns: `fecha`, `banco`, `monto`, `estado` (colored badge), `hash` (truncated to 8 chars).

Access MUST require `current_user_can('manage_options')`.

All output MUST be escaped with `esc_html()`.

#### Scenario: History widget renders 20 rows for admin

- GIVEN the API returns 20 history records and the user has `manage_options`
- WHEN the history widget page loads
- THEN 20 rows are displayed with fecha, banco, monto, estado badge, and truncated hash columns

#### Scenario: API error on history fetch shows graceful error message

- GIVEN the API returns a network error or 5xx
- WHEN the history widget attempts to load
- THEN a user-friendly error message is displayed (no raw PHP error/stack trace)

#### Scenario: History table output is properly escaped

- GIVEN a history record with `banco = "<script>alert(1)</script>"`
- WHEN the history widget renders the table row
- THEN the output is `&lt;script&gt;alert(1)&lt;/script&gt;` (escaped via `esc_html()`)

---

### Requirement R-09: WooCommerce Hook

The class `COCR_Woo_Hook` MUST hook into `woocommerce_order_status_completed` and call `POST /upload-slip/async` if the order has a comprobante attachment.

The `task_id` from the async response MUST be stored in order meta as `_cocr_task_id` via `update_post_meta()`.

`COCR_Woo_Hook` MUST only load if `class_exists('WooCommerce')` is true.

#### Scenario: Hook fires on order completion with attachment and stores task_id

- GIVEN WooCommerce is active and an order transitions to `completed` with a comprobante attachment
- WHEN `woocommerce_order_status_completed` fires
- THEN `POST /upload-slip/async` is called
- AND the returned `task_id` is saved in `_cocr_task_id` order meta

#### Scenario: WooCommerce absent — class does not load

- GIVEN WooCommerce is NOT installed or active (`class_exists('WooCommerce')` returns false)
- WHEN the plugin loads
- THEN `COCR_Woo_Hook` class is never instantiated
- AND no fatal errors occur

#### Scenario: Hook fires on order without comprobante attachment — no API call

- GIVEN an order transitions to `completed` with no comprobante attachment
- WHEN `woocommerce_order_status_completed` fires
- THEN `POST /upload-slip/async` is NOT called

---

### Requirement R-10: Internationalization

All user-visible PHP strings MUST be wrapped in `__()` or `_e()` with domain `comprobantes-ocr`.

`load_plugin_textdomain('comprobantes-ocr', ...)` MUST be called on the `plugins_loaded` hook.

Language files MUST include: `languages/comprobantes-ocr.pot`, `es_MX.po/.mo`, `en_US.po/.mo`.

#### Scenario: Plugin strings are translateable via .pot

- GIVEN the `.pot` file is generated from the plugin source
- WHEN it is loaded in a translation tool (Poedit / GlotPress)
- THEN all user-visible strings appear as translatable entries
- AND no hardcoded untranslated string appears in plugin output

#### Scenario: Locale switch to es_MX uses Spanish translations

- GIVEN WordPress is set to `es_MX` locale and the `es_MX.mo` file is present
- WHEN the plugin settings page renders
- THEN all UI labels appear in Spanish

---

### Requirement R-11: WP.org readme.txt

`readme.txt` MUST follow the WP.org SVN format with sections: `Description`, `Installation`, `FAQ`, `Screenshots`, `Changelog`, declaring `Tested up to: 6.5`.

#### Scenario: readme.txt parses correctly in Plugin Directory parser

- GIVEN the `readme.txt` is submitted to the WP.org parser
- WHEN the parser reads the file
- THEN all required sections are detected and no parse errors are reported

---

### Requirement R-12: Plugin Check Compliance

Running WordPress Plugin Check on the plugin MUST produce 0 critical errors and MUST NOT exceed 3 warnings (block-related notices are acceptable).

#### Scenario: Plugin Check passes with 0 critical errors

- GIVEN the plugin ZIP is installed on a fresh WordPress 6.5 instance
- WHEN Plugin Check is run
- THEN the report shows 0 critical errors
- AND ≤ 3 warnings (block notices acceptable)

---

### Requirement R-13: Uninstall Cleanup

`uninstall.php` MUST remove all plugin options via `delete_option()`. The file MUST check `defined('WP_UNINSTALL_PLUGIN')` before executing.

#### Scenario: Uninstall guard prevents direct file execution

- GIVEN `uninstall.php` is accessed directly (not via WP admin delete flow)
- WHEN the file is executed
- THEN the `WP_UNINSTALL_PLUGIN` check fails and no options are deleted

---

## CAP-2: fastapi-api-key-auth

### Requirement R-14: require_api_key FastAPI Dependency

`api/dependencies/auth_api_key.py` MUST expose a FastAPI dependency `require_api_key` that reads the `X-API-Key` request header, queries the `usuarios` table to find a `Usuario` where `bcrypt.checkpw(plain_key, token_api_hash)` returns `True`, and returns the `Usuario` object.

The `id_usuario` from the resolved `Usuario` MUST replace the `SYSTEM_USER_ID` hardcode in `upload.py`.

#### Scenario: Valid API key resolves to Usuario object

- GIVEN a request with `X-API-Key: <valid_plain_key>` where a `Usuario` row has `bcrypt.checkpw(plain_key, token_api_hash) == True`
- WHEN `require_api_key` is resolved by FastAPI
- THEN the dependency returns the `Usuario` object
- AND the endpoint receives `id_usuario = usuario.id_usuario`

#### Scenario: Authenticated upload uses resolved id_usuario not SYSTEM_USER_ID

- GIVEN a valid API key resolves to `usuario.id_usuario = uuid-X`
- WHEN `POST /upload-slip` is called
- THEN the created `Comprobante` row has `id_usuario = uuid-X`
- AND `SYSTEM_USER_ID` is never used

---

### Requirement R-15: Missing API Key Returns 401

If the `X-API-Key` header is absent or empty, `require_api_key` MUST raise `HTTPException(status_code=401, detail="API key required")`.

#### Scenario: No X-API-Key header returns 401

- GIVEN a request to `POST /upload-slip` with no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 401 with body `{"detail": "API key required"}`

#### Scenario: Empty X-API-Key header returns 401

- GIVEN a request with `X-API-Key: ""` (empty string)
- WHEN the endpoint is called
- THEN the response is HTTP 401 with body `{"detail": "API key required"}`

---

### Requirement R-16: Invalid API Key Returns 401 (Timing-Safe)

If the key is not found in the database or `bcrypt.checkpw` returns `False`, `require_api_key` MUST raise `HTTPException(status_code=401, detail="Invalid API key")`.

The error response MUST NOT distinguish between "key not found" and "wrong key" (timing-safe — prevents user enumeration).

#### Scenario: Unknown API key returns 401 Invalid API key

- GIVEN a request with `X-API-Key: nonexistent-key`
- WHEN `require_api_key` is resolved
- THEN the response is HTTP 401 with body `{"detail": "Invalid API key"}`

#### Scenario: Key exists but bcrypt mismatch returns 401 Invalid API key

- GIVEN a `Usuario` row exists but `bcrypt.checkpw(submitted_key, token_api_hash)` is `False`
- WHEN `require_api_key` is resolved
- THEN the response is HTTP 401 with body `{"detail": "Invalid API key"}`
- AND the response is indistinguishable from the "not found" case

---

### Requirement R-17: Protected Endpoints Require API Key

The following endpoints MUST declare `Depends(require_api_key)`:

- `POST /upload-slip`
- `POST /upload-slip/async`
- `GET /history`
- `POST /validate/{id}`
- `GET /report`

`GET /health` MUST remain public (no auth dependency).

#### Scenario: GET /health is accessible without API key

- GIVEN a request to `GET /health` with no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 200 (health status)

#### Scenario: GET /history without API key returns 401

- GIVEN a request to `GET /history` with no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 401

#### Scenario: GET /report without API key returns 401

- GIVEN a request to `GET /report` with no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 401

---

### Requirement R-18: Existing Tests Continue Passing (Regression Gate)

All 352 existing pytest tests MUST continue passing after `require_api_key` is added to protected endpoints.

Existing tests MUST mock or override the dependency using FastAPI's `app.dependency_overrides` mechanism rather than sending real API keys.

#### Scenario: Test suite passes after auth middleware is added

- GIVEN `require_api_key` is injected into all protected endpoints
- WHEN the full pytest suite runs with `dependency_overrides[require_api_key] = lambda: mock_usuario`
- THEN all 352 existing tests pass
- AND no new test failures are introduced by the auth layer

#### Scenario: Test without override fails with 401 (proves auth is active)

- GIVEN a test that calls `POST /upload-slip` without a dependency override AND without an `X-API-Key` header
- WHEN the test runs
- THEN the response is HTTP 401 (confirming auth is enforced)

---

## CAP-3: github-actions-plugin-zip

### Requirement R-19: Workflow Trigger

`.github/workflows/build-plugin.yml` MUST define a workflow that triggers on `push` events for tags matching the pattern `v*`.

#### Scenario: Push of tag v1.0.0 triggers the workflow

- GIVEN a commit is tagged `v1.0.0` and pushed to the repository
- WHEN GitHub Actions processes the push event
- THEN the `build-plugin` workflow is triggered
- AND the workflow runs to completion

#### Scenario: Push to a branch (not a tag) does NOT trigger the workflow

- GIVEN a commit is pushed to the `main` branch (no tag)
- WHEN GitHub Actions processes the push event
- THEN the `build-plugin` workflow is NOT triggered

---

### Requirement R-20: Build, ZIP, and Release Attachment

The workflow MUST execute in order: checkout → Node.js 20 setup → `npm ci` in `plugin-wp/comprobantes-ocr/block/` → `npm run build` → create ZIP of `plugin-wp/comprobantes-ocr/` excluding `block/src/`, `block/node_modules/`, and `assets/` → attach the ZIP to the GitHub Release created from the tag.

#### Scenario: ZIP is created and attached to GitHub Release on tag push

- GIVEN tag `v1.0.0` is pushed and the workflow runs
- WHEN all steps complete successfully
- THEN a GitHub Release for `v1.0.0` is created
- AND `comprobantes-ocr.zip` is attached as a release asset

#### Scenario: ZIP excludes block/src/, block/node_modules/, assets/

- GIVEN the workflow runs and creates the ZIP
- WHEN the ZIP contents are inspected
- THEN `block/src/` is absent
- AND `block/node_modules/` is absent
- AND `assets/` (WP.org directory assets) is absent
- AND `block/build/` IS present (compiled output)

#### Scenario: npm build failure aborts the workflow

- GIVEN `npm run build` exits with a non-zero code
- WHEN the workflow runs
- THEN the workflow fails and no ZIP is created
- AND no GitHub Release is published

---

## MODIFIED (Delta): upload-slip API Endpoints

> **Reference:** `openspec/specs/fase-2-spec.md` CAP-06 — Requirement: Async Pipeline Task & Report Aggregation Endpoint

### Requirement: Upload Endpoints Require API Key Auth
(Previously: `POST /upload-slip` and `POST /upload-slip/async` accepted requests without authentication; `SYSTEM_USER_ID` was hardcoded)

`POST /upload-slip` and `POST /upload-slip/async` MUST validate the `X-API-Key` header via `require_api_key` before executing the pipeline. The `id_usuario` from the resolved `Usuario` MUST be used when creating the `Comprobante` record, replacing the `SYSTEM_USER_ID` constant.

`GET /history`, `POST /validate/{id}`, and `GET /report` MUST also require `require_api_key`.

#### Scenario: Unauthenticated upload returns 401 (regression protection)

- GIVEN a request to `POST /upload-slip` with a valid file but no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 401 with `{"detail": "API key required"}`
- AND no Comprobante record is created

#### Scenario: Authenticated upload uses resolved id_usuario (replaces SYSTEM_USER_ID)

- GIVEN a valid API key resolves to `Usuario` with `id_usuario = uuid-A`
- WHEN `POST /upload-slip` processes the file
- THEN the created `Comprobante.id_usuario = uuid-A`
- AND `SYSTEM_USER_ID` is no longer referenced in the upload pipeline

#### Scenario: Async upload endpoint also enforces auth

- GIVEN a request to `POST /upload-slip/async` with no `X-API-Key` header
- WHEN the endpoint is called
- THEN the response is HTTP 401

---

## Constraints and Cross-Cutting Rules

| Rule | Source |
|------|--------|
| All PHP input sanitized: `sanitize_text_field()`, `absint()`, `esc_url_raw()` | WP standards |
| All PHP output escaped: `esc_html()`, `esc_attr()`, `esc_url()` | WP standards |
| Nonces used on ALL form submissions and AJAX actions | WP standards |
| `current_user_can()` checked before every admin action | WP standards |
| `wp_remote_post()` ONLY — never direct cURL | WP standards |
| `load_plugin_textdomain()` on `plugins_loaded` | WP standards |
| `register_rest_route()` with `permission_callback` if REST routes added | WP REST API |
| FastAPI: async endpoints, Pydantic v2, Annotated DI | Project standard |
| pytest: `asyncio_mode=auto`, parametrize table tests | Project standard |
| bcrypt timing-safe comparison — no early-exit on key mismatch | Security |
| Block `apiVersion: 3`, built with `@wordpress/scripts ^30.x` | WP block standard |
