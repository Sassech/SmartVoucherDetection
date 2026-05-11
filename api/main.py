"""FastAPI application entry point for SmartVoucherDetection.

Run in dev mode from `api/`:

    uv run fastapi dev main.py

For production:

    uv run fastapi run main.py --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import health, history, report, upload, upload_async, validate, web_auth

app = FastAPI(
    title="SmartVoucherDetection API",
    description="OCR + duplicate-detection backend for deposit slips.",
    version="0.1.0",
)

# CORS — tightened in Fase 4 to specific webapp origin.
# `allow_credentials=True` requires explicit origin (not "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.webapp_origin],
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


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root redirect-ish helper — points clients at the OpenAPI docs."""
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "llama_server": settings.llama_server_url,
    }
