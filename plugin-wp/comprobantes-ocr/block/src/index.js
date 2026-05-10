import { registerBlockType } from '@wordpress/blocks';
import { __ } from '@wordpress/i18n';
import Edit from './edit';
import metadata from '../block.json';

registerBlockType( metadata.name, {
	...metadata,
	edit: Edit,
	save: () => null, // Dynamic block — rendered server-side via render_callback
} );
