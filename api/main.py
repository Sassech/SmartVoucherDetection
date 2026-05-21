"""FastAPI application entry point for SmartVoucherDetection.

Run in dev mode from `api/`:

    uv run fastapi dev main.py

For production:

    uv run fastapi run main.py --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import health, history, report, upload, upload_async, validate, web_auth, web_comprobantes, web_stats

app = FastAPI(
    title="SmartVoucherDetection API",
    description="OCR + duplicate-detection backend for deposit slips.",
    version="0.1.0",
)

# CORS — Fase 6.F: usa settings.cors_origins (lista configurable via env var
# CORS_ORIGINS). Reemplaza el hardcoded [settings.webapp_origin] de Fase 4.
# `allow_credentials=True` requires explicit origins (not "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(history.router)
app.include_router(upload.router)
app.include_router(validate.router)
app.include_router(report.router)
app.include_router(upload_async.router)
app.include_router(web_auth.router)
app.include_router(web_comprobantes.router)
app.include_router(web_stats.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root redirect-ish helper — points clients at the OpenAPI docs."""
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "llama_server": settings.llama_server_url,
    }
