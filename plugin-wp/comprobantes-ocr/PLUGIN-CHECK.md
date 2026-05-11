# Plugin Check Gate

Run before merging PR-D and before WP.org submission.

## How to run

1. Install the [Plugin Check](https://wordpress.org/plugins/plugin-check/) plugin on a local WP 6.5+ site
2. Upload `comprobantes-ocr.zip` (built by CI) or activate the plugin from the monorepo
3. Go to **Tools > Plugin Check** → select **Comprobantes OCR** → Run Checks

## Acceptance criteria (from spec R-12)

- ✅ 0 critical errors
- ✅ ≤ 3 warnings (block-related notices acceptable)

## Known acceptable warnings

- Block build artifacts (`index.asset.php` version hash) — cosmetic, not functional
- Missing `Tested up to` header if running against WP trunk — update `readme.txt` before submission
- Block category notice if WP version predates a given category — update `block.json` as needed

## Common issues to check manually

- All `echo` calls use `esc_html()` / `esc_attr()` / `esc_url()`
- All AJAX handlers use `check_ajax_referer()` and `current_user_can()`
- `uninstall.php` uses `WP_UNINSTALL_PLUGIN` guard
- No direct DB queries (`$wpdb` without `$wpdb->prepare()`)
- No `eval()` or `base64_decode()` on user input
- All translatable strings use domain `'comprobantes-ocr'`
- `load_plugin_textdomain()` called on `plugins_loaded` hook

## Plugin Check warning count (D4 gate — update after running)

> **Status**: Not yet run (requires WP environment).
> Update this section with the actual warning count before submitting to WP.org.

Plugin Check warnings: _TBD_
Plugin Check critical errors: _TBD_
