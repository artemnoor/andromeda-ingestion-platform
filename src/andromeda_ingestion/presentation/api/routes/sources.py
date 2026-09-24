from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.domain.contracts import SourceDefinition
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import DiscoveryRunRequest, FetchRequest, SourceCreateRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/sources", tags=["sources"], responses=API_ERROR_RESPONSES)


@router.post("", summary="Register or update an ingestion source", status_code=201)
async def create_source(
    payload: SourceCreateRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    source = SourceDefinition(
        id=payload.id or uuid4().hex,
        stable_key=payload.stable_key,
        organization=payload.organization,
        source_category=payload.source_category,
        source_type=payload.source_type,
        base_url=str(payload.base_url),
        discovery_strategy=payload.discovery_strategy,
        fetch_strategy=payload.fetch_strategy,
        content_type=payload.content_type,
        trust_level=payload.trust_level,
        refresh_policy=payload.refresh_policy,
        allowed_hosts=payload.allowed_hosts,
        metadata=payload.metadata,
    )
    return await services.source.create_or_update(source)


@router.get("", summary="List registered sources")
async def list_sources(services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    return await services.source.list_sources()


@router.get("/{source_id}", summary="Read a source definition")
async def get_source(source_id: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    return await services.repository.get_source(source_id)


@router.post("/discovery/run", summary="Discover documents for a source", status_code=200)
async def run_discovery(
    payload: DiscoveryRunRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> list[dict[str, Any]]:
    return await services.source.discover(payload.source_id)


@router.post("/{source_id}/discover", summary="Discover documents for a source", status_code=200)
async def discover_source(
    source_id: str, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> list[dict[str, Any]]:
    return await services.source.discover(source_id)


@router.get("/{source_id}/discovered", summary="List discovered source items")
async def list_discovered(source_id: str, services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    return await services.source.list_discovered(source_id)


@router.post("/{source_id}/fetch", summary="Fetch one discovered URL into immutable raw storage")
async def fetch_source(
    source_id: str, payload: FetchRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    result = await services.fetch.fetch_item(source_id, payload.item_id)
    return {"artifact": result["artifact"], "unchanged": result["unchanged"]}
