"""Schema, ontology, DSL, evidence and confidence validation."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import (
    CandidateFact,
    CandidateRelation,
    CandidateRule,
    ExtractionResult,
    OntologySnapshot,
    UnknownConceptCandidate,
    ValidationIssue,
    ValidationReport,
)
from andromeda_ingestion.domain.validation.dsl import EFFECTS, validate_rule_dsl
from andromeda_ingestion.infrastructure.config import Settings


class ExtractionValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def validate(self, result: ExtractionResult, ontology: OntologySnapshot) -> ValidationReport:
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
                invalid_effects = [effect.get("type") for effect in candidate.effects if effect.get("type") not in EFFECTS]
                if dsl_errors or invalid_effects:
                    issues.append(
                        ValidationIssue(
                            code="INVALID_RULE_DSL",
                            message=f"Rule candidate failed closed DSL validation: {dsl_errors or invalid_effects}",
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
            "REJECTED" if rejected_ids and not valid_ids and not review_ids else "NEEDS_REVIEW" if review_ids else "VALIDATED"
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
