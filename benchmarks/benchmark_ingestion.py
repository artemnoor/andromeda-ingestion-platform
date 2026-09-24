"""Small reproducible ingestion benchmark; numbers are environment-specific."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from andromeda_ingestion.application.changes.service import ChangeDetectionService
from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import ExtractionContext, RawArtifact
from andromeda_ingestion.infrastructure.ai.mock import MockDocumentUnderstanding
from andromeda_ingestion.infrastructure.ai.profiles import profile_map
from andromeda_ingestion.infrastructure.preparation.generic import GenericDocumentPreparation


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    body = (root / "fixtures" / "bmstu" / "admission-regulation-2026.pdf").read_bytes()
    preparer = GenericDocumentPreparation()
    provider = MockDocumentUnderstanding()
    profile = profile_map()["regulatory_document"]
    preparation_started = time.perf_counter()
    prepared = []
    for index in range(100):
        artifact = RawArtifact(
            id=f"bench-{index}",
            source_id="bench-source",
            requested_url="https://example.test/doc.pdf",
            canonical_url=f"https://example.test/doc-{index}.pdf",
            final_url="https://example.test/doc.pdf",
            retrieved_at=utc_now(),
            content_type="application/pdf",
            checksum="0" * 64,
            raw_content_location=f"bench/{index}",
            byte_size=len(body),
            metadata={"document_kind": "regulatory_document"},
            created_at=utc_now(),
        )
        prepared.append((artifact, await preparer.prepare(artifact, body)))
    preparation_ms = (time.perf_counter() - preparation_started) * 1000
    extraction_started = time.perf_counter()
    results = []
    for artifact, document in prepared:
        results.append(
            await provider.extract(
                ExtractionContext(
                    artifact=artifact,
                    prepared_document=document,
                    profile=profile,
                    trusted_instructions=profile.instructions,
                    untrusted_document_data=document.content_chunks,
                )
            )
        )
    extraction_ms = (time.perf_counter() - extraction_started) * 1000
    change_started = time.perf_counter()
    changes = ChangeDetectionService().compare(results[0], results[1])
    change_ms = (time.perf_counter() - change_started) * 1000
    print(
        {
            "documents": 100,
            "preparation_ms": round(preparation_ms, 3),
            "extraction_ms": round(extraction_ms, 3),
            "change_detection_ms": round(change_ms, 3),
            "changes": len(changes),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
