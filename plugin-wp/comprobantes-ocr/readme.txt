=== Comprobantes OCR ===
Contributors: smartvoucher
Tags: ocr, comprobante, voucher, payment, woocommerce
Requires at least: 6.5
Tested up to: 6.5
Requires PHP: 8.0
Stable tag: 1.0.0
License: GPL-2.0-or-later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Detect duplicate payment slips automatically using AI-powered OCR.

== Description ==

Comprobantes OCR connects your WordPress site to the SmartVoucherDetection API to automatically detect duplicate payment slips (comprobantes) using multimodal OCR and fuzzy matching.

**Features:**

* Upload comprobantes via drag-and-drop shortcode `[comprobante_upload]`
* Gutenberg block equivalent to the shortcode
* Traffic-light semaphore: green (valid), yellow (suspicious), red (duplicate/error)
* Admin history widget showing the last 20 processed comprobantes
* WooCommerce integration: automatically processes comprobantes on order completion
* i18n ready: Spanish (Mexico) and English (US) included

== Installation ==

1. Upload the `comprobantes-ocr` folder to `/wp-content/plugins/`
2. Activate the plugin through the **Plugins** menu in WordPress
3. Go to **Settings > Comprobantes OCR** and enter your API URL and API Key

== Getting Started ==

**API Key Setup**

The SmartVoucherDetection API uses key-based authentication. To generate your first API key, run the following script on your server (requires Python and access to the API database):

`cd /path/to/SmartVoucherDetection/api && uv run python ../infra/scripts/seed_api_key.py`

This prints your API key once. Copy it immediately and paste it in **Settings > Comprobantes OCR > API Key**.

**Shortcode Usage**

Add `[comprobante_upload]` to any page or post. The upload form is only visible to logged-in users with the `upload_files` capability.

**WooCommerce Integration**

If WooCommerce is active, the plugin automatically hooks into `woocommerce_order_status_completed`. To attach a comprobante to an order, store the file path in the `_cocr_comprobante_path` order meta before marking the order as completed.

== Frequently Asked Questions ==

= What file formats are supported? =

JPEG, PNG, and PDF (first page only).

= What is the maximum file size? =

10 MB per comprobante.

= Does this plugin require WooCommerce? =

No. WooCommerce integration is optional and activates automatically if WooCommerce is installed.

= Where is my data stored? =

Files are processed by the SmartVoucherDetection API you configure. No data is sent to third-party servers by this plugin.

= How do I generate an API key? =

Run `uv run python infra/scripts/seed_api_key.py` in your API project directory. The plaintext key is printed once to stdout — copy and save it immediately.

== Screenshots ==

1. Upload form with drag-and-drop and traffic-light semaphore
2. Admin settings page
3. History widget showing last 20 comprobantes

== Changelog ==

= 1.0.0 =
* Initial release

== Upgrade Notice ==

= 1.0.0 =
Initial release.
