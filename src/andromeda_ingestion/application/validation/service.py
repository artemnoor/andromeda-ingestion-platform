"""Schema, ontology, DSL, evidence and confidence validation."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import (
    CandidateFact,
    CandidateRelation,
    CandidateRule,
    EvidenceRef,
    ExtractionResult,
    OntologySnapshot,
    PreparedDocument,
    RawArtifact,
    UnknownConceptCandidate,
    ValidationIssue,
    ValidationReport,
)
from andromeda_ingestion.domain.validation.dsl import validate_rule_dsl, validate_rule_effects
from andromeda_ingestion.infrastructure.config import Settings


class ExtractionValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def validate(
        self,
        result: ExtractionResult,
        ontology: OntologySnapshot,
        prepared: PreparedDocument | None = None,
        artifact: RawArtifact | None = None,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        review_ids: list[str] = []
        rejected_ids: list[str] = []
        valid_ids: list[str] = []
        known_properties = {str(item.get("code")) for item in ontology.properties if item.get("code")}
        known_relations = {str(item.get("code")) for item in ontology.relation_types if item.get("code")}

        candidates: list[CandidateFact | CandidateRelation | CandidateRule | UnknownConceptCandidate] = [
            *result.facts,
            *result.relations,
            *result.rules,
            *result.unknown_concepts,
        ]
        for candidate in candidates:
            confidence = Decimal(str(candidate.confidence))
            if not candidate.evidence:
                issues.append(
                    ValidationIssue(code="MISSING_EVIDENCE", message="Candidate has no evidence", path=str(candidate.candidate_id))
                )
                rejected_ids.append(candidate.candidate_id)
                continue
            if prepared is not None and artifact is not None and not all(
                self._evidence_matches(item, result, prepared, artifact) for item in candidate.evidence
            ):
                issues.append(
                    ValidationIssue(
                        code="EVIDENCE_MISMATCH",
                        message="Candidate evidence does not exactly match its source artifact and locator.",
                        path=str(candidate.candidate_id),
                    )
                )
                rejected_ids.append(candidate.candidate_id)
                continue
            if confidence < Decimal(str(self.settings.confidence_review_threshold)):
                review_ids.append(candidate.candidate_id)
                issues.append(
                    ValidationIssue(
                        code="LOW_CONFIDENCE",
                        message="Candidate confidence is below review threshold",
                        path=str(candidate.candidate_id),
                        severity="warning",
                    )
                )
                continue
            if isinstance(candidate, CandidateFact) and known_properties and candidate.property_code not in known_properties:
                review_ids.append(candidate.candidate_id)
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_PROPERTY",
                        message="Fact property is absent from ontology snapshot",
                        path=candidate.property_code,
                        severity="warning",
                    )
                )
                continue
            if isinstance(candidate, CandidateRelation) and known_relations and candidate.relation_type_code not in known_relations:
                review_ids.append(candidate.candidate_id)
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_RELATION",
                        message="Relation type is absent from ontology snapshot",
                        path=candidate.relation_type_code,
                        severity="warning",
                    )
                )
                continue
            if isinstance(candidate, CandidateRule):
                dsl_errors = validate_rule_dsl(candidate.conditions)
                effect_errors = validate_rule_effects(candidate.effects)
                if dsl_errors or effect_errors:
                    issues.append(
                        ValidationIssue(
                            code="INVALID_RULE_DSL" if dsl_errors else "INVALID_RULE_EFFECT",
                            message=f"Rule candidate failed closed Core contract validation: {dsl_errors or effect_errors}",
                            path=candidate.logical_key,
                        )
                    )
                    rejected_ids.append(candidate.candidate_id)
                    continue
            if isinstance(candidate, UnknownConceptCandidate):
                review_ids.append(candidate.candidate_id)
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_CONCEPT",
                        message="Unknown concept requires Core ontology review",
                        path=candidate.name,
                        severity="warning",
                    )
                )
                continue
            valid_ids.append(candidate.candidate_id)

        status: Literal["VALIDATED", "NEEDS_REVIEW", "REJECTED"] = (
            "REJECTED"
            if rejected_ids and not valid_ids and not review_ids
            else "NEEDS_REVIEW"
            if review_ids or rejected_ids
            else "VALIDATED"
        )
        return ValidationReport(
            extraction_id=result.id,
            status=status,
            issues=issues,
            validated_candidate_ids=valid_ids,
            review_candidate_ids=review_ids,
            rejected_candidate_ids=rejected_ids,
            completed_at=utc_now(),
        )

    @staticmethod
    def _evidence_matches(
        evidence: EvidenceRef,
        result: ExtractionResult,
        prepared: PreparedDocument,
        artifact: RawArtifact,
    ) -> bool:
        locator = evidence.locator
        if evidence.artifact_id != result.artifact_id or locator.artifact_id != result.artifact_id:
            return False
        if locator.source_url not in {artifact.canonical_url, artifact.final_url}:
            return False
        quote = evidence.quote or locator.quote
        if not quote:
            return False
        normalized_quote = re.sub(r"\s+", " ", quote).strip()
        if not normalized_quote:
            return False
        for chunk in prepared.content_chunks:
            chunk_locator = chunk.locator
            if chunk.artifact_id != result.artifact_id:
                continue
            if locator.page is not None and chunk_locator.page != locator.page:
                continue
            if locator.selector is not None and chunk_locator.selector != locator.selector:
                continue
            if locator.table is not None and chunk_locator.table != locator.table:
                continue
            if locator.row is not None and chunk_locator.row != locator.row:
                continue
            normalized_text = re.sub(r"\s+", " ", chunk.text).strip()
            if normalized_quote in normalized_text:
                return True
        return False
