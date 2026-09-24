"""Small registry facade used by application services and seed commands."""

from __future__ import annotations

from collections.abc import Iterable

from andromeda_ingestion.domain.contracts import SourceDefinition
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort


class SourceRegistry:
    def __init__(self, repository: IngestionRepositoryPort) -> None:
        self.repository = repository

    async def register(self, source: SourceDefinition) -> dict[str, object]:
        return await self.repository.upsert_source(source.model_dump(mode="python"))

    async def register_many(self, sources: Iterable[SourceDefinition]) -> list[dict[str, object]]:
        result = [await self.register(source) for source in sources]
        await self.repository.commit()
        return result
