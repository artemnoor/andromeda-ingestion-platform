from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import DiscoveryRunRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"], responses=API_ERROR_RESPONSES)


@router.post("/run", summary="Run configured source discovery")
async def run(
    payload: DiscoveryRunRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> list[dict[str, Any]]:
    return await services.source.discover(payload.source_id)
