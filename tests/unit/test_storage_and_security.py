import pytest

from andromeda_ingestion.domain.common import DiscoveryStrategy, FetchStrategy, SourceCategory, SourceType, TrustLevel
from andromeda_ingestion.domain.contracts import SourceDefinition
from andromeda_ingestion.domain.errors import StorageError, UpstreamError
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.fetchers.http import SafeHttpFetcher
from andromeda_ingestion.infrastructure.storage.filesystem import FileSystemArtifactStorage


@pytest.mark.asyncio
async def test_filesystem_storage_rejects_path_escape(tmp_path):
    storage = FileSystemArtifactStorage(tmp_path / "artifacts")
    with pytest.raises(StorageError):
        await storage.put("../escape", b"secret")


def test_http_fetcher_rejects_non_allowlisted_host():
    fetcher = SafeHttpFetcher(Settings(app_env="test"))
    source = SourceDefinition(
        id="s",
        stable_key="s",
        organization="x",
        source_category=SourceCategory.UNIVERSITY,
        source_type=SourceType.WEB_PAGE,
        base_url="https://example.com",
        discovery_strategy=DiscoveryStrategy.STATIC_URL,
        fetch_strategy=FetchStrategy.HTTP,
        trust_level=TrustLevel.UNVERIFIED,
        allowed_hosts=["example.com"],
    )
    with pytest.raises(UpstreamError) as error:
        fetcher._validate_url("https://evil.example/", source)
    assert error.value.code == "FETCH_SSRF_REJECTED"
