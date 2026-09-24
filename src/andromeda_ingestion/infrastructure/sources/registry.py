"""Source registry entries and generic discovery configuration.

University-specific code stops at access metadata. Semantic extraction is selected
by profiles and provider adapters, not by a BMSTU parser class.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from andromeda_ingestion.domain.common import DiscoveryStrategy, FetchStrategy, SourceCategory, SourceType, TrustLevel
from andromeda_ingestion.domain.contracts import SourceDefinition


def _source(
    stable_key: str,
    organization: str,
    source_type: SourceType,
    url: str,
    *,
    document_kind: str,
    profile_code: str,
    fixture_path: str | None = None,
    source_id: str | None = None,
) -> SourceDefinition:
    metadata = {
        "document_kind": document_kind,
        "profile_code": profile_code,
        "discovered_items": [{"url": url, "document_kind": document_kind, "relevance_score": "1.0"}],
    }
    if fixture_path:
        metadata["fixture_path"] = fixture_path
    return SourceDefinition(
        id=source_id or uuid4().hex,
        stable_key=stable_key,
        organization=organization,
        source_category=SourceCategory.UNIVERSITY,
        source_type=source_type,
        base_url=url,
        discovery_strategy=DiscoveryStrategy.STATIC_URL,
        fetch_strategy=FetchStrategy.FIXTURE if fixture_path else FetchStrategy.HTTP,
        content_type="application/pdf" if source_type == SourceType.PDF else "text/html",
        trust_level=TrustLevel.OFFICIAL_PRIMARY,
        allowed_hosts=["bmstu.ru", "admissions.bmstu.ru"],
        metadata=metadata,
    )


def demo_source_definitions(fixture_root: str | Path) -> list[SourceDefinition]:
    root = str(Path(fixture_root).resolve())
    return [
        _source(
            "bmstu.programs.demo",
            "BMSTU",
            SourceType.WEB_PAGE,
            "https://admissions.bmstu.ru/programs/09.03.01",
            document_kind="program",
            profile_code="university_program",
            fixture_path=str(Path(root) / "bmstu" / "program.html"),
            source_id="src-bmstu-programs",
        ),
        _source(
            "bmstu.regulation.demo",
            "BMSTU",
            SourceType.PDF,
            "https://admissions.bmstu.ru/documents/admission-regulation-2026.pdf",
            document_kind="regulatory_document",
            profile_code="regulatory_document",
            fixture_path=str(Path(root) / "bmstu" / "admission-regulation-2026.pdf"),
            source_id="src-bmstu-regulation",
        ),
        _source(
            "bmstu.regulation.changed.demo",
            "BMSTU",
            SourceType.PDF,
            "https://admissions.bmstu.ru/documents/admission-regulation-2026-amended.pdf",
            document_kind="regulatory_document",
            profile_code="regulatory_document",
            fixture_path=str(Path(root) / "bmstu" / "admission-regulation-2026-amended.pdf"),
            source_id="src-bmstu-regulation-amended",
        ),
        _source(
            "bmstu.regulation.unknown.demo",
            "BMSTU",
            SourceType.PDF,
            "https://admissions.bmstu.ru/documents/admission-regulation-2026-unknown.pdf",
            document_kind="regulatory_document",
            profile_code="regulatory_document",
            fixture_path=str(Path(root) / "bmstu" / "admission-regulation-2026-unknown.pdf"),
            source_id="src-bmstu-regulation-unknown",
        ),
        _source(
            "bmstu.regulation.ambiguous.demo",
            "BMSTU",
            SourceType.PDF,
            "https://admissions.bmstu.ru/documents/admission-regulation-2026-ambiguous.pdf",
            document_kind="regulatory_document",
            profile_code="regulatory_document",
            fixture_path=str(Path(root) / "bmstu" / "admission-regulation-2026-ambiguous.pdf"),
            source_id="src-bmstu-regulation-ambiguous",
        ),
    ]
