"""Deterministic AI adapter used by local development, tests and golden evals.

It models the provider contract and safety boundary: document text is treated as
untrusted data, while the profile and DSL schema are trusted control inputs.
No candidate produced here is canonical knowledge or an activation command.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

from andromeda_ingestion.domain.changes.fingerprints import fingerprint
from andromeda_ingestion.domain.common import ConfidenceStatus, utc_now
from andromeda_ingestion.domain.contracts import (
    CandidateEntity,
    CandidateFact,
    CandidateRelation,
    CandidateRule,
    EvidenceLocator,
    EvidenceRef,
    ExtractionContext,
    ExtractionProfile,
    ExtractionResult,
)
from andromeda_ingestion.domain.ports.ai import AIProviderRouterPort, DocumentUnderstandingPort


class MockAIProviderRouter(AIProviderRouterPort):
    def __init__(self, provider: DocumentUnderstandingPort | None = None) -> None:
        self.provider = provider or MockDocumentUnderstanding()

    async def provider_for(self, profile: ExtractionProfile) -> DocumentUnderstandingPort:
        return self.provider


class MockDocumentUnderstanding(DocumentUnderstandingPort):
    name = "mock"
    model = "mock-evidence-extractor-1"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, context: ExtractionContext) -> ExtractionResult:
        self.calls += 1
        started = time.perf_counter()
        text = "\n".join(chunk.text for chunk in context.untrusted_document_data)
        evidence = self._evidence(context)
        entities: list[CandidateEntity] = []
        facts: list[CandidateFact] = []
        relations: list[CandidateRelation] = []
        rules: list[CandidateRule] = []
        unknown_concepts = []
        warnings: list[str] = []

        if context.prepared_document.document_type == "program" or "09.03.01" in text:
            university = CandidateEntity(
                stable_key="university:bmstu",
                object_type_code="University",
                display_name="BMSTU",
                aliases=["МГТУ им. Н. Э. Баумана", "Bauman Moscow State Technical University"],
            )
            program = CandidateEntity(
                stable_key="program:bmstu:09.03.01",
                object_type_code="Program",
                display_name="Informatics and Computer Engineering",
                aliases=["09.03.01"],
            )
            entities.extend([university, program])
            facts.extend(
                [
                    CandidateFact(
                        candidate_id=uuid4().hex,
                        subject=program,
                        property_code="required_exam",
                        value=["russian", "mathematics", "computer_science"],
                        value_type="collection",
                        confidence=Decimal("0.99"),
                        confidence_status=ConfidenceStatus.VERIFIED,
                        evidence=evidence,
                    ),
                    CandidateFact(
                        candidate_id=uuid4().hex,
                        subject=program,
                        property_code="minimum_score",
                        value=40,
                        value_type="integer",
                        confidence=Decimal("0.98"),
                        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                        evidence=evidence,
                    ),
                    CandidateFact(
                        candidate_id=uuid4().hex,
                        subject=program,
                        property_code="budget_places",
                        value=120,
                        value_type="integer",
                        confidence=Decimal("0.97"),
                        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                        evidence=evidence,
                    ),
                    CandidateFact(
                        candidate_id=uuid4().hex,
                        subject=program,
                        property_code="tuition_per_year",
                        value=385000,
                        value_type="integer",
                        confidence=Decimal("0.96"),
                        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                        evidence=evidence,
                    ),
                ]
            )
            curriculum = CandidateEntity(
                stable_key="curriculum:bmstu:09.03.01:2026", object_type_code="Curriculum", display_name="Curriculum 09.03.01 2026"
            )
            relations.append(
                CandidateRelation(
                    candidate_id=uuid4().hex,
                    subject=program,
                    relation_type_code="HAS_CURRICULUM",
                    target=curriculum,
                    confidence=Decimal("0.96"),
                    confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                    evidence=evidence,
                )
            )

        if (
            context.prepared_document.document_type == "regulatory_document"
            or "additional exam" in text.lower()
            or "дополнительный экзамен" in text.lower()
        ):
            threshold_match = re.search(r"(?:score|балл|threshold|порог)\D{0,30}(\d{2,3})", text, flags=re.IGNORECASE)
            threshold = int(threshold_match.group(1)) if threshold_match else 90
            confidence = Decimal("0.54") if "ambiguous" in text.lower() or "неоднознач" in text.lower() else Decimal("0.96")
            confidence_status = ConfidenceStatus.UNCERTAIN if confidence < Decimal("0.8") else ConfidenceStatus.HIGH_CONFIDENCE
            rule = CandidateRule(
                candidate_id=uuid4().hex,
                logical_key="admission.additional_exam_bonus",
                rule_type="admission_benefit",
                scope={"organization": "BMSTU", "admission_campaign_year": 2026},
                conditions={
                    "kind": "comparison",
                    "operator": ">=",
                    "left": {"kind": "applicant", "path": "additional_exam_score"},
                    "right": {"kind": "literal", "value": threshold},
                },
                effects=[
                    {"type": "ADD", "target": "admission_bonus", "value": 30},
                    {"type": "EMIT_DERIVED", "target": "AdmissionBenefit", "value": {"code": "additional_exam_bonus", "points": 30}},
                ],
                priority=100,
                confidence=confidence,
                confidence_status=confidence_status,
                evidence=evidence,
                test_cases=[
                    {"name": "below threshold", "applicant": {"additional_exam_score": threshold - 1}, "expected_effects": []},
                    {
                        "name": "at threshold",
                        "applicant": {"additional_exam_score": threshold},
                        "expected_effects": [{"type": "ADD", "target": "admission_bonus", "value": 30}],
                    },
                ],
                metadata={
                    "document_title": "BMSTU Admission Regulation 2026",
                    "issuer": "BMSTU",
                    "document_number": "AD-2026-01",
                    "effective_date": "2026-03-01" if "ambiguous" not in text.lower() else None,
                },
            )
            rules.append(rule)
            if "minimum 2 of 3" in text.lower():
                rules.append(
                    CandidateRule(
                        candidate_id=uuid4().hex,
                        logical_key="benefit.three_condition.threshold",
                        rule_type="benefit",
                        scope={"organization": "BMSTU"},
                        conditions={
                            "kind": "quantifier",
                            "operator": "at_least",
                            "count": 2,
                            "items": [
                                {"kind": "context", "path": "condition_a"},
                                {"kind": "context", "path": "condition_b"},
                                {"kind": "context", "path": "condition_c"},
                            ],
                        },
                        effects=[{"type": "GRANT", "target": "benefit", "value": "Benefit X"}],
                        confidence=Decimal("0.94"),
                        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
                        evidence=evidence,
                        test_cases=[],
                    )
                )
        if "RegionalEducationalCoefficient" in text:
            from andromeda_ingestion.domain.contracts import UnknownConceptCandidate

            unknown_concepts.append(
                UnknownConceptCandidate(
                    candidate_id=uuid4().hex,
                    name="RegionalEducationalCoefficient",
                    description="A coefficient referenced by the document but absent from the supplied ontology snapshot.",
                    suggested_property="regional_educational_coefficient",
                    confidence=Decimal("0.91"),
                    reason="The source introduces a semantic concept that is not in the extraction context.",
                    evidence=evidence,
                )
            )

        payload = {
            "entities": [item.model_dump(mode="json") for item in entities],
            "facts": [item.model_dump(mode="json") for item in facts],
            "relations": [item.model_dump(mode="json") for item in relations],
            "rules": [item.model_dump(mode="json") for item in rules],
            "unknown_concepts": [item.model_dump(mode="json") for item in unknown_concepts],
        }
        return ExtractionResult(
            id=uuid4().hex,
            artifact_id=context.artifact.id,
            profile_id=context.profile.id,
            profile_version=context.profile.version,
            input_fingerprint=context.prepared_document.content_fingerprint,
            output_fingerprint=fingerprint(payload),
            document_type=context.prepared_document.document_type,
            provider=self.name,
            model=self.model,
            prompt_version=context.profile.prompt_version,
            entities=entities,
            facts=facts,
            relations=relations,
            rules=rules,
            unknown_concepts=unknown_concepts,
            confidence_summary=self._confidence_summary(facts, relations, rules, unknown_concepts),
            warnings=warnings,
            raw_provider_metadata={"safety": "document_content_treated_as_untrusted_data", "fixture": True},
            duration_ms=(time.perf_counter() - started) * 1000,
            token_usage={"input": len(text.split()), "output": len(payload)},
            created_at=utc_now(),
        )

    @staticmethod
    def _evidence(context: ExtractionContext) -> list[EvidenceRef]:
        chunks = context.prepared_document.content_chunks
        locator = (
            chunks[0].locator
            if chunks
            else EvidenceLocator(artifact_id=context.artifact.id, source_url=context.artifact.canonical_url, fragment_id="root")
        )
        return [EvidenceRef(artifact_id=context.artifact.id, locator=locator, quote=locator.quote, confidence=Decimal("0.99"))]

    @staticmethod
    def _confidence_summary(
        facts: list[CandidateFact], relations: list[CandidateRelation], rules: list[CandidateRule], unknown: Sequence[Any]
    ) -> dict[str, Decimal]:
        values = [item.confidence for item in [*facts, *relations, *rules, *unknown] if hasattr(item, "confidence")]
        return {
            "min": min(values) if values else Decimal("0"),
            "average": sum(values, Decimal("0")) / len(values) if values else Decimal("0"),
        }
