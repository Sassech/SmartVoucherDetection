/* global cocrAdmin, jQuery */
/**
 * admin-settings.js — "Test Connection" AJAX handler for COCR settings page.
 *
 * Reads the current api_url and api_key values from the form, posts them to
 * the cocr_test_connection AJAX action, and shows an inline result next to
 * the button without reloading the page.
 */
jQuery( function ( $ ) {
	$( '#cocr-test-connection' ).on( 'click', function () {
		const $btn    = $( this );
		const $result = $( '#cocr-test-result' );
		const apiUrl  = $( 'input[name="comprobantes_api_url"]' ).val();
		const apiKey  = $( 'input[name="comprobantes_api_key"]' ).val();

		$btn.prop( 'disabled', true );
		$result.removeAttr( 'style' ).text( cocrAdmin.i18n.testing );

		$.post( cocrAdmin.ajax_url, {
			action : 'cocr_test_connection',
			nonce  : cocrAdmin.nonce,
			api_url: apiUrl,
			api_key: apiKey,
		} )
		.done( function ( response ) {
			if ( response.success ) {
				$result.css( 'color', 'green' ).text( cocrAdmin.i18n.ok );
			} else {
				const detail = ( response.data && response.data.message ) ? ' — ' + response.data.message : '';
				$result.css( 'color', 'red' ).text( cocrAdmin.i18n.fail + detail );
			}
		} )
		.fail( function () {
			$result.css( 'color', 'red' ).text( cocrAdmin.i18n.fail );
		} )
		.always( function () {
			$btn.prop( 'disabled', false );
		} );
	} );
} );
