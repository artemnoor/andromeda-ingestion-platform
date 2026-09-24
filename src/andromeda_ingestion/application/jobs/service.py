"""Small synchronous job facade, replaceable by a worker adapter later."""

from __future__ import annotations

from uuid import uuid4

from andromeda_ingestion.application.orchestration.service import PipelineOrchestrator
from andromeda_ingestion.domain.common import JobState, PipelineState, utc_now
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort


class JobService:
    def __init__(self, repository: IngestionRepositoryPort, pipeline: PipelineOrchestrator) -> None:
        self.repository = repository
        self.pipeline = pipeline

    async def submit(self, kind: str, payload: dict, idempotency_key: str, correlation_id: str) -> dict:
        existing = await self.repository.get_job_by_key(idempotency_key)
        if existing:
            return existing
        job = await self.repository.create_job(
            {
                "id": uuid4().hex,
                "kind": kind,
                "state": JobState.PENDING.value,
                "payload": payload,
                "attempts": 0,
                "max_attempts": 3,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        await self.repository.commit()
        if kind != "PIPELINE":
            return job
        if not payload.get("source_id") or not payload.get("item_id"):
            updated = await self.repository.update_job(
                job["id"],
                {
                    "state": JobState.FAILED.value,
                    "error_code": "VALIDATION_FAILED",
                    "error_message": "PIPELINE job requires source_id and item_id",
                },
                expected_version=job["row_version"],
            )
            await self.repository.commit()
            return updated
        running = await self.repository.update_job(
            job["id"], {"state": JobState.RUNNING.value, "attempts": 1}, expected_version=job["row_version"]
        )
        await self.repository.commit()
        result = await self.pipeline.run(
            payload["source_id"],
            payload["item_id"],
            profile_code=payload.get("profile_code"),
            idempotency_key=payload.get("pipeline_idempotency_key"),
            correlation_id=correlation_id,
        )
        final_state = (
            JobState.NEEDS_REVIEW.value
            if result["state"] == PipelineState.NEEDS_REVIEW.value
            else JobState.SUCCEEDED.value
            if result["state"] in {PipelineState.PUBLISHED.value, PipelineState.SKIPPED_UNCHANGED.value}
            else JobState.RETRYABLE.value
        )
        updated = await self.repository.update_job(
            running["id"],
            {"state": final_state, "error_code": result.get("error_code"), "error_message": result.get("error_message")},
            expected_version=running["row_version"],
        )
        await self.repository.commit()
        return updated
