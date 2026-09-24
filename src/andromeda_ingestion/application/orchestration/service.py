"""Explicit restartable pipeline state machine."""

from __future__ import annotations

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
            return existing
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
        try:
            await self._transition(
                run, PipelineState.FETCHING, attempts=int(run["attempts"]) + 1, started_at=run.get("started_at") or utc_now()
            )
            fetched = await self.fetch.fetch_item(source_id, item_id)
            await self._transition(run, PipelineState.FETCHED, artifact_id=fetched["artifact"]["id"])
            if fetched["unchanged"]:
                return await self._transition(run, PipelineState.SKIPPED_UNCHANGED, finished_at=utc_now())
            await self._transition(run, PipelineState.PREPARING)
            await self.prepare.prepare_artifact(fetched["artifact"]["id"])
            await self._transition(run, PipelineState.PREPARED)
            await self._transition(run, PipelineState.EXTRACTING)
            extraction = await self.extract.extract(fetched["artifact"]["id"], profile_code)
            await self._transition(
                run,
                PipelineState.EXTRACTED,
                extraction_id=extraction["extraction"]["id"],
                profile_id=extraction["extraction"]["profile_id"],
            )
            await self._transition(run, PipelineState.VALIDATING)
            report = await self.validate.validate(extraction["extraction"]["id"])
            await self._transition(run, PipelineState.VALIDATED)
            await self._transition(run, PipelineState.PUBLISHING)
            published = await self.publish.publish(extraction["extraction"]["id"], correlation_id)
            has_review = report["status"] == "NEEDS_REVIEW" or any(item["core"]["status"] == "NEEDS_REVIEW" for item in published)
            return await self._transition(
                run,
                PipelineState.NEEDS_REVIEW if has_review else PipelineState.PUBLISHED,
                finished_at=utc_now(),
                error_code="NEEDS_REVIEW" if has_review else None,
                error_message="Review is required for one or more candidates" if has_review else None,
            )
        except DomainError as exc:
            current = await self.repository.get_pipeline(run["id"])
            current_state = PipelineState(current["state"])
            target = (
                PipelineState.RETRYABLE
                if current_state in {PipelineState.FETCHING, PipelineState.PREPARING, PipelineState.EXTRACTING, PipelineState.PUBLISHING}
                and int(current["attempts"]) < int(current["max_attempts"])
                else PipelineState.FAILED
            )
            return await self._transition(
                run,
                target,
                error_code=exc.code,
                error_message=exc.message,
                finished_at=utc_now() if target == PipelineState.FAILED else None,
            )
        except Exception as exc:
            current = await self.repository.get_pipeline(run["id"])
            current_state = PipelineState(current["state"])
            target = (
                PipelineState.RETRYABLE
                if current_state in {PipelineState.FETCHING, PipelineState.PREPARING, PipelineState.EXTRACTING, PipelineState.PUBLISHING}
                else PipelineState.FAILED
            )
            return await self._transition(
                run,
                target,
                error_code="UNEXPECTED_ERROR",
                error_message=str(exc)[:2000],
                finished_at=utc_now() if target == PipelineState.FAILED else None,
            )

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
