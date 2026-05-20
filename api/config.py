"""Configuracion centralizada de la app (Pydantic Settings v2).

Single source of truth para variables de entorno. Lee `.env` desde la raiz
del repo (un nivel arriba de `api/`). Cualquier modulo que necesite config
debe `from config import settings`.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# api/config.py -> api/ -> raiz del repo
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Variables de entorno de la app.

    Cargadas desde `.env` en la raiz del repo. Cualquier var no declarada
    se ignora (`extra="ignore"`) para que el `.env` pueda contener tambien
    cosas que solo le interesan a docker-compose (POSTGRES_USER, etc.).
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Base de datos ------------------------------------------------------
    # Usamos el driver async (asyncpg) tanto para la app como para Alembic.
    database_url: str

    # --- Redis --------------------------------------------------------------
    redis_url: str

    # --- llama-server (glm-ocr) --------------------------------------------
    llama_server_url: str
    # Alias del modelo expuesto por llama-server (`-a GLM-OCR` en el script).
    # Va literal en el campo `model` del request OpenAI-compatible.
    llama_model_alias: str = "GLM-OCR"
    # Timeout total por request HTTP a llama-server (segundos).
    llama_timeout_s: float = 10.0
    # Reintentos ante errores de red o 5xx (NO ante 4xx ni JSON invalido).
    llama_max_retries: int = 3

    # --- Storage de uploads ------------------------------------------------
    # Directorio raiz donde se persisten los archivos originales subidos.
    # En Fase 1 es filesystem local; en Fase 5+ migrara a S3/B2 detras del
    # mismo contrato de `services/storage_service.py`. Default `./data/uploads`
    # relativo a la raiz del repo para que en dev local no requiera setup.
    upload_dir: Path = ROOT_DIR / "data" / "uploads"

    # --- JWT Auth (Fase 4) -------------------------------------------------
    # Clave secreta para firmar tokens HS256. Generar con:
    #   openssl rand -hex 32
    # MUST be set in production. En dev, si no existe en .env, Settings()
    # falla con ValidationError — esto es intencional (fuerza config explicita).
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- CORS (Fase 4) -----------------------------------------------------
    # Origen exacto del webapp Next.js. `allow_credentials=True` require que
    # `allow_origins` sea una lista de origenes especificos (no "*").
    webapp_origin: str = "http://localhost:3000"

    # --- Dataset evaluation (Fase 5.0) ------------------------------------
    # Opcionales — solo usados por scripts de evaluación en scripts/.
    # En producción estos campos no existen en .env y quedan None.
    dataset_dir: Path | None = None
    results_dir: Path | None = None


settings = Settings()  # type: ignore[call-arg]
