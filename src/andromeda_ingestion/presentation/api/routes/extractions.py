from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/extractions", tags=["extractions"], responses=API_ERROR_RESPONSES)


@router.get("/{extraction_id}", summary="Read extraction result and persisted candidates")
async def get_extraction(extraction_id: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    return {
        "extraction": await services.repository.get_extraction(extraction_id),
        "candidates": await services.repository.list_candidates(extraction_id),
    }


@router.post("/{extraction_id}/validate", summary="Validate extraction output against schema, ontology and confidence policy")
async def validate_extraction(
    extraction_id: str, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    return await services.validation.validate(extraction_id)


@router.get("/{extraction_id}/candidates", summary="List extraction candidates")
async def list_candidates(extraction_id: str, services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    return await services.repository.list_candidates(extraction_id)
