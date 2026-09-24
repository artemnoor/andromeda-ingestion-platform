from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import ExtractionRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"], responses=API_ERROR_RESPONSES)


@router.get("/{artifact_id}", summary="Read immutable raw artifact metadata")
async def get_artifact(artifact_id: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    return await services.repository.get_artifact(artifact_id)


@router.post("/{artifact_id}/prepare", summary="Prepare an artifact for AI extraction")
async def prepare_artifact(
    artifact_id: str, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    return await services.preparation.prepare_artifact(artifact_id)


@router.post("/{artifact_id}/extract", summary="Extract typed evidence-backed candidates")
async def extract_artifact(
    artifact_id: str,
    payload: ExtractionRequest | None = None,
    _: Role = Depends(require_role(Role.EDITOR)),
    services: ServiceBundle = Depends(get_services),
) -> dict[str, Any]:
    result = await services.extraction.extract(artifact_id, payload.profile_code if payload else None)
    return result
