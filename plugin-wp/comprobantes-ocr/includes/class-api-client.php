<?php
/**
 * COCR_API_Client — thin HTTP wrapper around the FastAPI OCR service.
 *
 * All network calls use `wp_remote_post()` / `wp_remote_get()` exclusively
 * (never direct cURL). Binary file uploads use a manually constructed
 * multipart/form-data body because `wp_remote_post()` with an array `body`
 * encodes as `application/x-www-form-urlencoded`, which corrupts binary files.
 *
 * WP_Error taxonomy (see R-03):
 *   cocr_network_error   — DNS / TLS / timeout (is_wp_error on response)
 *   cocr_client_error    — HTTP 4xx (data includes HTTP status code)
 *   cocr_server_error    — HTTP 5xx (retry hint in message)
 *   cocr_invalid_response — non-JSON or malformed JSON body
 *   cocr_file_unreadable  — file_path not readable before building multipart
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class COCR_API_Client {

	/**
	 * Upload a comprobante file to FastAPI POST /upload-slip.
	 *
	 * @param string $file_path  Absolute path to the file on disk.
	 * @param string $api_url    Base URL of the FastAPI service (no trailing slash needed).
	 * @param string $api_key    Plaintext API key sent as X-API-Key header.
	 * @param int    $timeout    Request timeout in seconds (5–120, default 30).
	 * @return array{status:string,hash:string,id:string,message:string}|\WP_Error
	 */
	public function upload_slip( string $file_path, string $api_url, string $api_key, int $timeout = 30 ): array|\WP_Error {
		if ( ! is_readable( $file_path ) ) {
			return new \WP_Error(
				'cocr_file_unreadable',
				sprintf(
					/* translators: %s: file path */
					__( 'File is not readable: %s', 'comprobantes-ocr' ),
					$file_path
				)
			);
		}

		$timeout  = max( 5, min( 120, $timeout ) );
		$boundary = $this->_generate_boundary();
		$body     = $this->_build_multipart( $boundary, [], $file_path );

		return $this->_make_request(
			'POST',
			trailingslashit( $api_url ) . 'upload-slip',
			[
				'timeout' => $timeout,
				'headers' => [
					'X-API-Key'    => $api_key,
					'Content-Type' => 'multipart/form-data; boundary=' . $boundary,
				],
				'body'    => $body,
			]
		);
	}

	/**
	 * Fetch the last $limit comprobantes from GET /history.
	 *
	 * @param string $api_url Base URL of the FastAPI service.
	 * @param string $api_key Plaintext API key.
	 * @param int    $limit   Number of records to fetch (default 20).
	 * @return array|\WP_Error
	 */
	public function get_history( string $api_url, string $api_key, int $limit = 20 ): array|\WP_Error {
		$url      = trailingslashit( $api_url ) . 'history?limit=' . absint( $limit );
		$response = wp_remote_get(
			$url,
			[
				'timeout' => 10,
				'headers' => [ 'X-API-Key' => $api_key ],
			]
		);

		return $this->_parse_response( $response );
	}

	/**
	 * Test API connectivity via GET /health (public endpoint).
	 *
	 * @param string $api_url Base URL of the FastAPI service.
	 * @param string $api_key Plaintext API key (unused by /health, sent for completeness).
	 * @return true|\WP_Error  Returns true on success, WP_Error on failure.
	 */
	public function test_connection( string $api_url, string $api_key ): bool|\WP_Error {
		$response = wp_remote_get(
			trailingslashit( $api_url ) . 'health',
			[
				'timeout' => 5,
				'headers' => [ 'X-API-Key' => $api_key ],
			]
		);

		if ( is_wp_error( $response ) ) {
			return new \WP_Error(
				'cocr_network_error',
				$response->get_error_message()
			);
		}

		$code = wp_remote_retrieve_response_code( $response );
		if ( 200 !== $code ) {
			return new \WP_Error(
				'cocr_client_error',
				sprintf(
					/* translators: %d: HTTP status code */
					__( 'Health check returned HTTP %d', 'comprobantes-ocr' ),
					$code
				),
				[ 'status' => $code ]
			);
		}

		return true;
	}

	// -------------------------------------------------------------------------
	// Private helpers
	// -------------------------------------------------------------------------

	/**
	 * Generate a unique MIME boundary string.
	 *
	 * @return string
	 */
	private function _generate_boundary(): string {
		return '----WPBoundary' . wp_generate_uuid4();
	}

	/**
	 * Build a raw multipart/form-data body string for binary file upload.
	 *
	 * `wp_remote_post()` encodes array bodies as `application/x-www-form-urlencoded`,
	 * which corrupts binary payloads. We construct the raw string manually so the
	 * Content-Type header can specify the exact boundary.
	 *
	 * @param string $boundary   MIME boundary (without leading dashes).
	 * @param array  $fields     Associative array of scalar form fields (name => value).
	 * @param string $file_path  Absolute path to the file to upload.
	 * @param string $field_name Form field name for the file part (default 'file').
	 * @return string  Raw multipart body.
	 */
	private function _build_multipart( string $boundary, array $fields, string $file_path, string $field_name = 'file' ): string {
		$body     = '';
		$filename  = basename( $file_path );
		$mime_type = mime_content_type( $file_path ) ?: 'application/octet-stream'; // phpcs:ignore WordPress.WP.AlternativeFunctions.file_system_operations_file_get_contents
		$content   = file_get_contents( $file_path ); // phpcs:ignore WordPress.WP.AlternativeFunctions.file_get_contents_file_get_contents

		// Optional scalar fields.
		foreach ( $fields as $name => $value ) {
			$body .= "--{$boundary}\r\n";
			$body .= "Content-Disposition: form-data; name=\"{$name}\"\r\n\r\n";
			$body .= $value . "\r\n";
		}

		// File part.
		$body .= "--{$boundary}\r\n";
		$body .= "Content-Disposition: form-data; name=\"{$field_name}\"; filename=\"{$filename}\"\r\n";
		$body .= "Content-Type: {$mime_type}\r\n\r\n";
		$body .= $content . "\r\n";
		$body .= "--{$boundary}--\r\n";

		return $body;
	}

	/**
	 * Execute an HTTP request via wp_remote_*.
	 *
	 * @param string $method  'GET' or 'POST'.
	 * @param string $url     Full endpoint URL.
	 * @param array  $args    Arguments passed directly to wp_remote_*.
	 * @return array|\WP_Error  Parsed response data or WP_Error.
	 */
	private function _make_request( string $method, string $url, array $args ): array|\WP_Error {
		if ( 'POST' === strtoupper( $method ) ) {
			$response = wp_remote_post( $url, $args );
		} else {
			$response = wp_remote_get( $url, $args );
		}

		return $this->_parse_response( $response );
	}

	/**
	 * Parse a wp_remote_* response into a structured array or WP_Error.
	 *
	 * Applies the WP_Error taxonomy defined in R-03:
	 *   - Network failure   → cocr_network_error
	 *   - HTTP 4xx          → cocr_client_error  (status in data)
	 *   - HTTP 5xx          → cocr_server_error   (retry hint in message)
	 *   - Non-JSON body     → cocr_invalid_response
	 *
	 * @param array|\WP_Error $response Raw wp_remote_* return value.
	 * @return array|\WP_Error
	 */
	private function _parse_response( array|\WP_Error $response ): array|\WP_Error {
		if ( is_wp_error( $response ) ) {
			return new \WP_Error(
				'cocr_network_error',
				$response->get_error_message()
			);
		}

		$code = wp_remote_retrieve_response_code( $response );
		$body = wp_remote_retrieve_body( $response );

		if ( $code >= 500 ) {
			return new \WP_Error(
				'cocr_server_error',
				sprintf(
					/* translators: %d: HTTP status code */
					__( 'Server error %d. Please retry later.', 'comprobantes-ocr' ),
					$code
				),
				[ 'status' => $code, 'retry' => true ]
			);
		}

		if ( $code >= 400 ) {
			return new \WP_Error(
				'cocr_client_error',
				sprintf(
					/* translators: 1: HTTP status code, 2: response body */
					__( 'Client error %1$d: %2$s', 'comprobantes-ocr' ),
					$code,
					$body
				),
				[ 'status' => $code ]
			);
		}

		$data = json_decode( $body, true );
		if ( JSON_ERROR_NONE !== json_last_error() ) {
			return new \WP_Error(
				'cocr_invalid_response',
				__( 'Invalid JSON response from API.', 'comprobantes-ocr' )
			);
		}

		return $data;
	}
}
