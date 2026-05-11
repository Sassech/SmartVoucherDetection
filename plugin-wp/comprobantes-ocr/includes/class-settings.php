<?php
/**
 * COCR_Settings — Admin settings page for Comprobantes OCR.
 *
 * Registers the plugin settings page at Settings > Comprobantes OCR,
 * uses WordPress Settings API with nonces, and provides a "Test Connection"
 * AJAX handler that calls COCR_API_Client::test_connection().
 *
 * Security:
 *   - All inputs sanitized: esc_url_raw(), sanitize_text_field(), absint()
 *   - All outputs escaped: esc_html(), esc_attr()
 *   - AJAX action gated on check_ajax_referer() + current_user_can('manage_options')
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_Settings {

	/** @var string wp_options key for the API base URL */
	const OPTION_URL     = 'comprobantes_api_url';

	/** @var string wp_options key for the API key */
	const OPTION_KEY     = 'comprobantes_api_key';

	/** @var string wp_options key for the request timeout (seconds) */
	const OPTION_TIMEOUT = 'comprobantes_timeout';

	/**
	 * Register all WordPress hooks for the settings subsystem.
	 */
	public function __construct() {
		add_action( 'admin_menu',             [ $this, 'add_menu' ] );
		add_action( 'admin_init',             [ $this, 'register_settings' ] );
		add_action( 'admin_enqueue_scripts',  [ $this, 'enqueue_admin_scripts' ] );
		add_action( 'wp_ajax_cocr_test_connection', [ $this, 'ajax_test_connection' ] );
	}

	// -------------------------------------------------------------------------
	// Admin menu
	// -------------------------------------------------------------------------

	/**
	 * Add the settings sub-page under the Settings menu.
	 */
	public function add_menu(): void {
		add_options_page(
			__( 'Comprobantes OCR', 'comprobantes-ocr' ),
			__( 'Comprobantes OCR', 'comprobantes-ocr' ),
			'manage_options',
			'comprobantes-ocr',
			[ $this, 'render_settings_page' ]
		);
	}

	// -------------------------------------------------------------------------
	// Settings API
	// -------------------------------------------------------------------------

	/**
	 * Register settings, sections, and fields via the WordPress Settings API.
	 */
	public function register_settings(): void {
		register_setting(
			'cocr_settings_group',
			self::OPTION_URL,
			[
				'sanitize_callback' => 'esc_url_raw',
				'default'           => '',
			]
		);

		register_setting(
			'cocr_settings_group',
			self::OPTION_KEY,
			[
				'sanitize_callback' => 'sanitize_text_field',
				'default'           => '',
			]
		);

		register_setting(
			'cocr_settings_group',
			self::OPTION_TIMEOUT,
			[
				'sanitize_callback' => function ( $val ) {
					$val = absint( $val );
					return ( $val >= 5 && $val <= 120 ) ? $val : 30;
				},
				'default'           => 30,
			]
		);

		add_settings_section(
			'cocr_main',
			__( 'API Configuration', 'comprobantes-ocr' ),
			'__return_false',
			'comprobantes-ocr'
		);

		add_settings_field(
			'cocr_api_url',
			__( 'API URL', 'comprobantes-ocr' ),
			[ $this, 'field_api_url' ],
			'comprobantes-ocr',
			'cocr_main'
		);

		add_settings_field(
			'cocr_api_key',
			__( 'API Key', 'comprobantes-ocr' ),
			[ $this, 'field_api_key' ],
			'comprobantes-ocr',
			'cocr_main'
		);

		add_settings_field(
			'cocr_timeout',
			__( 'Timeout (seconds)', 'comprobantes-ocr' ),
			[ $this, 'field_timeout' ],
			'comprobantes-ocr',
			'cocr_main'
		);
	}

	// -------------------------------------------------------------------------
	// Field renderers
	// -------------------------------------------------------------------------

	/**
	 * Render the API URL input field.
	 */
	public function field_api_url(): void {
		$val = esc_attr( get_option( self::OPTION_URL, '' ) );
		echo '<input type="url" name="' . esc_attr( self::OPTION_URL ) . '" value="' . $val . '" class="regular-text" placeholder="http://localhost:8000" />';
		echo '<p class="description">' . esc_html__( 'Base URL of the FastAPI OCR service (e.g. https://api.example.com).', 'comprobantes-ocr' ) . '</p>';
	}

	/**
	 * Render the API Key password field with the "Test Connection" button.
	 */
	public function field_api_key(): void {
		$val = esc_attr( get_option( self::OPTION_KEY, '' ) );
		echo '<input type="password" name="' . esc_attr( self::OPTION_KEY ) . '" value="' . $val . '" class="regular-text" autocomplete="new-password" />';
		echo '<button type="button" id="cocr-test-connection" class="button button-secondary" style="margin-left:8px">';
		echo esc_html__( 'Test Connection', 'comprobantes-ocr' );
		echo '</button>';
		echo '<span id="cocr-test-result" style="margin-left:8px"></span>';
	}

	/**
	 * Render the timeout number field.
	 */
	public function field_timeout(): void {
		$val = absint( get_option( self::OPTION_TIMEOUT, 30 ) );
		echo '<input type="number" name="' . esc_attr( self::OPTION_TIMEOUT ) . '" value="' . esc_attr( $val ) . '" min="5" max="120" class="small-text" /> ';
		echo esc_html__( 'seconds (5–120)', 'comprobantes-ocr' );
	}

	// -------------------------------------------------------------------------
	// Admin scripts
	// -------------------------------------------------------------------------

	/**
	 * Enqueue the admin JS only on our settings page.
	 *
	 * @param string $hook Current admin page hook suffix.
	 */
	public function enqueue_admin_scripts( string $hook ): void {
		if ( 'settings_page_comprobantes-ocr' !== $hook ) {
			return;
		}

		wp_enqueue_script(
			'cocr-admin',
			COCR_PLUGIN_URL . 'public/admin-settings.js',
			[ 'jquery' ],
			COCR_VERSION,
			true
		);

		wp_localize_script(
			'cocr-admin',
			'cocrAdmin',
			[
				'ajax_url' => admin_url( 'admin-ajax.php' ),
				'nonce'    => wp_create_nonce( 'cocr_test_connection' ),
				'i18n'     => [
					'testing' => __( 'Testing…', 'comprobantes-ocr' ),
					'ok'      => __( '✅ Connected', 'comprobantes-ocr' ),
					'fail'    => __( '❌ Failed', 'comprobantes-ocr' ),
				],
			]
		);
	}

	// -------------------------------------------------------------------------
	// AJAX: Test Connection
	// -------------------------------------------------------------------------

	/**
	 * AJAX handler — verify API connectivity via GET /health.
	 *
	 * Verifies the nonce and capability before calling COCR_API_Client.
	 * Responds with wp_send_json_success/error (JSON only — no HTML).
	 */
	public function ajax_test_connection(): void {
		check_ajax_referer( 'cocr_test_connection', 'nonce' );

		if ( ! current_user_can( 'manage_options' ) ) {
			wp_send_json_error(
				[ 'message' => __( 'Permission denied.', 'comprobantes-ocr' ) ],
				403
			);
		}

		// phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotSanitized
		$api_url = sanitize_text_field( wp_unslash( $_POST['api_url'] ?? '' ) );
		// phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotSanitized
		$api_key = sanitize_text_field( wp_unslash( $_POST['api_key'] ?? '' ) );

		if ( empty( $api_url ) ) {
			wp_send_json_error(
				[ 'message' => __( 'API URL is required.', 'comprobantes-ocr' ) ]
			);
		}

		$client = new COCR_API_Client();
		$result = $client->test_connection( $api_url, $api_key );

		if ( is_wp_error( $result ) ) {
			wp_send_json_error(
				[ 'message' => esc_html( $result->get_error_message() ) ]
			);
		}

		wp_send_json_success(
			[ 'message' => __( 'Connection successful.', 'comprobantes-ocr' ) ]
		);
	}

	// -------------------------------------------------------------------------
	// Page renderer
	// -------------------------------------------------------------------------

	/**
	 * Render the full settings page HTML.
	 *
	 * Uses settings_fields() + do_settings_sections() so WordPress handles
	 * the nonce (_wpnonce) and option_page fields automatically.
	 */
	public function render_settings_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		?>
		<div class="wrap">
			<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
			<form method="post" action="options.php">
				<?php
				settings_fields( 'cocr_settings_group' );
				do_settings_sections( 'comprobantes-ocr' );
				submit_button();
				?>
			</form>
		</div>
		<?php
	}
}
