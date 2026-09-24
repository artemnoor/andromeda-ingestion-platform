import json
from datetime import UTC, datetime

import httpx
import pytest

from andromeda_ingestion.domain.contracts import (
    ContentChunk,
    EvidenceLocator,
    ExtractionContext,
    ExtractionProfile,
    ExtractionResult,
    OntologySnapshot,
    PreparedDocument,
    RawArtifact,
)
from andromeda_ingestion.domain.errors import UpstreamError, ValidationError
from andromeda_ingestion.infrastructure.ai.http_json import StructuredJsonHttpAIAdapter


@pytest.mark.asyncio
async def test_structured_ai_adapter_sends_complete_ontology_snapshot() -> None:
    captured: dict = {}
    result = ExtractionResult(
        id="extraction-1",
        artifact_id="artifact-1",
        profile_id="profile-1",
        profile_version=1,
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
        document_type="document",
        provider="configured",
        model="model-1",
        prompt_version="prompt-1",
        created_at=datetime.now(UTC),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"output": result.model_dump(mode="json")}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    artifact = RawArtifact(
        id="artifact-1",
        source_id="source-1",
        requested_url="https://example.com/document",
        canonical_url="https://example.com/document",
        final_url="https://example.com/document",
        retrieved_at=datetime.now(UTC),
        checksum="c" * 64,
        raw_content_location="source-1/cc.bin",
        byte_size=4,
        created_at=datetime.now(UTC),
    )
    locator = EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, fragment_id="root", quote="data")
    chunk = ContentChunk(id="chunk-1", artifact_id=artifact.id, text="data", ordinal=0, locator=locator)
    context = ExtractionContext(
        artifact=artifact,
        prepared_document=PreparedDocument(
            id="prepared-1",
            artifact_id=artifact.id,
            preparation_version="test",
            content_fingerprint="d" * 64,
            document_type="document",
            content_chunks=[chunk],
            prepared_at=datetime.now(UTC),
        ),
        profile=ExtractionProfile(
            id="profile-1",
            profile_code="generic",
            version=1,
            output_schema={"type": "object"},
            instructions="Extract facts.",
        ),
        ontology=OntologySnapshot(
            ontology_version_id="ontology-1",
            version_code="v1",
            object_types=[{"code": "Program"}],
            properties=[{"code": "tuition_per_year", "value_type": "integer"}],
            relation_types=[{"code": "HAS_CURRICULUM"}],
            rule_dsl_schema={"kinds": ["comparison"]},
        ),
        trusted_instructions="Extract facts.",
        untrusted_document_data=[chunk],
    )

    await adapter.extract(context)
    await client.aclose()

    payload = captured
    system_content = payload["messages"][0]["content"]
    user_content = payload["messages"][1]["content"]
    assert isinstance(system_content, str)
    assert '"ontology_version_id": "ontology-1"' in system_content
    assert '"object_types": [{"code": "Program"}]' in system_content
    assert '"properties": [{"code": "tuition_per_year", "value_type": "integer"}]' in system_content
    assert '"relation_types": [{"code": "HAS_CURRICULUM"}]' in system_content
    assert '"kinds": ["comparison"]' in system_content
    assert '"type": "object"' in system_content
    assert "UNTRUSTED" in user_content
    assert payload["response_format"]["type"] == "json_schema"


def _minimal_context() -> ExtractionContext:
    artifact = RawArtifact(
        id="artifact-errors",
        source_id="source-1",
        requested_url="https://example.com/document",
        canonical_url="https://example.com/document",
        final_url="https://example.com/document",
        retrieved_at=datetime.now(UTC),
        checksum="c" * 64,
        raw_content_location="source-1/cc.bin",
        byte_size=4,
        created_at=datetime.now(UTC),
    )
    locator = EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, fragment_id="root")
    chunk = ContentChunk(id="chunk-errors", artifact_id=artifact.id, text="data", ordinal=0, locator=locator)
    return ExtractionContext(
        artifact=artifact,
        prepared_document=PreparedDocument(
            id="prepared-errors",
            artifact_id=artifact.id,
            preparation_version="test",
            content_fingerprint="d" * 64,
            document_type="document",
            content_chunks=[chunk],
            prepared_at=datetime.now(UTC),
        ),
        profile=ExtractionProfile(
            id="profile-errors",
            profile_code="generic",
            version=1,
            output_schema={"type": "object"},
            instructions="Extract facts.",
        ),
        ontology=OntologySnapshot(),
        trusted_instructions="Extract facts.",
        untrusted_document_data=[chunk],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(429, "AI_RATE_LIMIT"), (500, "AI_PROVIDER_UNAVAILABLE")])
async def test_structured_ai_adapter_maps_provider_statuses(status: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "provider failure"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(UpstreamError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == expected


@pytest.mark.asyncio
async def test_structured_ai_adapter_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(UpstreamError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == "AI_TIMEOUT"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [httpx.Response(200, text="not json"), httpx.Response(200, json={"output": {}})])
async def test_structured_ai_adapter_rejects_invalid_output(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(response.status_code, headers=response.headers, content=response.content, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(ValidationError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == "AI_INVALID_OUTPUT"
