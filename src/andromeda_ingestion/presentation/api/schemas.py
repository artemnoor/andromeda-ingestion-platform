"""Human-oriented FastAPI request contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from andromeda_ingestion.domain.common import DiscoveryStrategy, FetchStrategy, SourceCategory, SourceType, TrustLevel


class StrictAPIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ApiErrorDetails(BaseModel):
    code: str = Field(examples=["AI_INVALID_OUTPUT"])
    message: str = Field(examples=["The provider response did not satisfy the extraction contract."])
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(examples=["b8a2fb35-2a2e-4d7d-88c3-9e62e9bf3b0a"])


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "AI_INVALID_OUTPUT",
                        "message": "The provider response did not satisfy the extraction contract.",
                        "details": {},
                        "trace_id": "b8a2fb35-2a2e-4d7d-88c3-9e62e9bf3b0a",
                    }
                }
            ]
        }
    )

    error: ApiErrorDetails


class SourceCreateRequest(StrictAPIModel):
    id: str | None = Field(default=None, examples=["src-bmstu-programs"])
    stable_key: str = Field(min_length=1, max_length=255, examples=["bmstu.programs"])
    organization: str = Field(min_length=1, max_length=255, examples=["BMSTU"])
    source_category: SourceCategory = SourceCategory.UNIVERSITY
    source_type: SourceType = SourceType.WEB_PAGE
    base_url: HttpUrl | str
    discovery_strategy: DiscoveryStrategy = DiscoveryStrategy.STATIC_URL
    fetch_strategy: FetchStrategy = FetchStrategy.HTTP
    content_type: str | None = None
    trust_level: TrustLevel = TrustLevel.UNVERIFIED
    refresh_policy: dict[str, Any] = Field(default_factory=dict)
    allowed_hosts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryRunRequest(StrictAPIModel):
    source_id: str


class FetchRequest(StrictAPIModel):
    item_id: str


class ExtractionRequest(StrictAPIModel):
    profile_code: str | None = None


class PipelineRunRequest(StrictAPIModel):
    source_id: str
    item_id: str
    profile_code: str | None = None
    idempotency_key: str | None = None


class ProfileCreateRequest(StrictAPIModel):
    profile_code: str = Field(min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    expected_document_types: list[str] = Field(default_factory=list)
    expected_ontology_concepts: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    instructions: str = Field(min_length=1, max_length=20_000)
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    ai_strategy: str = "mock"
    prompt_version: str = "prompt-1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryJobRequest(StrictAPIModel):
    reason: str = Field(min_length=1, max_length=2000)


class JobCreateRequest(StrictAPIModel):
    kind: str = Field(default="PIPELINE", examples=["PIPELINE"])
    payload: dict[str, Any] = Field(
        default_factory=dict, examples=[{"source_id": "src-bmstu-programs", "item_id": "item-id", "profile_code": "university_program"}]
    )
    idempotency_key: str = Field(min_length=1, max_length=255)
