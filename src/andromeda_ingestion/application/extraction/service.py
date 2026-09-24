"""Provider-neutral extraction use case and candidate persistence."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from andromeda_ingestion.application.changes.service import ChangeDetectionService
from andromeda_ingestion.application.extraction.serialization import (
    extraction_profile,
    extraction_result,
    ontology_snapshot,
    prepared_document,
    raw_artifact,
)
from andromeda_ingestion.application.preparation.service import PreparationService
from andromeda_ingestion.domain.changes.fingerprints import natural_key
from andromeda_ingestion.domain.contracts import ExtractionContext, ExtractionProfile, OntologySnapshot
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.domain.ports.ai import AIProviderRouterPort
from andromeda_ingestion.domain.ports.knowledge_core import KnowledgeCorePort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.infrastructure.ai.profiles import DEFAULT_PROFILES


class ExtractionService:
    def __init__(
        self,
        repository: IngestionRepositoryPort,
        preparation: PreparationService,
        router: AIProviderRouterPort,
        core: KnowledgeCorePort,
        changes: ChangeDetectionService,
    ) -> None:
        self.repository = repository
        self.preparation = preparation
        self.router = router
        self.core = core
        self.changes = changes

    async def ensure_profile(self, profile_code: str, profile: ExtractionProfile | None = None) -> dict:
        existing = await self.repository.get_profile_by_code(profile_code)
        if existing:
            return existing
        profile = profile or next((item for item in DEFAULT_PROFILES if item.profile_code == profile_code), DEFAULT_PROFILES[-1])
        result = await self.repository.upsert_profile(profile.model_dump(mode="python"))
        await self.repository.commit()
        return result

    async def extract(self, artifact_id: str, profile_code: str | None = None) -> dict[str, Any]:
        artifact_data = await self.repository.get_artifact(artifact_id)
        artifact = raw_artifact(artifact_data)
        prepared_data = await self.repository.get_prepared(artifact_id)
        if not prepared_data:
            prepared_data = await self.preparation.prepare_artifact(artifact_id)
        prepared = prepared_document(prepared_data)
        profile_code = profile_code or str(artifact.metadata.get("profile_code", "generic"))
        profile_data = await self.ensure_profile(profile_code)
        profile = extraction_profile(profile_data)
        existing = await self.repository.find_extraction(artifact_id, profile.id, prepared.content_fingerprint)
        if existing:
            return {
                "extraction": existing,
                "candidates": await self.repository.list_candidates(existing["id"]),
                "cached": True,
                "changes": [],
            }
        ontology = await self._ontology()
        context = ExtractionContext(
            artifact=artifact,
            prepared_document=prepared,
            profile=profile,
            ontology=ontology,
            trusted_instructions=profile.instructions,
            untrusted_document_data=prepared.content_chunks,
        )
        provider = await self.router.provider_for(profile)
        result = await provider.extract(context)
        extraction_row = {
            "id": result.id,
            "artifact_id": result.artifact_id,
            "profile_id": result.profile_id,
            "profile_version": result.profile_version,
            "input_fingerprint": result.input_fingerprint,
            "output_fingerprint": result.output_fingerprint,
            "document_type": result.document_type,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "result_json": result.model_dump(mode="json"),
            "warnings": result.warnings,
            "confidence_summary": result.model_dump(mode="json").get("confidence_summary", {}),
            "duration_ms": result.duration_ms,
            "token_usage": result.token_usage,
            "estimated_cost": result.estimated_cost,
            "status": result.status,
            "created_at": result.created_at,
        }
        persisted = await self.repository.create_extraction(extraction_row)
        candidates: list[dict[str, Any]] = []
        for kind, values in (
            ("fact", result.facts),
            ("relation", result.relations),
            ("rule", result.rules),
            ("unknown_concept", result.unknown_concepts),
            ("change", result.changes),
        ):
            for candidate in values:
                payload = candidate.model_dump(mode="json")
                key = self._candidate_key(kind, payload)
                candidates.append(
                    await self.repository.create_candidate(
                        {
                            "id": candidate.candidate_id,
                            "extraction_id": result.id,
                            "candidate_kind": kind,
                            "natural_key": natural_key(kind, key),
                            "payload_json": payload,
                            "confidence": Decimal(str(candidate.confidence)),
                            "confidence_status": str(getattr(candidate, "confidence_status", "UNKNOWN")),
                            "evidence": [item.model_dump(mode="json") for item in candidate.evidence],
                            "status": "EXTRACTED",
                        }
                    )
                )
        previous = await self._previous_result(artifact, profile.id)
        change_rows: list[dict[str, Any]] = []
        for change in self.changes.compare(previous, result):
            change_rows.append(
                await self.repository.upsert_change({**change, "extraction_id": result.id, "artifact_id": artifact.id, "status": "OPEN"})
            )
        await self.repository.commit()
        return {"extraction": persisted, "candidates": candidates, "cached": False, "changes": change_rows}

    async def _ontology(self) -> OntologySnapshot:
        try:
            return ontology_snapshot(await self.core.get_ontology_snapshot())
        except UpstreamError:
            return OntologySnapshot()

    async def _previous_result(self, artifact: Any, profile_id: str) -> Any:
        if not artifact.previous_artifact_id:
            return None
        row = await self.repository.find_latest_extraction_for_artifact(artifact.previous_artifact_id, profile_id)
        return extraction_result(row["result_json"]) if row else None

    @staticmethod
    def _candidate_key(kind: str, payload: dict[str, Any]) -> str:
        if kind == "fact":
            return f"{payload['subject']['stable_key']}:{payload['property_code']}"
        if kind == "relation":
            return f"{payload['subject']['stable_key']}:{payload['relation_type_code']}:{payload['target']['stable_key']}"
        if kind == "rule":
            return str(payload["logical_key"])
        if kind == "unknown_concept":
            return str(payload["name"])
        return str(payload.get("candidate_id", natural_key(payload)))
