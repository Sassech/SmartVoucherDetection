"""RED test for P0 NameError in process_slip eager path.

Task 1.1: process_slip had NameError due to param mismatch
  def process_slip(self, file_bytes_b64: str, _filename: str, _content_type: str)
  ...
  return asyncio.run(_run_pipeline(file_bytes, filename, content_type))
                                     ^^^^^^^^  ^^^^^^^^^^^^  undefined

This test runs with CELERY_TASK_ALWAYS_EAGER style mocking to prove the
eager path does not raise NameError after the fix.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest


def _make_b64_png() -> str:
    import io

    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(200, 200, 200))
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_process_slip_eager_does_not_raise_name_error():
    """Eager path: process_slip should not raise NameError on valid input."""
    from tasks.process_slip import process_slip

    b64 = _make_b64_png()

    # Mock the heavy async pipeline to isolate the NameError bug at the sync boundary
    with patch("tasks.process_slip._run_pipeline", new_callable=AsyncMock) as mock_pipeline:
        mock_pipeline.return_value = {"id_comprobante": "test-id", "estado_actual": "valido"}

        # Should NOT raise NameError even though original code used undefined `filename`
        # Use keyword args to verify param names are filename/content_type (not _filename)
        result = process_slip(
            file_bytes_b64=b64,
            filename="test.png",
            content_type="image/png",
        )

        # Verify pipeline was called with decoded bytes and correct filename/content_type
        assert mock_pipeline.call_count == 1
        call_args = mock_pipeline.call_args[0]
        assert isinstance(call_args[0], bytes)
        assert call_args[1] == "test.png"
        assert call_args[2] == "image/png"
        assert result["id_comprobante"] == "test-id"


def test_process_slip_eager_positional_args():
    """Positional args should also work (Celery send_task uses args=[...])."""
    from tasks.process_slip import process_slip

    b64 = _make_b64_png()

    with patch("tasks.process_slip._run_pipeline", new_callable=AsyncMock) as mock_pipeline:
        mock_pipeline.return_value = {"id_comprobante": "pos-id"}

        # Celery calls with positional args: args=[file_b64, filename, content_type]
        result = process_slip(b64, "upload.png", "image/png")

        assert mock_pipeline.call_count == 1
        assert mock_pipeline.call_args[0][1] == "upload.png"
        assert result["id_comprobante"] == "pos-id"


def test_process_slip_invalid_base64_raises_value_error():
    """Invalid base64 should raise ValueError, not NameError."""
    from tasks.process_slip import process_slip

    with pytest.raises(ValueError, match="Invalid base64"):
        process_slip("!!!not-base64!!!", "test.png", "image/png")
