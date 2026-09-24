"""SQLAlchemy metadata models for ingestion state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceDefinitionModel(Base):
    __tablename__ = "source_definitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    organization: Mapped[str] = mapped_column(String(255))
    source_category: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(2048))
    discovery_strategy: Mapped[str] = mapped_column(String(64))
    fetch_strategy: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trust_level: Mapped[str] = mapped_column(String(64))
    refresh_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    allowed_hosts_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DiscoveredItemModel(Base):
    __tablename__ = "discovered_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_definitions.id"), index=True)
    canonical_url: Mapped[str] = mapped_column(String(2048))
    document_kind: Mapped[str] = mapped_column(String(128), index=True)
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    discovery_method: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(64), default="DISCOVERED", index=True)
    __table_args__ = (UniqueConstraint("source_id", "canonical_url", name="uq_discovered_source_url"),)


class RawArtifactModel(Base):
    __tablename__ = "raw_artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_definitions.id"), index=True)
    discovered_item_id: Mapped[str | None] = mapped_column(ForeignKey("discovered_items.id"), nullable=True)
    requested_url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048), index=True)
    final_url: Mapped[str] = mapped_column(String(2048))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_content_location: Mapped[str] = mapped_column(String(2048))
    byte_size: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("source_id", "canonical_url", "checksum", name="uq_artifact_source_url_checksum"),
        Index("ix_artifact_source_current", "source_id", "canonical_url", "is_current"),
    )


class PreparedDocumentModel(Base):
    __tablename__ = "prepared_documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.id"), unique=True, index=True)
    preparation_version: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    document_type: Mapped[str] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sections_json: Mapped[list] = mapped_column(JSON, default=list)
    tables_json: Mapped[list] = mapped_column(JSON, default=list)
    links_json: Mapped[list] = mapped_column(JSON, default=list)
    chunks_json: Mapped[list] = mapped_column(JSON, default=list)
    structural_hints_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractionProfileModel(Base):
    __tablename__ = "extraction_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_code: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(64), default="ACTIVE", index=True)
    expected_document_types_json: Mapped[list] = mapped_column(JSON, default=list)
    expected_ontology_concepts_json: Mapped[list] = mapped_column(JSON, default=list)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    instructions: Mapped[str] = mapped_column(Text)
    validation_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_strategy: Mapped[str] = mapped_column(String(64), default="mock")
    prompt_version: Mapped[str] = mapped_column(String(64), default="prompt-1")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("profile_code", "version", name="uq_profile_code_version"),)


class ExtractionModel(Base):
    __tablename__ = "extractions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.id"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("extraction_profiles.id"), index=True)
    profile_version: Mapped[int] = mapped_column(Integer)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    output_fingerprint: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    token_usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="EXTRACTED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("artifact_id", "profile_id", "input_fingerprint", name="uq_extraction_input"),)


class ExtractionCandidateModel(Base):
    __tablename__ = "extraction_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    extraction_id: Mapped[str] = mapped_column(ForeignKey("extractions.id"), index=True)
    candidate_kind: Mapped[str] = mapped_column(String(64), index=True)
    natural_key: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    confidence_status: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="EXTRACTED", index=True)
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    core_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    core_observation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("extraction_id", "natural_key", name="uq_candidate_extraction_key"),)


class PipelineRunModel(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_definitions.id"), index=True)
    discovered_item_id: Mapped[str | None] = mapped_column(ForeignKey("discovered_items.id"), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("raw_artifacts.id"), nullable=True)
    extraction_id: Mapped[str | None] = mapped_column(ForeignKey("extractions.id"), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("extraction_profiles.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    transition_history_json: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobModel(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChangeCandidateModel(Base):
    __tablename__ = "change_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    extraction_id: Mapped[str] = mapped_column(ForeignKey("extractions.id"), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    target_key: Mapped[str] = mapped_column(String(512), index=True)
    before_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    reason: Mapped[str] = mapped_column(String(2000))
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(64), default="OPEN", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(128), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
