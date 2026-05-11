<?php
/**
 * Plugin Name: Comprobantes OCR
 * Plugin URI:  https://github.com/sassech/SmartVoucherDetection
 * Description: Upload and validate payment vouchers via OCR with duplicate detection.
 * Version:     1.0.0
 * Requires at least: 6.5
 * Requires PHP: 8.0
 * Author:      SmartVoucher
 * Author URI:  https://github.com/sassech/SmartVoucherDetection
 * License:     GPL-2.0-or-later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: comprobantes-ocr
 * Domain Path: /languages
 *
 * @package Comprobantes_OCR
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// Plugin constants.
define( 'COCR_VERSION', '1.0.0' );
define( 'COCR_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'COCR_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'COCR_PLUGIN_FILE', __FILE__ );

/**
 * PSR-4-style autoloader for COCR_ classes.
 *
 * Maps class name COCR_Foo_Bar → includes/class-foo-bar.php.
 * Only handles classes with the COCR_ prefix.
 *
 * @param string $class_name Fully-qualified class name.
 */
function cocr_autoloader( string $class_name ): void {
	if ( strpos( $class_name, 'COCR_' ) !== 0 ) {
		return;
	}

	// Convert COCR_Foo_Bar → class-foo-bar.php.
	$suffix    = substr( $class_name, strlen( 'COCR_' ) );
	$file_name = 'class-' . strtolower( str_replace( '_', '-', $suffix ) ) . '.php';
	$file_path = COCR_PLUGIN_DIR . 'includes/' . $file_name;

	if ( file_exists( $file_path ) ) {
		require_once $file_path;
	}
}

spl_autoload_register( 'cocr_autoloader' );

/**
 * Fired on plugin activation.
 *
 * Registers activation tasks. No DB changes in Fase 3 — the API
 * credentials are entered manually via the settings page after activation.
 */
function cocr_activate(): void {
	// Flush rewrite rules so shortcode pages resolve correctly.
	flush_rewrite_rules();
}

register_activation_hook( COCR_PLUGIN_FILE, 'cocr_activate' );

/**
 * Fired on plugin deactivation.
 *
 * Cleans up runtime artifacts but intentionally preserves saved options
 * (api_url, api_key, timeout). Those are only removed on full uninstall.
 */
function cocr_deactivate(): void {
	flush_rewrite_rules();
}

register_deactivation_hook( COCR_PLUGIN_FILE, 'cocr_deactivate' );

/**
 * Initialize plugin classes on `plugins_loaded`.
 *
 * Each class is guarded so a missing file causes a recoverable notice
 * rather than a fatal. COCR_Woo_Hook is gated on WooCommerce presence.
 */
function cocr_init(): void {
	// Load i18n strings.
	load_plugin_textdomain(
		'comprobantes-ocr',
		false,
		dirname( plugin_basename( COCR_PLUGIN_FILE ) ) . '/languages/'
	);

	// Core classes (always loaded).
	if ( class_exists( 'COCR_Settings' ) ) {
		new COCR_Settings();
	}

	if ( class_exists( 'COCR_Shortcode' ) ) {
		new COCR_Shortcode();
	}

	if ( class_exists( 'COCR_History_Widget' ) ) {
		new COCR_History_Widget();
	}

	if ( class_exists( 'COCR_Gutenberg' ) ) {
		new COCR_Gutenberg();
	}

	// Optional: WooCommerce integration — only when WooCommerce is active.
	if ( class_exists( 'WooCommerce' ) && class_exists( 'COCR_Woo_Hook' ) ) {
		new COCR_Woo_Hook();
	}
}

add_action( 'plugins_loaded', 'cocr_init' );
