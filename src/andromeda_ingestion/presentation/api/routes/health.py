from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_ingestion.infrastructure.observability.metrics import metrics_payload
from andromeda_ingestion.presentation.api.dependencies import get_session

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await request.app.state.adapters.services(session).repository.database_ready()
    return {"status": "ready"}


@router.get("/metrics", summary="Prometheus metrics")
async def metrics() -> Response:
    return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4")
