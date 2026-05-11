/* global cocrPublic, cocrShowResult */
/**
 * upload-handler.js — drag-and-drop + file-input AJAX upload handler.
 *
 * Reads the file, validates size and MIME type client-side, builds a
 * FormData payload with the AJAX action and nonce, then POSTs to
 * admin-ajax.php. On success the JSON is passed to cocrShowResult()
 * (defined in result-display.js) to update the traffic-light semaphore.
 */
( function () {
	'use strict';

	const ALLOWED_TYPES = [ 'image/jpeg', 'image/png', 'application/pdf' ];

	document.addEventListener( 'DOMContentLoaded', function () {
		const wrap = document.querySelector( '.cocr-upload-wrap' );
		if ( ! wrap ) {
			return;
		}

		const dropzone  = document.getElementById( 'cocr-dropzone' );
		const fileInput = document.getElementById( 'cocr-file-input' );
		const browseBtn = document.getElementById( 'cocr-browse' );
		const msgEl     = document.getElementById( 'cocr-message' );
		const nonce     = wrap.dataset.nonce;

		// Open file picker on "Browse" button click.
		browseBtn.addEventListener( 'click', function () {
			fileInput.click();
		} );

		// Handle file chosen via native file picker.
		fileInput.addEventListener( 'change', function () {
			handleFile( fileInput.files[ 0 ] );
		} );

		// Drag-and-drop event wiring.
		dropzone.addEventListener( 'dragover', function ( e ) {
			e.preventDefault();
			dropzone.classList.add( 'cocr-drag-over' );
		} );

		dropzone.addEventListener( 'dragleave', function () {
			dropzone.classList.remove( 'cocr-drag-over' );
		} );

		dropzone.addEventListener( 'drop', function ( e ) {
			e.preventDefault();
			dropzone.classList.remove( 'cocr-drag-over' );
			if ( e.dataTransfer.files.length ) {
				handleFile( e.dataTransfer.files[ 0 ] );
			}
		} );

		/**
		 * Display a status message below the drop zone.
		 *
		 * @param {string}  text    Message to display.
		 * @param {boolean} isError Whether to use error (red) styling.
		 */
		function showMsg( text, isError ) {
			msgEl.textContent = text;
			msgEl.style.color = isError ? '#cc1818' : '#1e7e34';
		}

		/**
		 * Validate, then upload the given file via admin-ajax.php.
		 *
		 * @param {File|undefined} file The file to upload.
		 */
		function handleFile( file ) {
			if ( ! file ) {
				return;
			}

			// Client-side MIME type check.
			if ( ! ALLOWED_TYPES.includes( file.type ) ) {
				showMsg( cocrPublic.i18n.type_error, true );
				return;
			}

			// Client-side size check.
			if ( file.size > cocrPublic.max_size ) {
				showMsg( cocrPublic.i18n.size_error, true );
				return;
			}

			showMsg( cocrPublic.i18n.uploading, false );

			const form = new FormData();
			form.append( 'action', 'cocr_upload_slip' );
			form.append( 'nonce',  nonce );
			form.append( 'file',   file, file.name );

			fetch( cocrPublic.ajax_url, { method: 'POST', body: form } )
				.then( function ( r ) {
					return r.json();
				} )
				.then( function ( json ) {
					if ( json.success ) {
						cocrShowResult( json.data );
						showMsg( '', false );
					} else {
						const msg = ( json.data && json.data.message )
							? json.data.message
							: cocrPublic.i18n.server_error;
						showMsg( msg, true );
						cocrShowResult( null );
					}
				} )
				.catch( function () {
					showMsg( cocrPublic.i18n.server_error, true );
					cocrShowResult( null );
				} );
		}
	} );
} )();
