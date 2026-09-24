"""Publish evidence-backed candidates to Core without bypassing its API."""

from __future__ import annotations

from decimal import Decimal

from andromeda_ingestion.domain.common import CandidateStatus, ConfidenceStatus
from andromeda_ingestion.domain.contracts import CandidateEntity, ObservationCandidate, RawArtifact, SourceDefinition
from andromeda_ingestion.domain.ports.knowledge_core import KnowledgeCorePort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort


class PublishingService:
    def __init__(self, repository: IngestionRepositoryPort, core: KnowledgeCorePort) -> None:
        self.repository = repository
        self.core = core

    async def publish(self, extraction_id: str, correlation_id: str) -> list[dict]:
        extraction = await self.repository.get_extraction(extraction_id)
        artifact = RawArtifact.model_validate(await self.repository.get_artifact(extraction["artifact_id"]))
        source = SourceDefinition.model_validate(await self.repository.get_source(artifact.source_id))
        core_source_id = await self.core.register_source(source, artifact)
        results: list[dict] = []
        for row in await self.repository.list_candidates(extraction_id):
            if row["status"] == CandidateStatus.REJECTED.value or row.get("core_observation_id"):
                continue
            candidate = self._observation(row)
            result = await self.core.publish_observation(
                core_source_id, candidate, idempotency_key=f"ingestion:{row['id']}", correlation_id=correlation_id
            )
            status = (
                CandidateStatus.NEEDS_REVIEW.value
                if result.review_id or result.status == "NEEDS_REVIEW"
                else CandidateStatus.PUBLISHED.value
            )
            updated = await self.repository.update_candidate(
                row["id"],
                {
                    "status": status,
                    "core_source_id": core_source_id,
                    "core_observation_id": result.core_observation_id,
                    "review_id": result.review_id,
                    "proposal_id": result.proposal_id,
                },
                expected_version=row["row_version"],
            )
            results.append({"candidate": updated, "core": result.model_dump(mode="json")})
        await self.repository.commit()
        return results

    @staticmethod
    def _observation(row: dict) -> ObservationCandidate:
        payload = row["payload_json"]
        kind = row["candidate_kind"]
        if kind == "fact":
            subject = CandidateEntity.model_validate(payload["subject"])
            property_candidate = payload["property_code"]
            value = payload.get("value")
            value_type = payload.get("value_type")
            relation_candidate = None
        elif kind == "relation":
            subject = CandidateEntity.model_validate(payload["subject"])
            property_candidate = None
            value = payload.get("properties", {})
            value_type = "object"
            relation_candidate = {
                "relation_type_code": payload["relation_type_code"],
                "target": payload["target"],
                "properties": payload.get("properties", {}),
            }
        elif kind == "rule":
            subject = CandidateEntity(
                stable_key=f"rule:{payload['logical_key']}", object_type_code="Rule", display_name=payload["logical_key"]
            )
            property_candidate = f"rule:{payload['logical_key']}"
            value = {
                "conditions": payload["conditions"],
                "effects": payload["effects"],
                "exceptions": payload.get("exceptions", []),
                "scope": payload.get("scope", {}),
            }
            value_type = "reference"
            relation_candidate = None
        elif kind == "unknown_concept":
            subject = CandidateEntity(
                stable_key=f"unknown:{payload['name']}", object_type_code="UnknownConcept", display_name=payload["name"]
            )
            property_candidate = payload.get("suggested_property") or payload["name"]
            value = payload
            value_type = "reference"
            relation_candidate = None
        else:
            subject = CandidateEntity(
                stable_key=f"change:{payload.get('target_key', row['id'])}",
                object_type_code="ChangeCandidate",
                display_name=payload.get("target_key", row["id"]),
            )
            property_candidate = "change_candidate"
            value = payload
            value_type = "reference"
            relation_candidate = None
        return ObservationCandidate(
            candidate_id=row["id"],
            candidate_kind=kind,
            subject_candidate=subject,
            property_candidate=property_candidate,
            relation_candidate=relation_candidate,
            value=value,
            value_type=value_type,
            evidence=[item for item in [*map(lambda item: item, row.get("evidence", []))] if item],
            confidence=Decimal(str(row["confidence"])),
            confidence_status=ConfidenceStatus(row["confidence_status"]),
            ontology_version_id=payload.get("ontology_version_id"),
            raw_payload={"candidate_kind": kind, "candidate": payload},
        )
