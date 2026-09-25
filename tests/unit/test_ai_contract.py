import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from andromeda_ingestion.application.container import AdapterContainer
from andromeda_ingestion.application.extraction.service import ExtractionService
from andromeda_ingestion.domain.contracts import (
    ContentChunk,
    EvidenceLocator,
    ExtractionContext,
    ExtractionProfile,
    LLMExtractionPayload,
    OntologySnapshot,
    PreparedDocument,
    RawArtifact,
)
from andromeda_ingestion.domain.errors import UpstreamError, ValidationError
from andromeda_ingestion.infrastructure.ai.http_json import StructuredJsonHttpAIAdapter
from andromeda_ingestion.infrastructure.config import Settings


def test_ai_timeout_setting_is_passed_to_provider_adapter(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mock_ai_enabled=False,
        ai_provider="polza",
        ai_endpoint="https://ai.example/chat/completions",
        ai_api_key="test-key",
        ai_timeout_seconds=180,
        artifact_storage_root=str(tmp_path / "artifacts"),
        fixture_root=str(tmp_path),
    )

    container = AdapterContainer.from_settings(settings)

    assert isinstance(container.ai_router.provider, StructuredJsonHttpAIAdapter)
    assert container.ai_router.provider.timeout_seconds == 180


def test_ordinary_test_settings_cannot_select_live_ai_from_dotenv() -> None:
    settings = Settings(app_env="test")
    container = AdapterContainer.from_settings(settings)

    assert settings.ai_provider == "mock"
    assert not settings.ai_endpoint
    assert not settings.ai_api_key
    assert settings.mock_ai_enabled is True
    assert not isinstance(container.ai_router.provider, StructuredJsonHttpAIAdapter)


@pytest.mark.asyncio
async def test_structured_ai_adapter_sends_complete_ontology_snapshot() -> None:
    captured: dict = {}
    semantic_payload = _empty_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": semantic_payload.model_dump(mode="json"),
                "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter(
        "https://ai.example/extract", "secret", "model-1", client=client, provider="configured"
    )
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

    result = await adapter.extract(context)
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
    document_json = user_content.partition("\n")[2].partition("\nAll chunks inherit")[0]
    document_bundle = json.loads(document_json)
    assert document_bundle["artifact"] == {
        "artifact_id": artifact.id,
        "canonical_url": artifact.canonical_url,
        "final_url": artifact.final_url,
    }
    assert document_bundle["chunks"][0]["text"] == "data"
    assert document_bundle["chunks"][0]["locator"]["quote"] == "data"
    assert "source_url" not in document_bundle["chunks"][0]["locator"]
    assert payload["response_format"] == {"type": "json_object"}
    assert result.artifact_id == artifact.id
    assert result.profile_id == "profile-1"
    assert result.provider == "configured"
    assert result.model == "model-1"
    assert len(result.input_fingerprint) == 64
    assert len(result.output_fingerprint) == 64
    assert result.token_usage == {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}
    assert result.created_at.tzinfo is not None


def _empty_payload() -> LLMExtractionPayload:
    return LLMExtractionPayload(
        entities=[],
        facts=[],
        relations=[],
        rules=[],
        unknown_concepts=[],
        changes=[],
    )


