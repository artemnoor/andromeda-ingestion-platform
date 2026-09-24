from decimal import Decimal

from andromeda_ingestion.application.changes.service import ChangeDetectionService
from andromeda_ingestion.domain.common import ConfidenceStatus, utc_now
from andromeda_ingestion.domain.contracts import CandidateRule, EvidenceLocator, EvidenceRef, ExtractionResult


def _result(threshold: int) -> ExtractionResult:
    evidence = [
        EvidenceRef(
            artifact_id="artifact",
            locator=EvidenceLocator(artifact_id="artifact", source_url="https://example.test/rule", page=1),
            quote="rule",
        )
    ]
    rule = CandidateRule(
        candidate_id=f"rule-{threshold}",
        logical_key="admission.additional_exam_bonus",
        conditions={
            "kind": "comparison",
            "operator": ">=",
            "left": {"kind": "applicant", "path": "additional_exam_score"},
            "right": {"kind": "literal", "value": threshold},
        },
        effects=[{"type": "ADD", "target": "admission_bonus", "value": 30}],
        confidence=Decimal("0.95"),
        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
        evidence=evidence,
    )
    return ExtractionResult(
        id=f"extraction-{threshold}",
        artifact_id="artifact",
        profile_id="profile",
        profile_version=1,
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
        document_type="regulatory_document",
        provider="mock",
        model="mock",
        prompt_version="prompt-1",
        rules=[rule],
        created_at=utc_now(),
    )


def test_rule_threshold_change_is_modified() -> None:
    changes = ChangeDetectionService().compare(_result(90), _result(85))
    assert len(changes) == 1
    assert changes[0]["kind"] == "MODIFIED"
    assert changes[0]["target_key"] == "rule:admission.additional_exam_bonus"
