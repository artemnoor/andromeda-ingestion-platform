from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.domain.common import JobState, utc_now
from andromeda_ingestion.infrastructure.observability.correlation import correlation_id_context
from andromeda_ingestion.presentation.api.dependencies import Role, require_role
from andromeda_ingestion.presentation.api.errors import API_ERROR_RESPONSES
from andromeda_ingestion.presentation.api.schemas import JobCreateRequest, RetryJobRequest
from andromeda_ingestion.presentation.api.service_dependencies import get_services

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"], responses=API_ERROR_RESPONSES)


@router.get("", summary="List pipeline jobs")
async def list_jobs(state: str | None = None, services: ServiceBundle = Depends(get_services)) -> list[dict[str, Any]]:
    return await services.repository.list_jobs(state)


@router.post("", summary="Submit a restartable ingestion job", status_code=202)
async def create_job(
    payload: JobCreateRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    return await services.jobs.submit(payload.kind, payload.payload, payload.idempotency_key, correlation_id_context.get())


@router.get("/{job_id}", summary="Read a job")
async def get_job(job_id: str, services: ServiceBundle = Depends(get_services)) -> dict[str, Any]:
    return await services.repository.get_job(job_id)


@router.post("/{job_id}/retry", summary="Retry a failed pipeline job")
async def retry_job(
    job_id: str, payload: RetryJobRequest, _: Role = Depends(require_role(Role.EDITOR)), services: ServiceBundle = Depends(get_services)
) -> dict[str, Any]:
    job = await services.repository.get_job(job_id)
    if job["state"] not in {JobState.FAILED.value, JobState.RETRYABLE.value}:
        return job
    updated = await services.repository.update_job(
        job_id,
        {"state": JobState.PENDING.value, "attempts": 0, "error_code": None, "error_message": None, "updated_at": utc_now()},
        expected_version=job["row_version"],
    )
    await services.repository.record_audit(
        {
            "action": "JOB_RETRY_REQUESTED",
            "entity_type": "job",
            "entity_id": job_id,
            "actor": "EDITOR",
            "before": job,
            "after": updated,
            "details": {"reason": payload.reason},
            "correlation_id": job["correlation_id"],
        }
    )
    await services.repository.commit()
    return updated
