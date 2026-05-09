"""Health check endpoints.

Minimal implementation for Fase 1 (1.1.2) — returns a static OK so we can
verify FastAPI is wired up. The full multi-service health check (llama-server,
postgres, redis) is delivered in task 1.7.2.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 with a static payload."""
    return {"status": "ok"}
