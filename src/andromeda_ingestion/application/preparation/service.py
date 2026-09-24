"""Preparation application use case."""

from __future__ import annotations

from andromeda_ingestion.application.extraction.serialization import raw_artifact
from andromeda_ingestion.domain.ports.preparation import DocumentPreparationPort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.domain.ports.storage import ArtifactStoragePort


class PreparationService:
    def __init__(self, repository: IngestionRepositoryPort, storage: ArtifactStoragePort, preparer: DocumentPreparationPort) -> None:
        self.repository = repository
        self.storage = storage
        self.preparer = preparer

    async def prepare_artifact(self, artifact_id: str) -> dict:
        artifact = raw_artifact(await self.repository.get_artifact(artifact_id))
        existing = await self.repository.get_prepared(artifact_id)
        if existing and existing["content_fingerprint"]:
            return existing
        body = await self.storage.get(artifact.raw_content_location, artifact.checksum)
        prepared = await self.preparer.prepare(artifact, body)
        result = await self.repository.upsert_prepared(prepared.model_dump(mode="python"))
        await self.repository.commit()
        return result