def test_llm_payload_schema_is_self_consistent_and_empty_payload_is_valid() -> None:
    schema = LLMExtractionPayload.model_json_schema()
    assert set(schema["required"]).issubset(schema["properties"])
    assert LLMExtractionPayload.model_validate(
        {
            "entities": [],
            "facts": [],
            "relations": [],
            "rules": [],
            "unknown_concepts": [],
            "changes": [],
            "confidence_summary": {},
            "warnings": [],
        }
    ) == _empty_payload()


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
async def test_structured_ai_adapter_maps_timeout_and_logs_safe_request_metrics(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(UpstreamError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == "AI_TIMEOUT"
    request_record = next(record for record in caplog.records if record.message == "ai_provider_request_started")
    timeout_record = next(record for record in caplog.records if record.message == "ai_provider_timeout")
    assert request_record.document_chunk_count == 1
    assert request_record.document_character_count == len("data")
    assert request_record.request_bytes > 0
    assert timeout_record.provider_elapsed_ms >= 0
    assert timeout_record.request_bytes == request_record.request_bytes
    assert not hasattr(request_record, "api_key")


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


@pytest.mark.asyncio
async def test_empty_semantic_payload_builds_full_result_without_provider_metadata() -> None:
    semantic = _empty_payload().model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": semantic}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    result = await adapter.extract(_minimal_context())
    await client.aclose()

    assert result.entities == []
    assert result.facts == []
    assert result.artifact_id == "artifact-errors"
    assert result.profile_id == "profile-errors"
    assert result.provider == "openai-compatible"
    assert result.model == "model-1"
    assert result.input_fingerprint != "c" * 64
    assert result.output_fingerprint != "d" * 64


@pytest.mark.asyncio
async def test_json_object_mode_uses_same_local_contract() -> None:
    semantic = _empty_payload().model_dump(mode="json")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(semantic)}}]}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter(
        "https://ai.example/extract", "secret", "model-1", client=client, structured_output_mode="json_object"
    )
    result = await adapter.extract(_minimal_context())
    await client.aclose()

    assert captured["response_format"] == {"type": "json_object"}
    assert result.rules == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"artifact_id": "hallucinated"},
        {"provider": "hallucinated"},
        {"created_at": datetime.now(UTC).isoformat()},
    ],
)
async def test_llm_system_metadata_is_rejected_by_strict_semantic_contract(extra: dict) -> None:
    semantic = {**_empty_payload().model_dump(mode="json"), **extra}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": semantic}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(ValidationError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == "AI_INVALID_OUTPUT"


@pytest.mark.asyncio
async def test_malformed_semantic_field_is_rejected() -> None:
    semantic = {**_empty_payload().model_dump(mode="json"), "facts": "hello"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": semantic}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "secret", "model-1", client=client)
    with pytest.raises(ValidationError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()
    assert error.value.code == "AI_INVALID_OUTPUT"


@pytest.mark.asyncio
async def test_invalid_semantic_output_logs_only_safe_shape_diagnostics(caplog) -> None:
    hidden_value = "provider-response-must-not-be-logged"
    invalid_output = {"rules": [], "unexpected_secret": hidden_value}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(invalid_output)}}]},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StructuredJsonHttpAIAdapter("https://ai.example/extract", "fake-key", "model-1", client=client)
    with pytest.raises(ValidationError) as error:
        await adapter.extract(_minimal_context())
    await client.aclose()

    record = next(item for item in caplog.records if item.message == "ai_invalid_semantic_output")
    assert error.value.code == "AI_INVALID_OUTPUT"
    assert record.response_top_level_keys == ["rules", "unexpected_secret"]
    assert all("input" not in item for item in record.validation_errors)
    assert hidden_value not in caplog.text
    assert "fake-key" not in caplog.text


@pytest.mark.asyncio
async def test_truncated_prepared_document_is_rejected_before_provider_call() -> None:
    artifact = RawArtifact(
        id="artifact-truncated",
        source_id="source-1",
        requested_url="https://example.com/document",
        canonical_url="https://example.com/document",
        final_url="https://example.com/document",
        retrieved_at=datetime.now(UTC),
        checksum="a" * 64,
        raw_content_location="source-1/aa.bin",
        byte_size=4,
        created_at=datetime.now(UTC),
    )
    prepared = PreparedDocument(
        id="prepared-truncated",
        artifact_id=artifact.id,
        preparation_version="generic-2",
        content_fingerprint="b" * 64,
        document_type="document",
        structural_hints={"truncated_chunks": True},
        prepared_at=datetime.now(UTC),
    )
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=artifact.model_dump(mode="json")),
        get_prepared=AsyncMock(return_value=prepared.model_dump(mode="json")),
    )
    router = SimpleNamespace(provider_for=AsyncMock())
    service = ExtractionService(repository, SimpleNamespace(), router, SimpleNamespace(), SimpleNamespace())

    with pytest.raises(ValidationError) as error:
        await service.extract(artifact.id)

    assert error.value.code == "PREPARED_DOCUMENT_TRUNCATED"
    router.provider_for.assert_not_awaited()
