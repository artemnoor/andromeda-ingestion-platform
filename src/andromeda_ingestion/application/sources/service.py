"""Source registry and discovery application use cases."""

from __future__ import annotations

from andromeda_ingestion.domain.contracts import SourceDefinition
from andromeda_ingestion.domain.ports.discovery import SourceDiscoveryPort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort


class SourceService:
    def __init__(self, repository: IngestionRepositoryPort, discovery: SourceDiscoveryPort) -> None:
        self.repository = repository
        self.discovery = discovery

    async def create_or_update(self, source: SourceDefinition) -> dict:
        result = await self.repository.upsert_source(source.model_dump(mode="python"))
        await self.repository.commit()
        return result

    async def list_sources(self, enabled: bool | None = None) -> list[dict[str, object]]:
        return await self.repository.list_sources(enabled)

    async def discover(self, source_id: str) -> list[dict]:
        source = SourceDefinition.model_validate(await self.repository.get_source(source_id))
        items = await self.discovery.discover(source)
        result = [await self.repository.upsert_discovered_item(item.model_dump(mode="python")) for item in items]
        await self.repository.commit()
        return result

    async def list_discovered(self, source_id: str) -> list[dict]:
        return await self.repository.list_discovered_items(source_id)
