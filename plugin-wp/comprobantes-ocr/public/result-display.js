/* global cocrShowResult:true */
/**
 * result-display.js — traffic-light semaphore renderer.
 *
 * Exposes window.cocrShowResult(data) which maps the API response status
 * to a CSS class on the semaphore DOM element:
 *
 *   valido      → green light active  (R-06)
 *   sospechoso  → yellow light active
 *   duplicado   → red light active
 *   error       → red light active
 *   null/reset  → all lights off, semaphore hidden
 *
 * CSS transitions (≥ 300ms) are defined in style.css.
 */
( function () {
	'use strict';

	/** Map of API status values to semaphore light colours. */
	const STATUS_MAP = {
		valido     : 'green',
		sospechoso : 'yellow',
		duplicado  : 'red',
		error      : 'red',
	};

	/**
	 * Render the traffic-light semaphore based on API response data.
	 *
	 * @param {object|null} data  API response data (json.data) or null to reset.
	 */
	window.cocrShowResult = function ( data ) {
		const semaphore = document.getElementById( 'cocr-semaphore' );
		if ( ! semaphore ) {
			return;
		}

		const lights = {
			red   : document.getElementById( 'cocr-light-red' ),
			yellow: document.getElementById( 'cocr-light-yellow' ),
			green : document.getElementById( 'cocr-light-green' ),
		};

		// Reset all lights.
		Object.values( lights ).forEach( function ( el ) {
			if ( el ) {
				el.classList.remove( 'cocr-active' );
			}
		} );

		// Hide semaphore and bail when data is null (reset state).
		if ( ! data ) {
			semaphore.style.display = 'none';
			return;
		}

		// Activate the appropriate light (default to red for unknown statuses).
		const active = STATUS_MAP[ data.status ] || 'red';
		if ( lights[ active ] ) {
			lights[ active ].classList.add( 'cocr-active' );
		}

		semaphore.style.display = 'flex';
	};
} )();
