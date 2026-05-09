"""FastAPI application entry point for SmartVoucherDetection.

Run in dev mode from `api/`:

    uv run fastapi dev main.py

For production:

    uv run fastapi run main.py --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import health, history, upload

app = FastAPI(
    title="SmartVoucherDetection API",
    description="OCR + duplicate-detection backend for deposit slips.",
    version="0.1.0",
)

# CORS — permissive in dev. Tightened in Fase 4 once the webapp domain is fixed
# and multi-tenancy lands. See plan §4 (multi-tenant) and §5.10 (Nginx prod).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(history.router)
app.include_router(upload.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root redirect-ish helper — points clients at the OpenAPI docs."""
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "llama_server": settings.llama_server_url,
    }
