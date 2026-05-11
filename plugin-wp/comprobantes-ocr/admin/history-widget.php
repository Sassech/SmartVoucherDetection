<?php
/**
 * Template: history-widget.php — renders the last 20 comprobantes table.
 *
 * Included by COCR_History_Widget::render(). Variable $history is either
 * a WP_Error or an associative array from the FastAPI GET /history response.
 *
 * Security: ALL cell output wrapped in esc_html() — no XSS possible even if
 * the API returns malicious strings (e.g. banco = "<script>alert(1)</script>").
 *
 * @var array|WP_Error $history
 * @package Comprobantes_OCR
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>
<div class="wrap">
	<h1><?php esc_html_e( 'Comprobantes — Last 20', 'comprobantes-ocr' ); ?></h1>

	<?php if ( is_wp_error( $history ) ) : ?>

		<div class="notice notice-error inline">
			<p><?php echo esc_html( $history->get_error_message() ); ?></p>
		</div>

	<?php else : ?>

		<?php
		$items = ( is_array( $history ) && isset( $history['items'] ) )
			? $history['items']
			: [];

		/**
		 * Map API estado_actual values to WP admin badge CSS classes.
		 *
		 * badge-success → green  (valido)
		 * badge-warning  → yellow (sospechoso, en_revision)
		 * badge-error    → red    (duplicado, error)
		 * badge-info     → blue   (recibido, procesando, comparando)
		 */
		$badge_map = [
			'valido'      => 'success',
			'sospechoso'  => 'warning',
			'duplicado'   => 'error',
			'error'       => 'error',
			'recibido'    => 'info',
			'procesando'  => 'info',
			'comparando'  => 'info',
			'en_revision' => 'warning',
		];
		?>

		<table class="wp-list-table widefat fixed striped">
			<thead>
				<tr>
					<th scope="col"><?php esc_html_e( 'Date', 'comprobantes-ocr' ); ?></th>
					<th scope="col"><?php esc_html_e( 'Bank', 'comprobantes-ocr' ); ?></th>
					<th scope="col"><?php esc_html_e( 'Amount', 'comprobantes-ocr' ); ?></th>
					<th scope="col"><?php esc_html_e( 'Status', 'comprobantes-ocr' ); ?></th>
					<th scope="col"><?php esc_html_e( 'Hash', 'comprobantes-ocr' ); ?></th>
				</tr>
			</thead>
			<tbody>
				<?php if ( empty( $items ) ) : ?>
					<tr>
						<td colspan="5"><?php esc_html_e( 'No comprobantes found.', 'comprobantes-ocr' ); ?></td>
					</tr>
				<?php else : ?>
					<?php foreach ( $items as $item ) : ?>
						<?php
						$status    = sanitize_text_field( $item['estado_actual'] ?? '' );
						$badge_cls = 'badge-' . esc_attr( $badge_map[ $status ] ?? 'info' );
						?>
						<tr>
							<td><?php echo esc_html( $item['fecha_registro'] ?? '—' ); ?></td>
							<td><?php echo esc_html( $item['campos_extraidos']['banco'] ?? '—' ); ?></td>
							<td><?php echo esc_html( $item['campos_extraidos']['monto'] ?? '—' ); ?></td>
							<td>
								<span class="cocr-badge <?php echo $badge_cls; ?>">
									<?php echo esc_html( $status ); ?>
								</span>
							</td>
							<td>
								<code><?php echo esc_html( substr( $item['hash_documento'] ?? '', 0, 12 ) . '…' ); ?></code>
							</td>
						</tr>
					<?php endforeach; ?>
				<?php endif; ?>
			</tbody>
		</table>

	<?php endif; ?>
</div>

<style>
.cocr-badge {
	display: inline-block;
	padding: 2px 8px;
	border-radius: 4px;
	font-size: .85em;
	font-weight: 600;
}
.badge-success { background: #d4edda; color: #155724; }
.badge-warning  { background: #fff3cd; color: #856404; }
.badge-error    { background: #f8d7da; color: #721c24; }
.badge-info     { background: #d1ecf1; color: #0c5460; }
</style>
