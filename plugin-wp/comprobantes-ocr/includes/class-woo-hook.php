<?php
/**
 * COCR_Woo_Hook — WooCommerce integration for Comprobantes OCR.
 *
 * Fires on woocommerce_order_status_completed to upload an attached
 * comprobante asynchronously via POST /upload-slip/async.
 *
 * Loaded ONLY if class_exists('WooCommerce') — see entry point guard
 * in comprobantes-ocr.php (cocr_init()).
 *
 * Security:
 *   - sanitize_text_field() on all order meta reads
 *   - file_exists() guard before any API call
 *   - WP_Error logged via order note (no fatal on failure)
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_Woo_Hook {

	/** @var string Order meta key for the async task ID returned by the API */
	const META_TASK_ID = '_cocr_task_id';

	/** @var string Order meta key where the comprobante file path is stored */
	const META_FILE_PATH = '_cocr_comprobante_path';

	/**
	 * Register the order-status hook.
	 */
	public function __construct() {
		add_action( 'woocommerce_order_status_completed', [ $this, 'on_order_completed' ], 10, 1 );
	}

	// -------------------------------------------------------------------------
	// Hook callback
	// -------------------------------------------------------------------------

	/**
	 * Triggered when a WooCommerce order reaches "completed" status.
	 *
	 * 1. Loads the order.
	 * 2. Looks for a comprobante file path in order meta (_cocr_comprobante_path).
	 * 3. If found and readable, calls COCR_API_Client::upload_slip_async().
	 * 4. On success: stores task_id in _cocr_task_id meta + adds order note.
	 * 5. On failure: logs error as order note — never blocks order completion.
	 *
	 * @param int $order_id WooCommerce order ID.
	 */
	public function on_order_completed( int $order_id ): void {
		$order = wc_get_order( $order_id );
		if ( ! $order ) {
			return;
		}

		// Retrieve comprobante file path from order meta.
		$file_path = $this->get_comprobante_path( $order );
		if ( empty( $file_path ) || ! file_exists( $file_path ) ) {
			return; // No attachment — nothing to upload.
		}

		$api_url = get_option( COCR_Settings::OPTION_URL, '' );
		$api_key = get_option( COCR_Settings::OPTION_KEY, '' );

		if ( empty( $api_url ) ) {
			return; // Plugin not configured — skip silently.
		}

		$client = new COCR_API_Client();
		$result = $client->upload_slip_async( $file_path, $api_url, $api_key );

		if ( is_wp_error( $result ) ) {
			// Log the error as an order note — do NOT block order completion.
			$order->add_order_note(
				sprintf(
					/* translators: %s: error message */
					__( 'Comprobantes OCR: upload failed — %s', 'comprobantes-ocr' ),
					esc_html( $result->get_error_message() )
				)
			);
			return;
		}

		// Store task_id in order meta for later polling (Fase 4 webhooks).
		$task_id = sanitize_text_field( $result['task_id'] ?? '' );
		if ( $task_id ) {
			$order->update_meta_data( self::META_TASK_ID, $task_id );
			$order->save();
			$order->add_order_note(
				sprintf(
					/* translators: %s: task ID */
					__( 'Comprobantes OCR: processing started (task %s)', 'comprobantes-ocr' ),
					esc_html( $task_id )
				)
			);
		}
	}

	// -------------------------------------------------------------------------
	// Private helpers
	// -------------------------------------------------------------------------

	/**
	 * Retrieve comprobante file path from order meta.
	 *
	 * Convention: the file path is stored in _cocr_comprobante_path when the
	 * attachment is associated with the order (e.g., via a payment gateway or
	 * manual upload before order completion).
	 *
	 * @param \WC_Order $order WooCommerce order object.
	 * @return string  Sanitized absolute file path, or empty string if not set.
	 */
	private function get_comprobante_path( \WC_Order $order ): string {
		return sanitize_text_field( $order->get_meta( self::META_FILE_PATH, true ) );
	}
}
