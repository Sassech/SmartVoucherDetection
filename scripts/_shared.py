"""Bootstrap compartido para scripts de evaluación.

Todos los scripts en scripts/ importan este módulo para acceder
a los servicios de api/ sin duplicar la lógica de path setup.
"""

import sys
from pathlib import Path

# Raíz del monorepo (scripts/ está un nivel abajo)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = str(_REPO_ROOT / "api")


def setup_api_path() -> None:
    """Inserta api/ en sys.path[0]. Idempotente."""
    if _API_DIR not in sys.path:
        sys.path.insert(0, _API_DIR)


def load_settings():
    """Carga Settings de api/config.py. Retorna instancia configurada."""
    setup_api_path()
    from config import settings  # noqa: E402
    return settings


def get_ocr_client():
    """Retorna httpx.AsyncClient configurado para llama-server.

    Caller es responsable de llamar `await client.aclose()` al terminar.
    No usar como context manager — el client se comparte entre tareas
    concurrentes con asyncio.Semaphore.
    """
    import httpx  # noqa: E402

    s = load_settings()
    return httpx.AsyncClient(
        base_url=s.llama_server_url,
        timeout=s.llama_timeout_s,
    )
