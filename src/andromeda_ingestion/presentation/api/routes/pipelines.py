from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.infrastructure.observability.correlation import correlation_id_context
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import PipelineRunRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"], responses=API_ERROR_RESPONSES)


@router.post("/run", summary="Run restartable discovery-to-Core pipeline")
async def run_pipeline(
    payload: PipelineRunRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    return await services.pipeline.run(
        payload.source_id,
        payload.item_id,
        profile_code=payload.profile_code,
        idempotency_key=payload.idempotency_key,
        correlation_id=correlation_id_context.get(),
    )


@router.get("/{pipeline_id}", summary="Read pipeline state and transition history")
async def get_pipeline(pipeline_id: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    return await services.repository.get_pipeline(pipeline_id)
