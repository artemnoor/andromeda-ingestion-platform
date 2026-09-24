"""Anti-corruption port for Andromeda Knowledge Core."""

from __future__ import annotations

from typing import Protocol

from ..contracts import CorePublishResult, ObservationCandidate, OntologySnapshot, RawArtifact, SourceDefinition, SourceRegistration


class KnowledgeCorePort(Protocol):
    async def get_ontology_snapshot(self) -> OntologySnapshot: ...

    async def register_source(self, source: SourceDefinition, artifact: RawArtifact) -> SourceRegistration: ...

    async def publish_observation(
        self,
        source_id: str,
        candidate: ObservationCandidate,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> CorePublishResult: ...
