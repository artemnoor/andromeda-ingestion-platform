from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/changes", tags=["changes"], responses=API_ERROR_RESPONSES)


@router.get("", summary="List evidence-backed change candidates")
async def list_changes(kind: str | None = Query(default=None), services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    return await services.repository.list_changes(kind)
