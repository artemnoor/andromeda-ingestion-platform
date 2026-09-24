"""Fetch use case: bytes first, semantics later."""

from __future__ import annotations

from hashlib import sha256

from andromeda_ingestion.domain.common import FetchStrategy, utc_now
from andromeda_ingestion.domain.contracts import DiscoveredItem, RawArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.domain.ports.fetchers import ApiFetcherPort, BrowserFetcherPort, FileFetcherPort, HttpFetcherPort
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.domain.ports.storage import ArtifactStoragePort


class FetchService:
    def __init__(
        self,
        repository: IngestionRepositoryPort,
        storage: ArtifactStoragePort,
        http: HttpFetcherPort,
        browser: BrowserFetcherPort | None = None,
        file: FileFetcherPort | None = None,
        api: ApiFetcherPort | None = None,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.fetchers = {
            FetchStrategy.HTTP.value: http,
            FetchStrategy.BROWSER.value: browser or http,
            FetchStrategy.FILE.value: file or http,
            FetchStrategy.FIXTURE.value: file or http,
            FetchStrategy.API.value: api or http,
        }

    async def fetch_item(self, source_id: str, item_id: str) -> dict:
        source = SourceDefinition.model_validate(await self.repository.get_source(source_id))
        item = DiscoveredItem.model_validate(await self.repository.get_discovered_item(item_id))
        strategy = str(source.fetch_strategy)
        fetcher = self.fetchers.get(strategy)
        if fetcher is None:
            raise UpstreamError("FETCH_FAILED", "No fetch adapter registered", {"strategy": strategy})
        fetched = await fetcher.fetch(source, item)
        checksum = sha256(fetched.body).hexdigest()
        existing = await self.repository.find_artifact(source.id, item.canonical_url, checksum)
        if existing:
            return {"artifact": existing, "unchanged": True, "fetched": fetched}
        key = f"{source.id}/{checksum}.bin"
        await self.storage.put(key, fetched.body)
        current = await self.repository.get_current_artifact(source.id, item.canonical_url)
        artifact = RawArtifact(
            id=checksum[:32] + source.id[:8],
            source_id=source.id,
            discovered_item_id=item.id,
            requested_url=fetched.requested_url,
            canonical_url=item.canonical_url,
            final_url=fetched.final_url,
            retrieved_at=utc_now(),
            content_type=fetched.content_type,
            http_status=fetched.status_code,
            checksum=checksum,
            etag=fetched.etag,
            last_modified=fetched.last_modified,
            raw_content_location=key,
            byte_size=len(fetched.body),
            version=(int(current["version"]) + 1) if current else 1,
            previous_artifact_id=current["id"] if current else None,
            metadata={
                "document_kind": item.document_kind,
                "profile_code": item.metadata.get("profile_code", source.metadata.get("profile_code", "generic")),
                "access_mode": fetched.access_mode,
                "redirects": fetched.redirects,
            },
            created_at=utc_now(),
        )
        persisted = await self.repository.create_artifact(artifact.model_dump(mode="python"))
        await self.repository.commit()
        return {"artifact": persisted, "unchanged": False, "fetched": fetched}
