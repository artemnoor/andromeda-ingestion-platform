import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from andromeda_ingestion.domain.common import ConfidenceStatus, DiscoveryStrategy, FetchStrategy, SourceCategory, SourceType, TrustLevel
from andromeda_ingestion.domain.contracts import (
    CandidateEntity,
    CandidateRule,
    EvidenceLocator,
    EvidenceRef,
    ObservationCandidate,
    RawArtifact,
    SourceDefinition,
)
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.knowledge_core.http import KnowledgeCoreHttpAdapter


@pytest.mark.asyncio
async def test_core_http_adapter_registers_document_and_uses_its_id_for_observation() -> None:
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        seen.append((request.url.path, payload))
        if request.url.path.endswith("/ontology/snapshot"):
            return httpx.Response(200, json={"schema_version": "1.0", "object_types": [], "properties": [], "relation_types": []}, request=request)
        if request.url.path.endswith("/sources"):
            return httpx.Response(201, json={"id": "core-source-1"}, request=request)
        if request.url.path.endswith("/source-documents"):
            return httpx.Response(201, json={"id": "core-document-1"}, request=request)
        return httpx.Response(201, json={"id": "core-observation-1", "status": "ACCEPTED_AS_OBSERVATION"}, request=request)

    client = httpx.AsyncClient(base_url="https://core.example", transport=httpx.MockTransport(handler))
    adapter = KnowledgeCoreHttpAdapter(Settings(app_env="test", knowledge_core_url="https://core.example"), client=client)
    source = SourceDefinition(
        id="source-1",
        stable_key="example.source",
        organization="Example",
        source_category=SourceCategory.OTHER_OFFICIAL_SOURCE,
        source_type=SourceType.WEB_PAGE,
        base_url="https://example.com/page",
        discovery_strategy=DiscoveryStrategy.STATIC_URL,
        fetch_strategy=FetchStrategy.HTTP,
        trust_level=TrustLevel.UNVERIFIED,
    )
    artifact = RawArtifact(
        id="artifact-1",
        source_id=source.id,
        discovered_item_id="item-1",
        requested_url=source.base_url,
        canonical_url=source.base_url,
        final_url=source.base_url,
        retrieved_at=datetime.now(UTC),
        checksum="a" * 64,
        raw_content_location="source-1/aa.bin",
        byte_size=5,
        created_at=datetime.now(UTC),
    )
    registration = await adapter.register_source(source, artifact)
    candidate = ObservationCandidate(
        candidate_id="candidate-1",
        candidate_kind="fact",
        subject_candidate=CandidateEntity(stable_key="program:1", object_type_code="Program", display_name="Program"),
        property_candidate="tuition_per_year",
        value=100,
        value_type="integer",
        evidence=[
            EvidenceRef(
                artifact_id=artifact.id,
                locator=EvidenceLocator(artifact_id=artifact.id, source_url=source.base_url, fragment_id="root"),
            )
        ],
        confidence=Decimal("0.9"),
        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
        source_document_id=registration.source_document_id,
    )
    result = await adapter.publish_observation("core-source-1", candidate, idempotency_key="candidate-1", correlation_id="corr-1")
    await client.aclose()

    assert registration.source_id == "core-source-1"
    assert registration.source_document_id == "core-document-1"
    assert result.core_observation_id == "core-observation-1"
    observation_payload = next(payload for path, payload in seen if path.endswith("/observations"))
    assert observation_payload["source_document_id"] == "core-document-1"


@pytest.mark.asyncio
async def test_core_http_adapter_publishes_rule_candidate_to_dedicated_endpoint() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/candidates"):
            captured.update(json.loads(request.content))
            return httpx.Response(
                201,
                json={
                    "candidate_id": "rule-candidate-1",
                    "rule_id": "core-rule-1",
                    "provenance_id": "core-provenance-1",
                    "status": "NEEDS_REVIEW",
                    "review_id": "review-1",
                    "proposal_id": "proposal-1",
                },
                request=request,
            )
        return httpx.Response(200, json={}, request=request)

    client = httpx.AsyncClient(base_url="https://core.example", transport=httpx.MockTransport(handler))
    adapter = KnowledgeCoreHttpAdapter(Settings(app_env="test", knowledge_core_url="https://core.example"), client=client)
    artifact = RawArtifact(
        id="artifact-rule-1",
        source_id="source-1",
        requested_url="https://example.com/rule",
        canonical_url="https://example.com/rule",
        final_url="https://example.com/rule",
        retrieved_at=datetime.now(UTC),
        checksum="b" * 64,
        raw_content_location="source-1/bb.bin",
        byte_size=5,
        created_at=datetime.now(UTC),
    )
    candidate = CandidateRule(
        candidate_id="rule-candidate-1",
        logical_key="admission.bonus",
        conditions={"kind": "literal", "value": True},
        effects=[{"type": "SET", "target": "bonus", "value": 10}],
        confidence=Decimal("0.95"),
        confidence_status=ConfidenceStatus.HIGH_CONFIDENCE,
        evidence=[
            EvidenceRef(
                artifact_id=artifact.id,
                locator=EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, fragment_id="root"),
            )
        ],
    )
    result = await adapter.publish_rule_candidate(
        "core-source-1", "core-document-1", candidate, idempotency_key="rule-1", correlation_id="corr-1"
    )
    await client.aclose()
    assert result.core_rule_id == "core-rule-1"
    assert result.core_provenance_id == "core-provenance-1"
    assert result.status == "NEEDS_REVIEW"
    assert captured["source_id"] == "core-source-1"
    assert captured["source_document_id"] == "core-document-1"
    assert captured["candidate_id"] == "rule-candidate-1"
