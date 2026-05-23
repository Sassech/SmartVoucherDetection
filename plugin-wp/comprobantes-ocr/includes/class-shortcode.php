<?php
/**
 * COCR_Shortcode — [comprobante_upload] shortcode + AJAX handler.
 *
 * Renders a drag-and-drop upload area for authenticated users
 * (requires `upload_files` capability). The frontend sends the file
 * to the `cocr_upload_slip` AJAX action which calls COCR_API_Client
 * and returns the API result as JSON.
 *
 * Security (R-05):
 *   - Shortcode renders empty string for unauthenticated/uncapable users
 *   - AJAX handler: check_ajax_referer('cocr_upload_slip') + current_user_can('upload_files')
 *   - No nopriv hook — requires login
 *   - Server-side file size check (belt + suspenders — client also validates)
 *   - wp_check_filetype_and_ext() whitelist for type validation
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_Shortcode {

	/**
	 * Register the shortcode and all WordPress hooks.
	 */
	public function __construct() {
		add_shortcode( 'comprobante_upload', [ $this, 'render' ] );
		add_action( 'wp_enqueue_scripts',       [ $this, 'enqueue_scripts' ] );
		add_action( 'wp_ajax_cocr_upload_slip', [ $this, 'ajax_upload' ] );
		// NO nopriv — shortcode requires login (R-05, user decision)
	}

	// -------------------------------------------------------------------------
	// Shortcode render
	// -------------------------------------------------------------------------

	/**
	 * Render the upload widget HTML.
	 *
	 * Returns an empty string for users who do not have `upload_files`.
	 *
	 * @param array $atts Shortcode attributes (unused in Fase 3).
	 * @return string HTML output.
	 */
	public function render( array $atts = [] ): string {
		if ( ! current_user_can( 'upload_files' ) ) {
			return '';
		}

		$nonce = wp_create_nonce( 'cocr_upload_slip' );
		ob_start();
		?>
		<div class="cocr-upload-wrap" data-nonce="<?php echo esc_attr( $nonce ); ?>">

			<div class="cocr-dropzone" id="cocr-dropzone">
				<input
					type="file"
					id="cocr-file-input"
					accept="image/jpeg,image/png,application/pdf"
					multiple
					style="display:none"
				/>
				<p>
					<?php esc_html_e( 'Drag & drop your comprobantes here or', 'comprobantes-ocr' ); ?>
					<button type="button" id="cocr-browse">
						<?php esc_html_e( 'Browse', 'comprobantes-ocr' ); ?>
					</button>
				</p>
				<p class="cocr-hint">
					<?php esc_html_e( 'Accepted: JPEG, PNG, PDF · Max 10 MB each · Multiple files supported', 'comprobantes-ocr' ); ?>
				</p>
			</div>

			<div class="cocr-message" id="cocr-message"></div>

			<table class="cocr-results" id="cocr-results" style="display:none">
				<thead>
					<tr>
						<th><?php esc_html_e( 'File', 'comprobantes-ocr' ); ?></th>
						<th><?php esc_html_e( 'Status', 'comprobantes-ocr' ); ?></th>
						<th><?php esc_html_e( 'Amount', 'comprobantes-ocr' ); ?></th>
						<th><?php esc_html_e( 'Bank', 'comprobantes-ocr' ); ?></th>
						<th><?php esc_html_e( 'Date', 'comprobantes-ocr' ); ?></th>
						<th><?php esc_html_e( 'Reference', 'comprobantes-ocr' ); ?></th>
					</tr>
				</thead>
				<tbody id="cocr-results-body"></tbody>
			</table>

		</div>
		<?php
		return ob_get_clean();
	}

	// -------------------------------------------------------------------------
	// Script / style enqueue
	// -------------------------------------------------------------------------

	/**
	 * Enqueue public-facing JS and CSS.
	 *
	 * Only fires on singular posts/pages so we do not pollute every page.
	 */
	public function enqueue_scripts(): void {
		if ( ! is_singular() ) {
			return;
		}

		wp_enqueue_style(
			'cocr-public',
			COCR_PLUGIN_URL . 'public/style.css',
			[],
			COCR_VERSION
		);

		wp_enqueue_script(
			'cocr-upload',
			COCR_PLUGIN_URL . 'public/upload-handler.js',
			[],
			COCR_VERSION,
			true
		);

		wp_enqueue_script(
			'cocr-semaphore',
			COCR_PLUGIN_URL . 'public/result-display.js',
			[ 'cocr-upload' ],
			COCR_VERSION,
			true
		);

		wp_localize_script(
			'cocr-upload',
			'cocrPublic',
			[
				'ajax_url' => admin_url( 'admin-ajax.php' ),
				'max_size' => 10 * 1024 * 1024,
				'i18n'     => [
					'uploading'    => __( 'Uploading…', 'comprobantes-ocr' ),
					'size_error'   => __( 'File exceeds 10 MB limit.', 'comprobantes-ocr' ),
					'type_error'   => __( 'Only JPEG, PNG, and PDF files are accepted.', 'comprobantes-ocr' ),
					'server_error' => __( 'Server error. Please try again.', 'comprobantes-ocr' ),
				],
			]
		);
	}

	// -------------------------------------------------------------------------
	// AJAX: Upload slip
	// -------------------------------------------------------------------------

	/**
	 * AJAX handler — receive the uploaded file and proxy it to FastAPI.
	 *
	 * Validates nonce, capability, file presence, size, and calls
	 * COCR_API_Client::upload_slip(). Returns JSON success/error.
	 */
	public function ajax_upload(): void {
		check_ajax_referer( 'cocr_upload_slip', 'nonce' );

		if ( ! current_user_can( 'upload_files' ) ) {
			wp_send_json_error(
				[ 'message' => __( 'Permission denied.', 'comprobantes-ocr' ) ],
				403
			);
		}

		// phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotValidated
		if ( empty( $_FILES['file'] ) || UPLOAD_ERR_OK !== $_FILES['file']['error'] ) {
			wp_send_json_error(
				[ 'message' => __( 'No file received or upload error.', 'comprobantes-ocr' ) ]
			);
		}

		// phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotValidated
		$file = $_FILES['file'];

		// Server-side size check — client already validates but be defensive.
		if ( $file['size'] > 10 * 1024 * 1024 ) {
			wp_send_json_error(
				[ 'message' => __( 'File too large (max 10 MB).', 'comprobantes-ocr' ) ]
			);
		}

		// MIME type whitelist (server-side belt+suspenders).
		$allowed_types = [ 'jpg', 'jpeg', 'png', 'pdf' ];
		$file_info     = wp_check_filetype_and_ext(
			$file['tmp_name'],
			$file['name'],
			[
				'jpg'  => 'image/jpeg',
				'jpeg' => 'image/jpeg',
				'png'  => 'image/png',
				'pdf'  => 'application/pdf',
			]
		);

		if ( empty( $file_info['ext'] ) || ! in_array( $file_info['ext'], $allowed_types, true ) ) {
			wp_send_json_error(
				[ 'message' => __( 'Only JPEG, PNG, and PDF files are accepted.', 'comprobantes-ocr' ) ]
			);
		}

		$api_url = get_option( COCR_Settings::OPTION_URL, '' );
		$api_key = get_option( COCR_Settings::OPTION_KEY, '' );
		$timeout = absint( get_option( COCR_Settings::OPTION_TIMEOUT, 30 ) );

		if ( empty( $api_url ) ) {
			wp_send_json_error(
				[ 'message' => __( 'API URL not configured. Visit Settings > Comprobantes OCR.', 'comprobantes-ocr' ) ]
			);
		}

		$client = new COCR_API_Client();
		$result = $client->upload_slip( $file['tmp_name'], $api_url, $api_key, $timeout );

		if ( is_wp_error( $result ) ) {
			wp_send_json_error(
				[ 'message' => esc_html( $result->get_error_message() ) ]
			);
		}

		wp_send_json_success( $result );
	}
}
