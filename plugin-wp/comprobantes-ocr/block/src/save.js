// Dynamic block: content is rendered server-side via render_callback in COCR_Gutenberg.
// Save must return null so WordPress does not validate block content on load.
export default function save() {
	return null;
}
