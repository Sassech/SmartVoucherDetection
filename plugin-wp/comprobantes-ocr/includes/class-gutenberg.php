<?php
/**
 * COCR_Gutenberg — Gutenberg block registration for Comprobantes OCR.
 *
 * Block: comprobantes-ocr/upload (dynamic — server-side render via render_callback).
 * Reuses COCR_Shortcode::render() as the single source of truth for the upload form.
 *
 * Security (R-07):
 *   - Block registered only when build assets exist (graceful degradation)
 *   - render_callback delegates to COCR_Shortcode::render() which enforces
 *     current_user_can('upload_files') and all nonce/escaping rules
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_Gutenberg {

	/**
	 * Register the block on `init`.
	 */
	public function __construct() {
		add_action( 'init', [ $this, 'register_block' ] );
	}

	/**
	 * Register the block type using block.json.
	 *
	 * Reads the generated index.asset.php to obtain correct dependencies and
	 * version hash. Skips registration gracefully if build artifacts are missing
	 * (e.g., dev environment without `npm run build`).
	 */
	public function register_block(): void {
		$asset_file = COCR_PLUGIN_DIR . 'block/build/index.asset.php';

		if ( ! file_exists( $asset_file ) ) {
			// Build artifacts missing — graceful degradation (no block registered).
			return;
		}

		$asset = include $asset_file;

		wp_register_script(
			'cocr-block-editor',
			COCR_PLUGIN_URL . 'block/build/index.js',
			$asset['dependencies'],
			$asset['version'],
			false
		);

		register_block_type(
			COCR_PLUGIN_DIR . 'block/block.json',
			[
				'editor_script'   => 'cocr-block-editor',
				'render_callback' => [ $this, 'render_block' ],
			]
		);
	}

	/**
	 * Server-side render callback.
	 *
	 * Delegates to COCR_Shortcode::render() — single source of truth for the
	 * upload form HTML. All capability checks, nonce generation, and escaping
	 * are handled inside render().
	 *
	 * @param array $attributes Block attributes (apiUrlOverride etc.).
	 * @return string HTML output.
	 */
	public function render_block( array $attributes ): string {
		if ( ! class_exists( 'COCR_Shortcode' ) ) {
			return '';
		}

		// Instantiate shortcode renderer. Does not re-register hooks because
		// COCR_Shortcode was already bootstrapped in cocr_init().
		$shortcode = new COCR_Shortcode();
		return $shortcode->render( $attributes );
	}
}
