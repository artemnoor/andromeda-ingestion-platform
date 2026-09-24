"""Provider-neutral AI and entity resolution ports."""

from __future__ import annotations

from typing import Protocol

from ..contracts import (
    CandidateEntity,
    ExtractionContext,
    ExtractionProfile,
    ExtractionResult,
    OntologySnapshot,
)


class DocumentUnderstandingPort(Protocol):
    async def extract(self, context: ExtractionContext) -> ExtractionResult: ...


class StructuredExtractionPort(DocumentUnderstandingPort, Protocol):
    pass


class EntityExtractionPort(Protocol):
    async def extract_entities(self, context: ExtractionContext) -> list[CandidateEntity]: ...


class RelationExtractionPort(Protocol):
    async def extract_relations(self, context: ExtractionContext) -> list[dict[str, object]]: ...


class RuleExtractionPort(Protocol):
    async def extract_rules(self, context: ExtractionContext) -> list[dict[str, object]]: ...


class ChangeDetectionPort(Protocol):
    async def detect_changes(self, previous: ExtractionResult | None, current: ExtractionResult) -> list[dict[str, object]]: ...


class DocumentClassificationPort(Protocol):
    async def classify(self, context: ExtractionContext) -> str: ...


class EntityResolutionPort(Protocol):
    async def resolve(self, entity: CandidateEntity, ontology: OntologySnapshot) -> dict[str, object]: ...


class AIProviderRouterPort(Protocol):
    async def provider_for(self, profile: ExtractionProfile) -> DocumentUnderstandingPort: ...
