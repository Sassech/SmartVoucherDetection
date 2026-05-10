import { __ } from '@wordpress/i18n';
import { useBlockProps, InspectorControls } from '@wordpress/block-editor';
import { PanelBody, TextControl } from '@wordpress/components';

export default function Edit( { attributes, setAttributes } ) {
	const blockProps = useBlockProps( { className: 'cocr-block-editor-preview' } );
	const { apiUrlOverride } = attributes;

	return (
		<>
			<InspectorControls>
				<PanelBody title={ __( 'API Settings', 'comprobantes-ocr' ) }>
					<TextControl
						label={ __( 'API URL Override', 'comprobantes-ocr' ) }
						help={ __( 'Leave empty to use the global plugin setting.', 'comprobantes-ocr' ) }
						value={ apiUrlOverride }
						onChange={ ( val ) => setAttributes( { apiUrlOverride: val } ) }
						type="url"
					/>
				</PanelBody>
			</InspectorControls>
			<div { ...blockProps }>
				<div style={ { border: '2px dashed #ccc', borderRadius: '8px', padding: '24px', textAlign: 'center', background: '#fafafa' } }>
					<span className="dashicons dashicons-media-document" style={ { fontSize: '2em', marginBottom: '8px', display: 'block' } }></span>
					<strong>{ __( 'Comprobante Upload', 'comprobantes-ocr' ) }</strong>
					<p style={ { margin: '8px 0 0', color: '#888', fontSize: '0.85em' } }>
						{ __( 'This block renders the comprobante upload form on the front end.', 'comprobantes-ocr' ) }
					</p>
				</div>
			</div>
		</>
	);
}
