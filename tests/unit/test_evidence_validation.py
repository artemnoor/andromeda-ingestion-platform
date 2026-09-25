from datetime import UTC, datetime
from decimal import Decimal

import pytest

from andromeda_ingestion.application.validation.service import ExtractionValidator
from andromeda_ingestion.domain.contracts import (
    CandidateEntity,
    CandidateFact,
    ContentChunk,
    EvidenceLocator,
    EvidenceRef,
    ExtractionResult,
    OntologySnapshot,
    PreparedDocument,
    RawArtifact,
)
from andromeda_ingestion.infrastructure.config import Settings


def _validation_case(quote: str, evidence_page: int = 1):
    now = datetime.now(UTC)
    artifact = RawArtifact(
        id="artifact-evidence",
        source_id="source-evidence",
        requested_url="https://example.edu/program",
        canonical_url="https://example.edu/program",
        final_url="https://example.edu/program",
        retrieved_at=now,
        checksum="a" * 64,
        raw_content_location="source-evidence/a.bin",
        byte_size=1,
        created_at=now,
    )
    locator = EvidenceLocator(
        artifact_id=artifact.id,
        source_url=artifact.canonical_url,
        page=evidence_page,
        selector="#program",
        quote=quote,
    )
    fact = CandidateFact(
        candidate_id="fact-evidence",
        subject=CandidateEntity(
            stable_key="bmstu:09.03.01",
            object_type_code="Program",
            display_name="Informatics",
        ),
        property_code="program.code",
        value="09.03.01",
        value_type="string",
        confidence=Decimal("0.95"),
        evidence=[EvidenceRef(artifact_id=artifact.id, locator=locator, quote=quote)],
    )
    result = ExtractionResult(
        id="extraction-evidence",
        artifact_id=artifact.id,
        profile_id="profile-program",
        profile_version=1,
        input_fingerprint="b" * 64,
        output_fingerprint="c" * 64,
        document_type="program",
        provider="test",
        model="test",
        prompt_version="test-v1",
        facts=[fact],
        created_at=now,
    )
    chunk_locator = EvidenceLocator(
        artifact_id=artifact.id,
        source_url=artifact.canonical_url,
        page=1,
        selector="#program",
    )
    prepared = PreparedDocument(
        id="prepared-evidence",
        artifact_id=artifact.id,
        preparation_version="generic-2",
        content_fingerprint="d" * 64,
        document_type="program",
        content_chunks=[
            ContentChunk(
                id="chunk-evidence",
                artifact_id=artifact.id,
                text="Program code 09.03.01",
                ordinal=0,
                locator=chunk_locator,
            )
        ],
        prepared_at=now,
    )
    return artifact, prepared, result


@pytest.mark.asyncio
async def test_exact_evidence_quote_is_validated_against_artifact_and_locator() -> None:
    artifact, prepared, result = _validation_case("Program code 09.03.01")

    report = await ExtractionValidator(Settings(_env_file=None)).validate(result, OntologySnapshot(), prepared, artifact)

    assert report.status == "VALIDATED"
    assert report.validated_candidate_ids == ["fact-evidence"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quote", "page"),
    [("Program code 09.03.01 ...", 1), ("Program code 09.03.01", 2)],
)
async def test_inexact_quote_or_wrong_page_rejects_candidate(quote: str, page: int) -> None:
    artifact, prepared, result = _validation_case(quote, page)

    report = await ExtractionValidator(Settings(_env_file=None)).validate(result, OntologySnapshot(), prepared, artifact)

    assert report.status == "REJECTED"
    assert report.rejected_candidate_ids == ["fact-evidence"]
    assert report.issues[0].code == "EVIDENCE_MISMATCH"


@pytest.mark.asyncio
async def test_mixed_valid_and_rejected_candidates_require_review() -> None:
    artifact, prepared, result = _validation_case("Program code 09.03.01 ...")
    invalid_fact = result.facts[0]
    valid_quote = "Program code 09.03.01"
    valid_fact = invalid_fact.model_copy(
        update={
            "candidate_id": "fact-valid",
            "evidence": [
                EvidenceRef(
                    artifact_id=artifact.id,
                    locator=invalid_fact.evidence[0].locator.model_copy(update={"quote": valid_quote}),
                    quote=valid_quote,
                )
            ],
        }
    )
    result = result.model_copy(update={"facts": [valid_fact, invalid_fact]})

    report = await ExtractionValidator(Settings(_env_file=None)).validate(result, OntologySnapshot(), prepared, artifact)

    assert report.status == "NEEDS_REVIEW"
    assert report.validated_candidate_ids == ["fact-valid"]
    assert report.rejected_candidate_ids == ["fact-evidence"]
