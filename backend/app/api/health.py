import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.readiness import Check

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Process is up. Never touches dependencies."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """All dependencies reachable (Postgres + pgvector, Redis, object store)."""
    checks: list[Check] = request.app.state.readiness_checks
    results = await asyncio.gather(*(check() for check in checks))
    body: dict[str, Any] = {
        "status": "ok" if all(r.ok for r in results) else "degraded",
        "checks": [
            {"name": r.name, "ok": r.ok, "latency_ms": r.latency_ms, "detail": r.detail}
            for r in results
        ],
    }
    return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)
