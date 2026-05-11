<?php
/**
 * Uninstall — runs when the plugin is deleted via WP admin.
 *
 * Removes all options stored by the plugin. This file is executed
 * by WordPress core; it MUST check WP_UNINSTALL_PLUGIN to prevent
 * direct file execution.
 *
 * @package Comprobantes_OCR
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

delete_option( 'comprobantes_api_url' );
delete_option( 'comprobantes_api_key' );
delete_option( 'comprobantes_timeout' );
