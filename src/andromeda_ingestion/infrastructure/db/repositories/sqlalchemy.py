"""SQLAlchemy persistence adapter for ingestion metadata.

The adapter deliberately returns plain dictionaries at the application port.  The
domain and application layers therefore do not know about SQLAlchemy models or
JSON column names.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.errors import ConflictError, NotFoundError
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.infrastructure.db.models import (
    AuditEventModel,
    ChangeCandidateModel,
    DiscoveredItemModel,
    ExtractionCandidateModel,
    ExtractionModel,
    ExtractionProfileModel,
    JobModel,
    PipelineRunModel,
    PreparedDocumentModel,
    RawArtifactModel,
    SourceDefinitionModel,
)

ModelT = TypeVar("ModelT")


def _dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(f"unsupported datetime value: {value!r}")


def _id(data: dict[str, Any]) -> str:
    return str(data.get("id") or uuid4().hex)


def _json(value: Any, default: Any) -> Any:
    return default if value is None else value


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class SqlAlchemyIngestionRepository(IngestionRepositoryPort):
    """Concrete repository with optimistic updates for mutable pipeline state."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def database_ready(self) -> bool:
        await self.session.execute(select(1))
        return True

    async def get_source(self, source_id: str) -> dict[str, Any]:
        return self._source(await self._get(SourceDefinitionModel, source_id))

    async def get_source_by_key(self, stable_key: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(SourceDefinitionModel).where(SourceDefinitionModel.stable_key == stable_key))
        ).scalar_one_or_none()
        return self._source(row) if row else None

    async def list_sources(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        query = select(SourceDefinitionModel).order_by(SourceDefinitionModel.stable_key)
        if enabled is not None:
            query = query.where(SourceDefinitionModel.enabled == enabled)
        return [self._source(row) for row in (await self.session.execute(query)).scalars().all()]

    async def upsert_source(self, data: dict[str, Any]) -> dict[str, Any]:
        stable_key = str(data["stable_key"])
        row = (
            await self.session.execute(select(SourceDefinitionModel).where(SourceDefinitionModel.stable_key == stable_key))
        ).scalar_one_or_none()
        values = self._source_values(data)
        if row:
            for key, value in values.items():
                if key != "id":
                    setattr(row, key, value)
            row.updated_at = _dt(data.get("updated_at")) or utc_now()
        else:
            values.setdefault("created_at", utc_now())
            values.setdefault("updated_at", values["created_at"])
            row = SourceDefinitionModel(**values)
            self.session.add(row)
        await self.session.flush()
        return self._source(row)

    async def upsert_discovered_item(self, data: dict[str, Any]) -> dict[str, Any]:
        row = (
            await self.session.execute(
                select(DiscoveredItemModel).where(
                    DiscoveredItemModel.source_id == data["source_id"], DiscoveredItemModel.canonical_url == data["canonical_url"]
                )
            )
        ).scalar_one_or_none()
        values = self._discovered_values(data)
        if row:
            for key, value in values.items():
                if key != "id":
                    setattr(row, key, value)
        else:
            row = DiscoveredItemModel(**values)
            self.session.add(row)
        await self.session.flush()
        return self._discovered(row)

    async def get_discovered_item(self, item_id: str) -> dict[str, Any]:
        return self._discovered(await self._get(DiscoveredItemModel, item_id))

    async def list_discovered_items(self, source_id: str, limit: int = 200) -> list[dict[str, Any]]:
        query = (
            select(DiscoveredItemModel)
            .where(DiscoveredItemModel.source_id == source_id)
            .order_by(DiscoveredItemModel.discovered_at.desc())
            .limit(limit)
        )
        return [self._discovered(row) for row in (await self.session.execute(query)).scalars().all()]

    async def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        return self._artifact(await self._get(RawArtifactModel, artifact_id))

    async def find_artifact(self, source_id: str, canonical_url: str, checksum: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(RawArtifactModel).where(
                    RawArtifactModel.source_id == source_id,
                    RawArtifactModel.canonical_url == canonical_url,
                    RawArtifactModel.checksum == checksum,
                )
            )
        ).scalar_one_or_none()
        return self._artifact(row) if row else None

    async def get_current_artifact(self, source_id: str, canonical_url: str) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    select(RawArtifactModel)
                    .where(
                        RawArtifactModel.source_id == source_id,
                        RawArtifactModel.canonical_url == canonical_url,
                        RawArtifactModel.is_current.is_(True),
                    )
                    .order_by(RawArtifactModel.version.desc())
                )
            )
            .scalars()
            .first()
        )
        return self._artifact(row) if row else None

    async def create_artifact(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.find_artifact(str(data["source_id"]), str(data["canonical_url"]), str(data["checksum"]))
        if existing:
            return existing
        current = await self.get_current_artifact(str(data["source_id"]), str(data["canonical_url"]))
        if current:
            current_row = await self._get(RawArtifactModel, current["id"])
            current_row.is_current = False
        values = self._artifact_values(data)
        values["version"] = int(current["version"] + 1) if current else int(data.get("version", 1))
        values["previous_artifact_id"] = current["id"] if current else data.get("previous_artifact_id")
        row = RawArtifactModel(**values)
        self.session.add(row)
        await self.session.flush()
        return self._artifact(row)

    async def get_prepared(self, artifact_id: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(PreparedDocumentModel).where(PreparedDocumentModel.artifact_id == artifact_id))
        ).scalar_one_or_none()
        return self._prepared(row) if row else None

    async def upsert_prepared(self, data: dict[str, Any]) -> dict[str, Any]:
        row = (
            await self.session.execute(select(PreparedDocumentModel).where(PreparedDocumentModel.artifact_id == data["artifact_id"]))
        ).scalar_one_or_none()
        values = self._prepared_values(data)
        if row:
            for key, value in values.items():
                if key not in {"id", "artifact_id"}:
                    setattr(row, key, value)
        else:
            row = PreparedDocumentModel(**values)
            self.session.add(row)
        await self.session.flush()
        return self._prepared(row)

    async def get_profile(self, profile_id: str) -> dict[str, Any]:
        return self._profile(await self._get(ExtractionProfileModel, profile_id))

    async def get_profile_by_code(self, profile_code: str, version: int | None = None) -> dict[str, Any] | None:
        query = select(ExtractionProfileModel).where(ExtractionProfileModel.profile_code == profile_code)
        if version is not None:
            query = query.where(ExtractionProfileModel.version == version)
        else:
            query = query.order_by(ExtractionProfileModel.version.desc())
        row = (await self.session.execute(query)).scalars().first()
        return self._profile(row) if row else None

    async def upsert_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        row = (
            await self.session.execute(
                select(ExtractionProfileModel).where(
                    ExtractionProfileModel.profile_code == data["profile_code"], ExtractionProfileModel.version == data["version"]
                )
            )
        ).scalar_one_or_none()
        values = self._profile_values(data)
        if row:
            for key, value in values.items():
                if key not in {"id", "profile_code", "version"}:
                    setattr(row, key, value)
        else:
            row = ExtractionProfileModel(**values)
            self.session.add(row)
        await self.session.flush()
        return self._profile(row)

    async def create_extraction(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.find_extraction(str(data["artifact_id"]), str(data["profile_id"]), str(data["input_fingerprint"]))
        if existing:
            return existing
        row = ExtractionModel(**self._extraction_values(data))
        self.session.add(row)
        await self.session.flush()
        return self._extraction(row)

    async def get_extraction(self, extraction_id: str) -> dict[str, Any]:
        return self._extraction(await self._get(ExtractionModel, extraction_id))

    async def update_extraction_status(self, extraction_id: str, status: str) -> dict[str, Any]:
        row = await self._get(ExtractionModel, extraction_id)
        row.status = status
        await self.session.flush()
        return self._extraction(row)

    async def find_extraction(self, artifact_id: str, profile_id: str, input_fingerprint: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(ExtractionModel).where(
                    ExtractionModel.artifact_id == artifact_id,
                    ExtractionModel.profile_id == profile_id,
                    ExtractionModel.input_fingerprint == input_fingerprint,
                )
            )
        ).scalar_one_or_none()
        return self._extraction(row) if row else None

    async def find_latest_extraction_for_artifact(self, artifact_id: str, profile_id: str) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    select(ExtractionModel)
                    .where(ExtractionModel.artifact_id == artifact_id, ExtractionModel.profile_id == profile_id)
                    .order_by(ExtractionModel.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        return self._extraction(row) if row else None

    async def list_candidates(self, extraction_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query = (
            select(ExtractionCandidateModel)
            .where(ExtractionCandidateModel.extraction_id == extraction_id)
            .order_by(ExtractionCandidateModel.created_at)
        )
        if status:
            query = query.where(ExtractionCandidateModel.status == status)
        return [self._candidate(row) for row in (await self.session.execute(query)).scalars().all()]

    async def create_candidate(self, data: dict[str, Any]) -> dict[str, Any]:
        query = select(ExtractionCandidateModel).where(
            ExtractionCandidateModel.extraction_id == data["extraction_id"], ExtractionCandidateModel.natural_key == data["natural_key"]
        )
        existing = (await self.session.execute(query)).scalar_one_or_none()
        if existing:
            return self._candidate(existing)
        row = ExtractionCandidateModel(**self._candidate_values(data))
        self.session.add(row)
        await self.session.flush()
        return self._candidate(row)

    async def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        return self._candidate(await self._get(ExtractionCandidateModel, candidate_id))

    async def update_candidate(self, candidate_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        mapping = {
            "extraction_id": "extraction_id",
            "candidate_kind": "candidate_kind",
            "natural_key": "natural_key",
            "payload_json": "payload_json",
            "confidence": "confidence",
            "confidence_status": "confidence_status",
            "status": "status",
            "validation": "validation_json",
            "evidence": "evidence_json",
            "core_source_id": "core_source_id",
            "core_observation_id": "core_observation_id",
            "review_id": "review_id",
            "proposal_id": "proposal_id",
        }
        values = {db_key: data[key] for key, db_key in mapping.items() if key in data}
        for json_key in ("validation_json", "evidence_json", "payload_json"):
            if json_key in values:
                values[json_key] = _json(values[json_key], {} if json_key != "evidence_json" else [])
        values["updated_at"] = _dt(data.get("updated_at")) or utc_now()
        values["row_version"] = (expected_version or int(data.get("row_version", 1))) + 1
        query = update(ExtractionCandidateModel).where(ExtractionCandidateModel.id == candidate_id)
        if expected_version is not None:
            query = query.where(ExtractionCandidateModel.row_version == expected_version)
        result = await self.session.execute(query.values(**values))
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_UPDATE", "Candidate was changed by another process", {"candidate_id": candidate_id})
        await self.session.flush()
        return await self.get_candidate(candidate_id)

    async def upsert_change(self, data: dict[str, Any]) -> dict[str, Any]:
        row = (
            await self.session.execute(select(ChangeCandidateModel).where(ChangeCandidateModel.fingerprint == data["fingerprint"]))
        ).scalar_one_or_none()
        values = self._change_values(data)
        if row:
            return self._change(row)
        row = ChangeCandidateModel(**values)
        self.session.add(row)
        await self.session.flush()
        return self._change(row)

    async def list_changes(self, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = select(ChangeCandidateModel).order_by(ChangeCandidateModel.created_at.desc()).limit(limit)
        if kind:
            query = query.where(ChangeCandidateModel.kind == kind)
        return [self._change(row) for row in (await self.session.execute(query)).scalars().all()]

    async def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        return self._pipeline(await self._get(PipelineRunModel, pipeline_id))

    async def get_pipeline_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(PipelineRunModel).where(PipelineRunModel.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        return self._pipeline(row) if row else None

    async def create_pipeline(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.get_pipeline_by_key(str(data["idempotency_key"]))
        if existing:
            return existing
        row = PipelineRunModel(**self._pipeline_values(data))
        self.session.add(row)
        await self.session.flush()
        return self._pipeline(row)

    async def update_pipeline(self, pipeline_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        mapping = {
            "source_id": "source_id",
            "discovered_item_id": "discovered_item_id",
            "artifact_id": "artifact_id",
            "extraction_id": "extraction_id",
            "profile_id": "profile_id",
            "state": "state",
            "attempts": "attempts",
            "max_attempts": "max_attempts",
            "correlation_id": "correlation_id",
            "error_code": "error_code",
            "error_message": "error_message",
            "transition_history": "transition_history_json",
            "started_at": "started_at",
            "finished_at": "finished_at",
        }
        values = {db_key: data[key] for key, db_key in mapping.items() if key in data}
        if "transition_history_json" in values:
            values["transition_history_json"] = _json(values["transition_history_json"], [])
        for key in ("started_at", "finished_at"):
            if key in values:
                values[key] = _dt(values[key])
        values["updated_at"] = _dt(data.get("updated_at")) or utc_now()
        values["row_version"] = (expected_version or int(data.get("row_version", 1))) + 1
        query = update(PipelineRunModel).where(PipelineRunModel.id == pipeline_id)
        if expected_version is not None:
            query = query.where(PipelineRunModel.row_version == expected_version)
        result = await self.session.execute(query.values(**values))
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_UPDATE", "Pipeline was changed by another process", {"pipeline_id": pipeline_id})
        await self.session.flush()
        return await self.get_pipeline(pipeline_id)

    async def create_job(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.get_job_by_key(str(data["idempotency_key"]))
        if existing:
            return existing
        row = JobModel(**self._job_values(data))
        self.session.add(row)
        await self.session.flush()
        return self._job(row)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return self._job(await self._get(JobModel, job_id))

    async def get_job_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        row = (await self.session.execute(select(JobModel).where(JobModel.idempotency_key == idempotency_key))).scalar_one_or_none()
        return self._job(row) if row else None

    async def update_job(self, job_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        mapping = {
            "kind": "kind",
            "state": "state",
            "payload": "payload_json",
            "attempts": "attempts",
            "max_attempts": "max_attempts",
            "next_retry_at": "next_retry_at",
            "correlation_id": "correlation_id",
            "error_code": "error_code",
            "error_message": "error_message",
        }
        values = {db_key: data[key] for key, db_key in mapping.items() if key in data}
        if "payload_json" in values:
            values["payload_json"] = _json(values["payload_json"], {})
        if "next_retry_at" in values:
            values["next_retry_at"] = _dt(values["next_retry_at"])
        values["updated_at"] = _dt(data.get("updated_at")) or utc_now()
        values["row_version"] = (expected_version or int(data.get("row_version", 1))) + 1
        query = update(JobModel).where(JobModel.id == job_id)
        if expected_version is not None:
            query = query.where(JobModel.row_version == expected_version)
        result = await self.session.execute(query.values(**values))
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_UPDATE", "Job was changed by another process", {"job_id": job_id})
        await self.session.flush()
        return await self.get_job(job_id)

    async def list_jobs(self, state: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = select(JobModel).order_by(JobModel.created_at.desc()).limit(limit)
        if state:
            query = query.where(JobModel.state == state)
        return [self._job(row) for row in (await self.session.execute(query)).scalars().all()]

    async def record_audit(self, data: dict[str, Any]) -> dict[str, Any]:
        values = {
            "id": _id(data),
            "action": data["action"],
            "entity_type": data["entity_type"],
            "entity_id": data["entity_id"],
            "actor": data.get("actor", "SYSTEM"),
            "before_json": _jsonable(data.get("before")),
            "after_json": _jsonable(data.get("after")),
            "details_json": _jsonable(data.get("details", {})),
            "correlation_id": data.get("correlation_id", "system"),
            "created_at": _dt(data.get("created_at")) or utc_now(),
        }
        row = AuditEventModel(**values)
        self.session.add(row)
        await self.session.flush()
        return {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor": row.actor,
            "before": row.before_json,
            "after": row.after_json,
            "details": row.details_json,
            "correlation_id": row.correlation_id,
            "created_at": row.created_at,
        }

    async def _get(self, model: type[ModelT], key: str) -> ModelT:
        row = await self.session.get(model, key)
        if row is None:
            raise NotFoundError(model.__name__, key)
        return row

    @staticmethod
    def _source_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "stable_key": data["stable_key"],
            "organization": data["organization"],
            "source_category": str(data["source_category"]),
            "source_type": str(data["source_type"]),
            "base_url": data["base_url"],
            "discovery_strategy": str(data["discovery_strategy"]),
            "fetch_strategy": str(data["fetch_strategy"]),
            "content_type": data.get("content_type"),
            "trust_level": str(data.get("trust_level", "UNVERIFIED")),
            "refresh_policy_json": _json(data.get("refresh_policy"), {}),
            "enabled": data.get("enabled", True),
            "allowed_hosts_json": _json(data.get("allowed_hosts"), []),
            "metadata_json": _json(data.get("metadata"), {}),
            "version": data.get("version", 1),
            "created_at": _dt(data.get("created_at")) or utc_now(),
            "updated_at": _dt(data.get("updated_at")) or utc_now(),
        }

    @staticmethod
    def _discovered_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "source_id": data.get("source_id"),
            "canonical_url": data["canonical_url"],
            "document_kind": data["document_kind"],
            "relevance_score": data.get("relevance_score", 1),
            "discovered_at": _dt(data.get("discovered_at")) or utc_now(),
            "discovery_method": data.get("discovery_method", "STATIC_URL"),
            "metadata_json": _json(data.get("metadata"), {}),
            "status": data.get("status", "DISCOVERED"),
        }

    @staticmethod
    def _artifact_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "source_id": data.get("source_id"),
            "discovered_item_id": data.get("discovered_item_id"),
            "requested_url": data["requested_url"],
            "canonical_url": data["canonical_url"],
            "final_url": data.get("final_url", data["canonical_url"]),
            "retrieved_at": _dt(data.get("retrieved_at")) or utc_now(),
            "content_type": data.get("content_type"),
            "http_status": data.get("http_status"),
            "checksum": data["checksum"],
            "etag": data.get("etag"),
            "last_modified": data.get("last_modified"),
            "raw_content_location": data["raw_content_location"],
            "byte_size": data["byte_size"],
            "version": data.get("version", 1),
            "previous_artifact_id": data.get("previous_artifact_id"),
            "is_current": data.get("is_current", True),
            "metadata_json": _json(data.get("metadata"), {}),
            "created_at": _dt(data.get("created_at")) or utc_now(),
        }

    @staticmethod
    def _prepared_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "artifact_id": data["artifact_id"],
            "preparation_version": data["preparation_version"],
            "content_fingerprint": data["content_fingerprint"],
            "document_type": data["document_type"],
            "title": data.get("title"),
            "sections_json": _json(data.get("sections"), []),
            "tables_json": _json(data.get("tables"), []),
            "links_json": _json(data.get("links"), []),
            "chunks_json": _json(data.get("content_chunks"), []),
            "structural_hints_json": _json(data.get("structural_hints"), {}),
            "prepared_at": _dt(data.get("prepared_at")) or utc_now(),
        }

    @staticmethod
    def _profile_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "profile_code": data["profile_code"],
            "version": data["version"],
            "status": data.get("status", "ACTIVE"),
            "expected_document_types_json": _json(data.get("expected_document_types"), []),
            "expected_ontology_concepts_json": _json(data.get("expected_ontology_concepts"), []),
            "output_schema_json": _json(data.get("output_schema"), {}),
            "instructions": data["instructions"],
            "validation_rules_json": _json(data.get("validation_rules"), {}),
            "ai_strategy": data.get("ai_strategy", "mock"),
            "prompt_version": data.get("prompt_version", "prompt-1"),
            "metadata_json": _json(data.get("metadata"), {}),
            "created_at": _dt(data.get("created_at")) or utc_now(),
        }

    @staticmethod
    def _extraction_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "artifact_id": data["artifact_id"],
            "profile_id": data["profile_id"],
            "profile_version": data["profile_version"],
            "input_fingerprint": data["input_fingerprint"],
            "output_fingerprint": data["output_fingerprint"],
            "document_type": data["document_type"],
            "provider": data["provider"],
            "model": data["model"],
            "prompt_version": data["prompt_version"],
            "result_json": data["result_json"],
            "warnings_json": _json(data.get("warnings"), []),
            "confidence_summary_json": _json(data.get("confidence_summary"), {}),
            "duration_ms": data.get("duration_ms", 0),
            "token_usage_json": _json(data.get("token_usage"), {}),
            "estimated_cost": data.get("estimated_cost"),
            "status": data.get("status", "EXTRACTED"),
            "created_at": _dt(data.get("created_at")) or utc_now(),
        }

    @staticmethod
    def _candidate_values(data: dict[str, Any], include_defaults: bool = True) -> dict[str, Any]:
        values: dict[str, Any] = {
            "id": _id(data),
            "extraction_id": data.get("extraction_id"),
            "candidate_kind": data.get("candidate_kind"),
            "natural_key": data.get("natural_key"),
            "payload_json": data.get("payload_json"),
            "confidence": data.get("confidence"),
            "confidence_status": data.get("confidence_status", "UNKNOWN"),
            "status": data.get("status", "EXTRACTED"),
            "validation_json": _json(data.get("validation"), {}),
            "evidence_json": _json(data.get("evidence"), []),
            "core_source_id": data.get("core_source_id"),
            "core_observation_id": data.get("core_observation_id"),
            "review_id": data.get("review_id"),
            "proposal_id": data.get("proposal_id"),
            "row_version": data.get("row_version", 1),
            "created_at": _dt(data.get("created_at")) or utc_now(),
            "updated_at": _dt(data.get("updated_at")) or utc_now(),
        }
        if include_defaults:
            return values
        return {key: value for key, value in values.items() if key in data or key in {"updated_at", "row_version"}}

    @staticmethod
    def _change_values(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _id(data),
            "extraction_id": data["extraction_id"],
            "artifact_id": data["artifact_id"],
            "kind": data["kind"],
            "target_key": data["target_key"],
            "before_fingerprint": data.get("before_fingerprint"),
            "after_fingerprint": data.get("after_fingerprint"),
            "before_payload_json": data.get("before_payload"),
            "after_payload_json": data.get("after_payload"),
            "confidence": data["confidence"],
            "reason": data["reason"],
            "evidence_json": _json(data.get("evidence"), []),
            "status": data.get("status", "OPEN"),
            "fingerprint": data["fingerprint"],
            "created_at": _dt(data.get("created_at")) or utc_now(),
        }

    @staticmethod
    def _pipeline_values(data: dict[str, Any], include_defaults: bool = True) -> dict[str, Any]:
        values: dict[str, Any] = {
            "id": _id(data),
            "source_id": data.get("source_id"),
            "discovered_item_id": data.get("discovered_item_id"),
            "artifact_id": data.get("artifact_id"),
            "extraction_id": data.get("extraction_id"),
            "profile_id": data.get("profile_id"),
            "state": data.get("state"),
            "attempts": data.get("attempts", 0),
            "max_attempts": data.get("max_attempts", 3),
            "idempotency_key": data.get("idempotency_key"),
            "correlation_id": data.get("correlation_id"),
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message"),
            "transition_history_json": _json(data.get("transition_history"), []),
            "started_at": _dt(data.get("started_at")),
            "finished_at": _dt(data.get("finished_at")),
            "row_version": data.get("row_version", 1),
            "created_at": _dt(data.get("created_at")) or utc_now(),
            "updated_at": _dt(data.get("updated_at")) or utc_now(),
        }
        if include_defaults:
            return values
        return {key: value for key, value in values.items() if key in data or key in {"updated_at", "row_version"}}

    @staticmethod
    def _job_values(data: dict[str, Any], include_defaults: bool = True) -> dict[str, Any]:
        values: dict[str, Any] = {
            "id": _id(data),
            "kind": data.get("kind"),
            "state": data.get("state"),
            "payload_json": _json(data.get("payload"), {}),
            "attempts": data.get("attempts", 0),
            "max_attempts": data.get("max_attempts", 3),
            "next_retry_at": _dt(data.get("next_retry_at")),
            "idempotency_key": data.get("idempotency_key"),
            "correlation_id": data.get("correlation_id"),
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message"),
            "row_version": data.get("row_version", 1),
            "created_at": _dt(data.get("created_at")) or utc_now(),
            "updated_at": _dt(data.get("updated_at")) or utc_now(),
        }
        if include_defaults:
            return values
        return {key: value for key, value in values.items() if key in data or key in {"updated_at", "row_version"}}

    @staticmethod
    def _source(row: SourceDefinitionModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "stable_key": row.stable_key,
            "organization": row.organization,
            "source_category": row.source_category,
            "source_type": row.source_type,
            "base_url": row.base_url,
            "discovery_strategy": row.discovery_strategy,
            "fetch_strategy": row.fetch_strategy,
            "content_type": row.content_type,
            "trust_level": row.trust_level,
            "refresh_policy": row.refresh_policy_json or {},
            "enabled": row.enabled,
            "allowed_hosts": row.allowed_hosts_json or [],
            "metadata": row.metadata_json or {},
            "version": row.version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _discovered(row: DiscoveredItemModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_id": row.source_id,
            "canonical_url": row.canonical_url,
            "document_kind": row.document_kind,
            "relevance_score": row.relevance_score,
            "discovered_at": row.discovered_at,
            "discovery_method": row.discovery_method,
            "metadata": row.metadata_json or {},
            "status": row.status,
        }

    @staticmethod
    def _artifact(row: RawArtifactModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_id": row.source_id,
            "discovered_item_id": row.discovered_item_id,
            "requested_url": row.requested_url,
            "canonical_url": row.canonical_url,
            "final_url": row.final_url,
            "retrieved_at": row.retrieved_at,
            "content_type": row.content_type,
            "http_status": row.http_status,
            "checksum": row.checksum,
            "etag": row.etag,
            "last_modified": row.last_modified,
            "raw_content_location": row.raw_content_location,
            "byte_size": row.byte_size,
            "version": row.version,
            "previous_artifact_id": row.previous_artifact_id,
            "is_current": row.is_current,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at,
        }

    @staticmethod
    def _prepared(row: PreparedDocumentModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "artifact_id": row.artifact_id,
            "preparation_version": row.preparation_version,
            "content_fingerprint": row.content_fingerprint,
            "document_type": row.document_type,
            "title": row.title,
            "sections": row.sections_json or [],
            "tables": row.tables_json or [],
            "links": row.links_json or [],
            "content_chunks": row.chunks_json or [],
            "structural_hints": row.structural_hints_json or {},
            "prepared_at": row.prepared_at,
        }

    @staticmethod
    def _profile(row: ExtractionProfileModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "profile_code": row.profile_code,
            "version": row.version,
            "status": row.status,
            "expected_document_types": row.expected_document_types_json or [],
            "expected_ontology_concepts": row.expected_ontology_concepts_json or [],
            "output_schema": row.output_schema_json or {},
            "instructions": row.instructions,
            "validation_rules": row.validation_rules_json or {},
            "ai_strategy": row.ai_strategy,
            "prompt_version": row.prompt_version,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at,
        }

    @staticmethod
    def _extraction(row: ExtractionModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "artifact_id": row.artifact_id,
            "profile_id": row.profile_id,
            "profile_version": row.profile_version,
            "input_fingerprint": row.input_fingerprint,
            "output_fingerprint": row.output_fingerprint,
            "document_type": row.document_type,
            "provider": row.provider,
            "model": row.model,
            "prompt_version": row.prompt_version,
            "result_json": row.result_json,
            "warnings": row.warnings_json or [],
            "confidence_summary": row.confidence_summary_json or {},
            "duration_ms": float(row.duration_ms or 0),
            "token_usage": row.token_usage_json or {},
            "estimated_cost": row.estimated_cost,
            "status": row.status,
            "created_at": row.created_at,
        }

    @staticmethod
    def _candidate(row: ExtractionCandidateModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "extraction_id": row.extraction_id,
            "candidate_kind": row.candidate_kind,
            "natural_key": row.natural_key,
            "payload_json": row.payload_json,
            "confidence": row.confidence,
            "confidence_status": row.confidence_status,
            "status": row.status,
            "validation": row.validation_json or {},
            "evidence": row.evidence_json or [],
            "core_source_id": row.core_source_id,
            "core_observation_id": row.core_observation_id,
            "review_id": row.review_id,
            "proposal_id": row.proposal_id,
            "row_version": row.row_version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _change(row: ChangeCandidateModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "extraction_id": row.extraction_id,
            "artifact_id": row.artifact_id,
            "kind": row.kind,
            "target_key": row.target_key,
            "before_fingerprint": row.before_fingerprint,
            "after_fingerprint": row.after_fingerprint,
            "before_payload": row.before_payload_json,
            "after_payload": row.after_payload_json,
            "confidence": row.confidence,
            "reason": row.reason,
            "evidence": row.evidence_json or [],
            "status": row.status,
            "fingerprint": row.fingerprint,
            "created_at": row.created_at,
        }

    @staticmethod
    def _pipeline(row: PipelineRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_id": row.source_id,
            "discovered_item_id": row.discovered_item_id,
            "artifact_id": row.artifact_id,
            "extraction_id": row.extraction_id,
            "profile_id": row.profile_id,
            "state": row.state,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "idempotency_key": row.idempotency_key,
            "correlation_id": row.correlation_id,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "transition_history": row.transition_history_json or [],
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "row_version": row.row_version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _job(row: JobModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.kind,
            "state": row.state,
            "payload": row.payload_json or {},
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "next_retry_at": row.next_retry_at,
            "idempotency_key": row.idempotency_key,
            "correlation_id": row.correlation_id,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "row_version": row.row_version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
