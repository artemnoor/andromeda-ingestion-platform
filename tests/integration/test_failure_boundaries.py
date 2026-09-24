from __future__ import annotations

from pathlib import Path

from andromeda_ingestion.domain.contracts import (
    CorePublishResult,
    ExtractionContext,
    ExtractionResult,
    ObservationCandidate,
    OntologySnapshot,
    RawArtifact,
    SourceDefinition,
    SourceRegistration,
)
from andromeda_ingestion.domain.errors import UpstreamError, ValidationError
from andromeda_ingestion.infrastructure.ai.mock import MockDocumentUnderstanding
from andromeda_ingestion.infrastructure.knowledge_core.mock import MockKnowledgeCoreAdapter
from andromeda_ingestion.infrastructure.sources.registry import demo_source_definitions


def _source_payload(source, fixture_path: str | None = None) -> dict:
    return {
        "id": source.id,
        "stable_key": source.stable_key,
        "organization": source.organization,
        "source_category": source.source_category,
        "source_type": source.source_type,
        "base_url": source.base_url,
        "discovery_strategy": source.discovery_strategy,
        "fetch_strategy": source.fetch_strategy,
        "content_type": source.content_type,
        "trust_level": source.trust_level,
        "allowed_hosts": source.allowed_hosts,
        "metadata": {**source.metadata, **({"fixture_path": fixture_path} if fixture_path else {})},
    }


class InvalidOutputProvider:
    async def extract(self, context: ExtractionContext) -> ExtractionResult:
        raise ValidationError("AI_INVALID_OUTPUT", "Mock provider returned invalid structured output", {})


class UnavailableCore:
    async def get_ontology_snapshot(self) -> OntologySnapshot:
        raise UpstreamError("CORE_UNAVAILABLE", "Core is unavailable", {})

    async def register_source(self, source: SourceDefinition, artifact: RawArtifact) -> SourceRegistration:
        raise UpstreamError("CORE_UNAVAILABLE", "Core is unavailable", {})

    async def publish_observation(
        self,
        source_id: str,
        candidate: ObservationCandidate,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> CorePublishResult:
        raise UpstreamError("CORE_UNAVAILABLE", "Core is unavailable", {})


def test_invalid_ai_output_is_not_published(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[0]
    assert client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"}).status_code == 201
    item_id = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()[0]["id"]
    client.app.state.adapters.ai_router.provider = InvalidOutputProvider()

    result = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["state"] == "RETRYABLE"
    assert body["error_code"] == "AI_INVALID_OUTPUT"
    assert not client.app.state.adapters.core.observations

    client.app.state.adapters.ai_router.provider = MockDocumentUnderstanding()
    retried = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )
    assert retried.json()["state"] == "PUBLISHED"
    assert client.app.state.adapters.ai_router.provider.calls == 1


def test_core_outage_keeps_extraction_for_retry(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[0]
    assert client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"}).status_code == 201
    item_id = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()[0]["id"]
    client.app.state.adapters.core = UnavailableCore()

    result = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["state"] == "RETRYABLE"
    assert body["error_code"] == "CORE_UNAVAILABLE"
    extraction = client.get(f"/api/v1/extractions/{body['extraction_id']}")
    assert extraction.status_code == 200
    assert extraction.json()["extraction"]["status"] == "VALIDATED"

    provider = client.app.state.adapters.ai_router.provider
    client.app.state.adapters.core = MockKnowledgeCoreAdapter()
    retried = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )
    assert retried.status_code == 200
    assert retried.json()["state"] == "PUBLISHED"
    assert provider.calls == 1
