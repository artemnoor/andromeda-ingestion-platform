"""Strict serializable domain contracts crossing ingestion seams."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import (
    ChangeKind,
    ConfidenceStatus,
    DiscoveryStrategy,
    FetchStrategy,
    JobState,
    PipelineState,
    SourceCategory,
    SourceType,
    TrustLevel,
    validate_interval,
)

SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SourceDefinition(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    stable_key: str = Field(min_length=1, max_length=255)
    organization: str = Field(min_length=1, max_length=255)
    source_category: SourceCategory
    source_type: SourceType
    base_url: str
    discovery_strategy: DiscoveryStrategy
    fetch_strategy: FetchStrategy
    content_type: str | None = None
    trust_level: TrustLevel = TrustLevel.UNVERIFIED
    refresh_policy: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DiscoveredItem(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    source_id: str
    canonical_url: str
    document_kind: str = Field(min_length=1, max_length=128)
    relevance_score: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    discovered_at: datetime
    discovery_method: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "DISCOVERED"


class EvidenceLocator(StrictModel):
    artifact_id: str
    source_url: str
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=512)
    paragraph: str | None = Field(default=None, max_length=512)
    table: str | None = Field(default=None, max_length=512)
    row: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    selector: str | None = Field(default=None, max_length=2048)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    fragment_id: str | None = Field(default=None, max_length=255)
    quote: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_location(self) -> EvidenceLocator:
        has_range = self.text_start is not None or self.text_end is not None
        if self.text_start is not None and self.text_end is not None and self.text_end < self.text_start:
            raise ValueError("text_end must be greater than or equal to text_start")
        if not any((self.page, self.section, self.paragraph, self.table, self.row, self.selector, self.fragment_id, has_range)):
            raise ValueError("evidence locator must contain a page, section, selector, fragment or text range")
        return self


class EvidenceRef(StrictModel):
    artifact_id: str
    locator: EvidenceLocator
    excerpt_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    quote: str | None = Field(default=None, max_length=4000)
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)


class FetchedArtifact(StrictModel):
    schema_version: str = SCHEMA_VERSION
    requested_url: str
    final_url: str
    status_code: int | None = Field(default=None, ge=100, le=599)
    content_type: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes = Field(min_length=1)
    etag: str | None = None
    last_modified: str | None = None
    redirects: list[str] = Field(default_factory=list)
    elapsed_ms: float = Field(default=0, ge=0)
    access_mode: str = "http"
    truncated: bool = False


class RawArtifact(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    source_id: str
    discovered_item_id: str | None = None
    requested_url: str
    canonical_url: str
    final_url: str
    retrieved_at: datetime
    content_type: str | None = None
    http_status: int | None = None
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    etag: str | None = None
    last_modified: str | None = None
    raw_content_location: str
    byte_size: int = Field(ge=1)
    version: int = Field(default=1, ge=1)
    previous_artifact_id: str | None = None
    is_current: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ContentChunk(StrictModel):
    id: str
    artifact_id: str
    text: str = Field(min_length=1, max_length=100_000)
    ordinal: int = Field(ge=0)
    locator: EvidenceLocator
    kind: str = "text"
    structural_hints: dict[str, Any] = Field(default_factory=dict)


class PreparedDocument(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    artifact_id: str
    preparation_version: str
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_type: str
    title: str | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    content_chunks: list[ContentChunk] = Field(default_factory=list)
    structural_hints: dict[str, Any] = Field(default_factory=dict)
    prepared_at: datetime


class OntologySnapshot(StrictModel):
    schema_version: str = SCHEMA_VERSION
    ontology_version_id: str | None = None
    version_code: str | None = None
    object_types: list[dict[str, Any]] = Field(default_factory=list)
    properties: list[dict[str, Any]] = Field(default_factory=list)
    relation_types: list[dict[str, Any]] = Field(default_factory=list)
    rule_dsl_schema: dict[str, Any] = Field(default_factory=dict)


class ExtractionProfile(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    profile_code: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: str = "ACTIVE"
    expected_document_types: list[str] = Field(default_factory=list)
    expected_ontology_concepts: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any]
    instructions: str = Field(min_length=1, max_length=20_000)
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    ai_strategy: str = "mock"
    prompt_version: str = "prompt-1"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ExtractionContext(StrictModel):
    schema_version: str = SCHEMA_VERSION
    artifact: RawArtifact
    prepared_document: PreparedDocument
    profile: ExtractionProfile
    ontology: OntologySnapshot = Field(default_factory=OntologySnapshot)
    trusted_instructions: str
    untrusted_document_data: list[ContentChunk]


class CandidateEntity(StrictModel):
    stable_key: str = Field(min_length=1, max_length=255)
    object_type_code: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=512)
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class CandidateFact(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    subject: CandidateEntity
    property_code: str = Field(min_length=1, max_length=255)
    value: Any
    value_type: str = Field(min_length=1, max_length=32)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: Decimal = Field(ge=0, le=1)
    confidence_status: ConfidenceStatus = ConfidenceStatus.UNKNOWN
    evidence: list[EvidenceRef] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_time(self) -> CandidateFact:
        validate_interval(self.valid_from, self.valid_to)
        return self


class CandidateRelation(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    subject: CandidateEntity
    relation_type_code: str = Field(min_length=1, max_length=255)
    target: CandidateEntity
    properties: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: Decimal = Field(ge=0, le=1)
    confidence_status: ConfidenceStatus = ConfidenceStatus.UNKNOWN
    evidence: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time(self) -> CandidateRelation:
        validate_interval(self.valid_from, self.valid_to)
        return self


class CandidateRule(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    logical_key: str = Field(min_length=1, max_length=255)
    rule_type: str = "generic"
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any]
    effects: list[dict[str, Any]] = Field(min_length=1)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = 0
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: Decimal = Field(ge=0, le=1)
    confidence_status: ConfidenceStatus = ConfidenceStatus.UNKNOWN
    evidence: list[EvidenceRef] = Field(min_length=1)
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_time(self) -> CandidateRule:
        validate_interval(self.valid_from, self.valid_to)
        return self


class UnknownConceptCandidate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    suggested_object_type: str | None = None
    suggested_property: str | None = None
    suggested_relation: str | None = None
    confidence: Decimal = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ChangeCandidate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    kind: ChangeKind
    target_key: str = Field(min_length=1, max_length=512)
    before_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    after_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    before_payload: dict[str, Any] | None = None
    after_payload: dict[str, Any] | None = None
    confidence: Decimal = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ExtractionResult(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    artifact_id: str
    profile_id: str
    profile_version: int
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_type: str
    provider: str
    model: str
    prompt_version: str
    entities: list[CandidateEntity] = Field(default_factory=list)
    facts: list[CandidateFact] = Field(default_factory=list)
    relations: list[CandidateRelation] = Field(default_factory=list)
    rules: list[CandidateRule] = Field(default_factory=list)
    unknown_concepts: list[UnknownConceptCandidate] = Field(default_factory=list)
    changes: list[ChangeCandidate] = Field(default_factory=list)
    confidence_summary: dict[str, Decimal] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw_provider_metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = Field(default=0, ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    status: str = "EXTRACTED"
    created_at: datetime


class ValidationIssue(StrictModel):
    code: str
    message: str
    path: str = ""
    severity: Literal["error", "warning"] = "error"


class ValidationReport(StrictModel):
    schema_version: str = SCHEMA_VERSION
    extraction_id: str
    status: Literal["VALIDATED", "NEEDS_REVIEW", "REJECTED"]
    issues: list[ValidationIssue] = Field(default_factory=list)
    validated_candidate_ids: list[str] = Field(default_factory=list)
    review_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    completed_at: datetime


CandidateKind = Literal["fact", "relation", "rule", "unknown_concept", "change"]


class ObservationCandidate(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    candidate_kind: CandidateKind
    subject_candidate: CandidateEntity
    property_candidate: str | None = None
    relation_candidate: dict[str, Any] | None = None
    value: Any = None
    value_type: str | None = None
    evidence: list[EvidenceRef] = Field(min_length=1)
    confidence: Decimal = Field(ge=0, le=1)
    confidence_status: ConfidenceStatus = ConfidenceStatus.UNKNOWN
    ontology_version_id: str | None = None
    source_document_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PipelineRun(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    source_id: str
    discovered_item_id: str | None = None
    artifact_id: str | None = None
    extraction_id: str | None = None
    profile_id: str | None = None
    state: PipelineState
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    idempotency_key: str
    correlation_id: str
    error_code: str | None = None
    error_message: str | None = None
    transition_history: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    row_version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class Job(StrictModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    kind: str
    state: JobState
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    next_retry_at: datetime | None = None
    idempotency_key: str
    correlation_id: str
    error_code: str | None = None
    error_message: str | None = None
    row_version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class CorePublishResult(StrictModel):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    core_source_id: str | None = None
    core_observation_id: str | None = None
    core_rule_id: str | None = None
    core_provenance_id: str | None = None
    status: str
    review_id: str | None = None
    proposal_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SourceRegistration(StrictModel):
    """Core identifiers for source and immutable document metadata."""

    schema_version: str = SCHEMA_VERSION
    source_id: str
    source_document_id: str
