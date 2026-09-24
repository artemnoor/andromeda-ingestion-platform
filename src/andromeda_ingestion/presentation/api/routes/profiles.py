from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import ExtractionProfile
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import ProfileCreateRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"], responses=API_ERROR_RESPONSES)


@router.get("", summary="List active extraction profiles")
async def list_profiles(services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    # Profiles are intentionally addressed by code; the DB port exposes one version
    # lookup, so this endpoint returns the configured profile catalog.
    result: list[dict[str, Any]] = []
    for code in ("university_program", "regulatory_document", "generic"):
        item = await services.repository.get_profile_by_code(code)
        if item:
            result.append(item)
    return result


@router.post("", summary="Create a versioned extraction profile", status_code=201)
async def create_profile(
    payload: ProfileCreateRequest, _: Role = Depends(require_role(Role.ADMIN)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    profile = ExtractionProfile(id=uuid4().hex, created_at=utc_now(), **payload.model_dump())
    result = await services.repository.upsert_profile(profile.model_dump(mode="python"))
    await services.repository.commit()
    return result


@router.get("/{profile_code}", summary="Read the latest profile version")
async def get_profile(profile_code: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    result = await services.repository.get_profile_by_code(profile_code)
    if result is None:
        from andromeda_ingestion.domain.errors import NotFoundError

        raise NotFoundError("profile", profile_code)
    return result
