"""Validation use case that persists candidate review status atomically."""

from __future__ import annotations

from andromeda_ingestion.application.extraction.serialization import extraction_result, ontology_snapshot
from andromeda_ingestion.application.validation.service import ExtractionValidator
from andromeda_ingestion.domain.common import CandidateStatus
from andromeda_ingestion.domain.ports.knowledge_core import KnowledgeCorePort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort


class ValidationService:
    def __init__(self, repository: IngestionRepositoryPort, validator: ExtractionValidator, core: KnowledgeCorePort) -> None:
        self.repository = repository
        self.validator = validator
        self.core = core

    async def validate(self, extraction_id: str) -> dict:
        extraction = await self.repository.get_extraction(extraction_id)
        result = extraction_result(extraction["result_json"])
        try:
            ontology = ontology_snapshot(await self.core.get_ontology_snapshot())
        except Exception:
            ontology = ontology_snapshot({})
        report = await self.validator.validate(result, ontology)
        all_candidates = await self.repository.list_candidates(extraction_id)
        for row in all_candidates:
            if row["id"] in report.validated_candidate_ids:
                status = CandidateStatus.VALIDATED.value
            elif row["id"] in report.review_candidate_ids:
                status = CandidateStatus.NEEDS_REVIEW.value
            elif row["id"] in report.rejected_candidate_ids:
                status = CandidateStatus.REJECTED.value
            else:
                status = row["status"]
            await self.repository.update_candidate(
                row["id"],
                {
                    "status": status,
                    "validation": {"report_status": report.status, "issues": [item.model_dump(mode="json") for item in report.issues]},
                },
                expected_version=row["row_version"],
            )
        await self.repository.update_extraction_status(extraction_id, report.status)
        await self.repository.commit()
        return report.model_dump(mode="json")
