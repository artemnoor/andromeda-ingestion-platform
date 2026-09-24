"""Evaluate deterministic extraction against the checked-in golden fixtures."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import ExtractionContext, RawArtifact
from andromeda_ingestion.infrastructure.ai.mock import MockDocumentUnderstanding
from andromeda_ingestion.infrastructure.ai.profiles import profile_map
from andromeda_ingestion.infrastructure.preparation.generic import GenericDocumentPreparation


async def evaluate_one(root: Path, golden: Path) -> dict[str, float | str]:
    expected = json.loads(golden.read_text(encoding="utf-8"))
    source_path = root / "fixtures" / expected["fixture"]
    body = source_path.read_bytes()
    artifact = RawArtifact(
        id="golden-artifact",
        source_id="golden-source",
        requested_url="https://admissions.bmstu.ru/golden",
        canonical_url="https://admissions.bmstu.ru/golden",
        final_url="https://admissions.bmstu.ru/golden",
        retrieved_at=utc_now(),
        content_type="application/pdf",
        checksum="0" * 64,
        raw_content_location="golden",
        byte_size=len(body),
        metadata={"document_kind": expected["document_type"]},
        created_at=utc_now(),
    )
    prepared = await GenericDocumentPreparation().prepare(artifact, body)
    profile = profile_map()["regulatory_document"]
    result = await MockDocumentUnderstanding().extract(
        ExtractionContext(
            artifact=artifact,
            prepared_document=prepared,
            profile=profile,
            trusted_instructions=profile.instructions,
            untrusted_document_data=prepared.content_chunks,
        )
    )
    actual_rules = {rule.logical_key for rule in result.rules}
    expected_rules = set(expected["expected_rule_keys"])
    rule_accuracy = len(actual_rules & expected_rules) / len(expected_rules) if expected_rules else 1.0
    threshold = next(
        (rule.conditions["right"]["value"] for rule in result.rules if rule.logical_key == "admission.additional_exam_bonus"), None
    )
    evidence_accuracy = 1.0 if all(item.evidence[0].locator.page == expected["expected_evidence_page"] for item in result.rules) else 0.0
    unknown_accuracy = 1.0 if {item.name for item in result.unknown_concepts} == set(expected["expected_unknown_concepts"]) else 0.0
    return {
        "fixture": expected["fixture"],
        "rule_accuracy": rule_accuracy,
        "threshold_accuracy": 1.0 if threshold == expected["expected_threshold"] else 0.0,
        "evidence_locator_accuracy": evidence_accuracy,
        "unknown_concept_accuracy": unknown_accuracy,
    }


async def evaluate(root: Path | None = None) -> list[dict[str, float | str]]:
    root = root or Path(__file__).resolve().parents[1]
    return [await evaluate_one(root, path) for path in sorted((root / "fixtures" / "golden").glob("*.json"))]


def main() -> None:
    print(json.dumps(asyncio.run(evaluate()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
