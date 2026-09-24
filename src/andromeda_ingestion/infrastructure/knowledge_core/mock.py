"""In-memory Core contract double; it models the integration boundary only."""

from __future__ import annotations

from uuid import uuid4

from andromeda_ingestion.domain.contracts import (
    CorePublishResult,
    ObservationCandidate,
    OntologySnapshot,
    RawArtifact,
    SourceDefinition,
    SourceRegistration,
)
from andromeda_ingestion.domain.ports.knowledge_core import KnowledgeCorePort


class MockKnowledgeCoreAdapter(KnowledgeCorePort):
    def __init__(self, confidence_review_threshold: float = 0.8) -> None:
        self.confidence_review_threshold = confidence_review_threshold
        self.sources: dict[str, dict] = {}
        self.source_documents: dict[str, dict] = {}
        self.observations: dict[str, dict] = {}
        self.ontology = OntologySnapshot(
            ontology_version_id="ontology-demo-v1",
            version_code="v1",
            object_types=[
                {"code": "University", "aliases": ["BMSTU", "МГТУ им. Н. Э. Баумана", "Bauman Moscow State Technical University"]},
                {"code": "Program"},
                {"code": "Curriculum"},
            ],
            properties=[{"code": "required_exam"}, {"code": "minimum_score"}, {"code": "budget_places"}, {"code": "tuition_per_year"}],
            relation_types=[{"code": "HAS_CURRICULUM"}],
        )

    async def get_ontology_snapshot(self) -> OntologySnapshot:
        return self.ontology

    async def register_source(self, source: SourceDefinition, artifact: RawArtifact) -> SourceRegistration:
        source_row = self.sources.setdefault(
            source.stable_key,
            {"id": f"core-source-{uuid4().hex[:12]}", "source": source.model_dump(mode="json")},
        )
        document_key = f"{source_row['id']}:{artifact.checksum}"
        document_row = self.source_documents.setdefault(
            document_key,
            {"id": f"core-document-{uuid4().hex[:12]}", "artifact": artifact.model_dump(mode="json")},
        )
        return SourceRegistration(source_id=source_row["id"], source_document_id=document_row["id"])

    async def publish_observation(
        self, source_id: str, candidate: ObservationCandidate, *, idempotency_key: str, correlation_id: str
    ) -> CorePublishResult:
        if idempotency_key in self.observations:
            return CorePublishResult.model_validate(self.observations[idempotency_key])
        needs_review = candidate.confidence < self.confidence_review_threshold or candidate.candidate_kind == "unknown_concept"
        result = CorePublishResult(
            candidate_id=candidate.candidate_id,
            core_source_id=source_id,
            core_observation_id=f"core-observation-{uuid4().hex[:12]}",
            status="NEEDS_REVIEW" if needs_review else "ACCEPTED_AS_OBSERVATION",
            review_id=f"core-review-{uuid4().hex[:12]}" if needs_review else None,
            proposal_id=f"core-proposal-{uuid4().hex[:12]}" if candidate.candidate_kind == "unknown_concept" else None,
            details={"candidate_kind": candidate.candidate_kind, "correlation_id": correlation_id, "raw_payload": candidate.raw_payload},
        )
        self.observations[idempotency_key] = result.model_dump(mode="json")
        return result
