<?php
/**
 * COCR_History_Widget — admin page showing the last 20 comprobantes.
 *
 * Registers a top-level menu item in wp-admin ("Comprobantes") and renders
 * a WP-style table via the `admin/history-widget.php` template. All output
 * in the template is escaped with esc_html().
 *
 * Access requires `current_user_can('manage_options')` (R-08).
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_History_Widget {

	/**
	 * Register the admin_menu hook.
	 */
	public function __construct() {
		add_action( 'admin_menu', [ $this, 'add_menu' ] );
	}

	/**
	 * Register the top-level admin menu page.
	 */
	public function add_menu(): void {
		add_menu_page(
			__( 'Comprobantes History', 'comprobantes-ocr' ),
			__( 'Comprobantes', 'comprobantes-ocr' ),
			'manage_options',
			'cocr-history',
			[ $this, 'render' ],
			'dashicons-media-document',
			56
		);
	}

	/**
	 * Fetch history from the API and include the template.
	 *
	 * On WP_Error shows a user-friendly notice instead of a raw error/trace.
	 */
	public function render(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		$api_url = get_option( COCR_Settings::OPTION_URL, '' );
		$api_key = get_option( COCR_Settings::OPTION_KEY, '' );

		if ( empty( $api_url ) ) {
			echo '<div class="wrap"><div class="notice notice-warning inline"><p>';
			esc_html_e( 'Please configure the API URL in Settings > Comprobantes OCR.', 'comprobantes-ocr' );
			echo '</p></div></div>';
			return;
		}

		$client  = new COCR_API_Client();
		$history = $client->get_history( $api_url, $api_key, 20 );

		include COCR_PLUGIN_DIR . 'admin/history-widget.php';
	}
}
