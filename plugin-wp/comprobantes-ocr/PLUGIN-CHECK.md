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

---

## Pre-submission Checklist

### W-01 — Plugin Check CLI

Run the Plugin Check tool in a real WordPress environment (local WP site or staging) before submitting to WP.org. The CI build (`build-plugin.yml`) produces a `comprobantes-ocr.zip` artifact — use that for the check to test exactly what will be submitted.

```bash
# Using WP-CLI + Plugin Check CLI (if installed)
wp plugin check comprobantes-ocr
```

### Resolved Warnings (PR-E)

| Warning | Description | Status |
|---------|-------------|--------|
| W-02 | Hash displayed in history widget truncated to 8 chars | ✅ RESOLVED |
| W-03 | All CSS classes use `cocr-badge-` prefix consistently | ✅ RESOLVED |
| W-04 | All JS globals use `cocr`/`cocrPublic`/`cocrAdmin` prefix consistently | ✅ RESOLVED |
| W-05 | Orphaned reference comment removed from `es_MX.po`; no empty `msgstr ""` entries remain | ✅ RESOLVED |

### SVN Submission Steps (manual — not automated by CI)

WP.org plugin submission uses SVN. Once the Plugin Check passes with 0 critical errors and ≤ 3 warnings:

1. Check out the plugin's SVN repository:
   ```bash
   svn co https://plugins.svn.wordpress.org/comprobantes-ocr/
   ```
2. Copy all plugin files into the `trunk/` directory:
   ```bash
   cp -r plugin-wp/comprobantes-ocr/* comprobantes-ocr/trunk/
   ```
3. Add any new files and commit:
   ```bash
   cd comprobantes-ocr
   svn add trunk/* --force
   svn ci -m "Initial submission v1.0.0"
   ```
4. Tag the release (after WP.org review approval):
   ```bash
   svn cp trunk tags/1.0.0
   svn ci -m "Tag 1.0.0"
   ```

> **Note**: WP.org review takes 1–4 weeks for initial submissions. Subsequent updates are faster (typically 1–2 business days).
