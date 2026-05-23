/* global cocrPublic */
/**
 * upload-handler.js — multi-file sequential upload with results table.
 *
 * Accepts multiple files (drag & drop or file picker). Processes them one
 * at a time to avoid overloading the API. Each file gets a row in the
 * results table with a spinner while processing; the row updates in place
 * when the API responds.
 */
( function () {
	'use strict';

	const ALLOWED_TYPES = [ 'image/jpeg', 'image/png', 'application/pdf' ];

	/** Maps API status to badge CSS modifier and display label. */
	const STATUS_META = {
		valido     : { mod: 'green',  label: '✔ Valid' },
		sospechoso : { mod: 'yellow', label: '⚠ Suspicious' },
		duplicado  : { mod: 'red',    label: '✕ Duplicate' },
		error      : { mod: 'red',    label: '✕ Error' },
	};

	document.addEventListener( 'DOMContentLoaded', function () {
		const wrap      = document.querySelector( '.cocr-upload-wrap' );
		if ( ! wrap ) {
			return;
		}

		const dropzone  = document.getElementById( 'cocr-dropzone' );
		const fileInput = document.getElementById( 'cocr-file-input' );
		const browseBtn = document.getElementById( 'cocr-browse' );
		const msgEl     = document.getElementById( 'cocr-message' );
		const table     = document.getElementById( 'cocr-results' );
		const tbody     = document.getElementById( 'cocr-results-body' );
		const nonce     = wrap.dataset.nonce;

		// ── File picker ────────────────────────────────────────────────────
		browseBtn.addEventListener( 'click', function () {
			fileInput.click();
		} );

		fileInput.addEventListener( 'change', function () {
			enqueueFiles( Array.from( fileInput.files ) );
			fileInput.value = ''; // allow re-selecting same files
		} );

		// ── Drag & drop ────────────────────────────────────────────────────
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
				enqueueFiles( Array.from( e.dataTransfer.files ) );
			}
		} );

		// ── Sequential queue ───────────────────────────────────────────────

		/** @type {boolean} True while a file is being processed. */
		let processing = false;

		/** @type {Array<{file: File, rowId: string}>} Pending items. */
		const queue = [];

		/**
		 * Validate and add files to the queue; kick off processing if idle.
		 *
		 * @param {File[]} files
		 */
		function enqueueFiles( files ) {
			let skipped = 0;

			files.forEach( function ( file ) {
				if ( ! ALLOWED_TYPES.includes( file.type ) ) {
					skipped++;
					return;
				}
				if ( file.size > cocrPublic.max_size ) {
					skipped++;
					return;
				}

				const rowId = 'cocr-row-' + Date.now() + '-' + Math.random().toString( 36 ).slice( 2 );
				addPendingRow( rowId, file.name );
				queue.push( { file, rowId } );
			} );

			if ( skipped ) {
				setMsg(
					skipped + ' file(s) skipped (wrong type or over 10 MB).',
					true
				);
			} else {
				setMsg( '', false );
			}

			processNext();
		}

		/** Dequeue and upload the next file if the worker is free. */
		function processNext() {
			if ( processing || queue.length === 0 ) {
				return;
			}

			processing = true;
			const item = queue.shift();
			uploadFile( item.file, item.rowId ).finally( function () {
				processing = false;
				processNext();
			} );
		}

		// ── Upload ─────────────────────────────────────────────────────────

		/**
		 * Upload a single file and update its table row.
		 *
		 * @param  {File}   file
		 * @param  {string} rowId
		 * @return {Promise<void>}
		 */
		function uploadFile( file, rowId ) {
			const form = new FormData();
			form.append( 'action', 'cocr_upload_slip' );
			form.append( 'nonce',  nonce );
			form.append( 'file',   file, file.name );

			return fetch( cocrPublic.ajax_url, { method: 'POST', body: form } )
				.then( function ( r ) {
					return r.json();
				} )
				.then( function ( json ) {
					if ( json.success ) {
						updateRow( rowId, json.data );
					} else {
						const msg = ( json.data && json.data.message )
							? json.data.message
							: cocrPublic.i18n.server_error;
						updateRowError( rowId, msg );
					}
				} )
				.catch( function () {
					updateRowError( rowId, cocrPublic.i18n.server_error );
				} );
		}

		// ── Table helpers ──────────────────────────────────────────────────

		/** Show the results table if hidden. */
		function ensureTableVisible() {
			if ( table.style.display === 'none' ) {
				table.style.display = '';
			}
		}

		/**
		 * Insert a new row in "pending / spinner" state.
		 *
		 * @param {string} rowId
		 * @param {string} fileName
		 */
		function addPendingRow( rowId, fileName ) {
			ensureTableVisible();

			const tr = document.createElement( 'tr' );
			tr.id = rowId;
			tr.innerHTML =
				'<td class="cocr-col-file" title="' + escAttr( fileName ) + '">' + escHtml( truncate( fileName, 28 ) ) + '</td>' +
				'<td><span class="cocr-badge cocr-badge--pending"><span class="cocr-spinner"></span> Processing…</span></td>' +
				'<td>—</td>' +
				'<td>—</td>' +
				'<td>—</td>' +
				'<td>—</td>';

			tbody.appendChild( tr );
		}

		/**
		 * Update an existing row with the API result.
		 *
		 * @param {string} rowId
		 * @param {object} data   API response data object.
		 */
		function updateRow( rowId, data ) {
			const tr = document.getElementById( rowId );
			if ( ! tr ) {
				return;
			}

			// API returns `estado_actual` on 201, `status` on our 409 shim.
			const status = data.estado_actual || data.status || 'error';
			const meta   = STATUS_META[ status ] || STATUS_META.error;
			const campos = data.campos_extraidos || {};

			const cells = tr.querySelectorAll( 'td' );
			// [0] filename — unchanged
			cells[ 1 ].innerHTML = '<span class="cocr-badge cocr-badge--' + meta.mod + '">' + meta.label + '</span>';
			cells[ 2 ].textContent = campos.monto       ? '$' + campos.monto       : '—';
			cells[ 3 ].textContent = campos.banco        ? campos.banco             : '—';
			cells[ 4 ].textContent = campos.fecha        ? campos.fecha             : '—';
			cells[ 5 ].textContent = campos.referencia   ? campos.referencia        : ( campos.numero_operacion ? campos.numero_operacion : '—' );

			if ( 'duplicado' === status || 'sospechoso' === status ) {
				tr.classList.add( 'cocr-row--duplicate' );
			}
		}

		/**
		 * Update a row to show an upload/network error.
		 *
		 * @param {string} rowId
		 * @param {string} message
		 */
		function updateRowError( rowId, message ) {
			const tr = document.getElementById( rowId );
			if ( ! tr ) {
				return;
			}

			const cells = tr.querySelectorAll( 'td' );
			cells[ 1 ].innerHTML  = '<span class="cocr-badge cocr-badge--red">✕ Error</span>';
			cells[ 2 ].colSpan    = 4;
			cells[ 2 ].textContent = message;
			cells[ 3 ].style.display = 'none';
			cells[ 4 ].style.display = 'none';
			cells[ 5 ].style.display = 'none';
		}

		// ── Utilities ──────────────────────────────────────────────────────

		function setMsg( text, isError ) {
			msgEl.textContent  = text;
			msgEl.style.color  = isError ? '#cc1818' : '#1e7e34';
		}

		function escHtml( str ) {
			return String( str )
				.replace( /&/g, '&amp;' )
				.replace( /</g, '&lt;' )
				.replace( />/g, '&gt;' );
		}

		function escAttr( str ) {
			return escHtml( str ).replace( /"/g, '&quot;' );
		}

		function truncate( str, max ) {
			return str.length > max ? str.slice( 0, max - 1 ) + '…' : str;
		}
	} );
} )();
