"""Explicit refreshable and restartable pipeline state machine."""

from __future__ import annotations

import logging
from uuid import uuid4

from andromeda_ingestion.application.extraction.service import ExtractionService
from andromeda_ingestion.application.fetching.service import FetchService
from andromeda_ingestion.application.preparation.service import PreparationService
from andromeda_ingestion.application.publishing.service import PublishingService
from andromeda_ingestion.application.validation.use_case import ValidationService
from andromeda_ingestion.domain.common import PipelineState, utc_now
from andromeda_ingestion.domain.errors import DomainError
from andromeda_ingestion.domain.pipelines.state import assert_transition
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.infrastructure.config import Settings

logger = logging.getLogger(__name__)

RETRYABLE_STAGES = {
    PipelineState.FETCHING,
    PipelineState.PREPARING,
    PipelineState.EXTRACTING,
    PipelineState.VALIDATING,
    PipelineState.PUBLISHING,
}


class PipelineOrchestrator:
    def __init__(
        self,
        repository: IngestionRepositoryPort,
        fetch: FetchService,
        prepare: PreparationService,
        extract: ExtractionService,
        validate: ValidationService,
        publish: PublishingService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.fetch = fetch
        self.prepare = prepare
        self.extract = extract
        self.validate = validate
        self.publish = publish
        self.settings = settings

    async def run(
        self, source_id: str, item_id: str, *, profile_code: str | None = None, idempotency_key: str | None = None, correlation_id: str
    ) -> dict:
        key = idempotency_key or f"pipeline:{source_id}:{item_id}:{profile_code or 'auto'}"
        existing = await self.repository.get_pipeline_by_key(key)
        if existing and existing["state"] in {
            PipelineState.PUBLISHED.value,
            PipelineState.SKIPPED_UNCHANGED.value,
            PipelineState.NEEDS_REVIEW.value,
        }:
            run = await self._start_refresh(existing)
        elif existing and existing["state"] == PipelineState.RETRYABLE.value:
            run = await self._start_retry(existing)
        elif existing and existing["state"] == PipelineState.FAILED.value:
            return existing
        else:
            run = existing or await self.repository.create_pipeline(
                {
                    "id": uuid4().hex,
                    "source_id": source_id,
                    "discovered_item_id": item_id,
                    "state": PipelineState.DISCOVERED.value,
                    "attempts": 0,
                    "max_attempts": self.settings.job_max_attempts,
                    "idempotency_key": key,
                    "correlation_id": correlation_id,
                    "transition_history": [],
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            await self.repository.commit()
            run = await self._transition(
                run, PipelineState.FETCHING, attempts=int(run["attempts"]) + 1, started_at=run.get("started_at") or utc_now()
            )
        logger.info(
            "pipeline_run_started",
            extra={"pipeline_id": run["id"], "pipeline_key": key[:16], "state": run["state"], "correlation_id": correlation_id},
        )
        try:
            return await self._continue(run, source_id, item_id, profile_code, correlation_id)
        except DomainError as exc:
            return await self._record_failure(run, exc.code, exc.message)
        except Exception as exc:
            logger.exception("pipeline_unexpected_failure", extra={"pipeline_id": run["id"], "correlation_id": correlation_id})
            return await self._record_failure(run, "UNEXPECTED_ERROR", str(exc)[:2000])

    async def _start_refresh(self, run: dict) -> dict:
        return await self._transition(
            run,
            PipelineState.FETCHING,
            attempts=1,
            started_at=utc_now(),
            finished_at=None,
            error_code=None,
            error_message=None,
            artifact_id=None,
            extraction_id=None,
            profile_id=None,
        )

    async def _start_retry(self, run: dict) -> dict:
        if int(run["attempts"]) >= int(run["max_attempts"]):
            return await self._transition(
                run,
                PipelineState.FAILED,
                finished_at=utc_now(),
                error_code=run.get("error_code") or "RETRY_LIMIT_EXCEEDED",
                error_message=run.get("error_message") or "Pipeline retry limit has been reached.",
            )
        resume_state = self._resume_state(run)
        if resume_state is None:
            resume_state = PipelineState.FETCHING
        logger.info("pipeline_retry_resuming", extra={"pipeline_id": run["id"], "resume_from": resume_state.value})
        return await self._transition(
            run,
            resume_state,
            attempts=int(run["attempts"]) + 1,
            started_at=run.get("started_at") or utc_now(),
            finished_at=None,
            error_code=None,
            error_message=None,
        )

    async def _continue(
        self, run: dict, source_id: str, item_id: str, profile_code: str | None, correlation_id: str
    ) -> dict:
        report: dict | None = None
        while True:
            state = PipelineState(run["state"])
            if state == PipelineState.FETCHING:
                fetched = await self.fetch.fetch_item(source_id, item_id)
                run = await self._transition(run, PipelineState.FETCHED, artifact_id=fetched["artifact"]["id"])
                if fetched["unchanged"]:
                    return await self._transition(run, PipelineState.SKIPPED_UNCHANGED, finished_at=utc_now())
                continue
            if state == PipelineState.FETCHED:
                run = await self._transition(run, PipelineState.PREPARING)
                continue
            if state == PipelineState.PREPARING:
                await self.prepare.prepare_artifact(run["artifact_id"])
                run = await self._transition(run, PipelineState.PREPARED)
                continue
            if state == PipelineState.PREPARED:
                run = await self._transition(run, PipelineState.EXTRACTING)
                continue
            if state == PipelineState.EXTRACTING:
                extraction = await self.extract.extract(run["artifact_id"], profile_code)
                run = await self._transition(
                    run,
                    PipelineState.EXTRACTED,
                    extraction_id=extraction["extraction"]["id"],
                    profile_id=extraction["extraction"]["profile_id"],
                )
                continue
            if state == PipelineState.EXTRACTED:
                run = await self._transition(run, PipelineState.VALIDATING)
                continue
            if state == PipelineState.VALIDATING:
                report = await self.validate.validate(run["extraction_id"])
                run = await self._transition(run, PipelineState.VALIDATED)
                continue
            if state == PipelineState.VALIDATED:
                run = await self._transition(run, PipelineState.PUBLISHING)
                continue
            if state == PipelineState.PUBLISHING:
                published = await self.publish.publish(run["extraction_id"], correlation_id)
                has_review = (report or {}).get("status") == "NEEDS_REVIEW" or any(
                    item["core"]["status"] == "NEEDS_REVIEW" for item in published
                )
                return await self._transition(
                    run,
                    PipelineState.NEEDS_REVIEW if has_review else PipelineState.PUBLISHED,
                    finished_at=utc_now(),
                    error_code="NEEDS_REVIEW" if has_review else None,
                    error_message="Review is required for one or more candidates" if has_review else None,
                )
            return run

    async def _record_failure(self, run: dict, code: str, message: str) -> dict:
        current = await self.repository.get_pipeline(run["id"])
        current_state = PipelineState(current["state"])
        retryable = current_state in RETRYABLE_STAGES and int(current["attempts"]) < int(current["max_attempts"])
        target = PipelineState.RETRYABLE if retryable else PipelineState.FAILED
        logger.error(
            "pipeline_stage_failed",
            extra={"pipeline_id": run["id"], "stage": current_state.value, "error_code": code, "retryable": retryable},
        )
        return await self._transition(
            run,
            target,
            error_code=code,
            error_message=message[:2000],
            finished_at=utc_now() if target == PipelineState.FAILED else None,
        )

    @staticmethod
    def _resume_state(run: dict) -> PipelineState | None:
        for transition in reversed(run.get("transition_history", [])):
            if transition.get("to") in {PipelineState.RETRYABLE.value, PipelineState.FAILED.value}:
                source = transition.get("from")
                if source in {state.value for state in RETRYABLE_STAGES}:
                    return PipelineState(source)
        return None

    async def _transition(self, run: dict, target: PipelineState, **fields: object) -> dict:
        current = await self.repository.get_pipeline(run["id"])
        source = PipelineState(current["state"])
        assert_transition(source, target)
        history = [*current.get("transition_history", []), {"from": source.value, "to": target.value, "at": utc_now().isoformat()}]
        data = {**fields, "state": target.value, "transition_history": history, "updated_at": utc_now()}
        updated = await self.repository.update_pipeline(run["id"], data, expected_version=int(current["row_version"]))
        await self.repository.record_audit(
            {
                "action": "PIPELINE_TRANSITION",
                "entity_type": "pipeline",
                "entity_id": run["id"],
                "actor": "SYSTEM",
                "before": current,
                "after": updated,
                "details": {"from": source.value, "to": target.value},
                "correlation_id": current["correlation_id"],
            }
        )
        await self.repository.commit()
        run.clear()
        run.update(updated)
        return updated
