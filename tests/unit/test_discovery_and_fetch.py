from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from andromeda_ingestion.domain.common import DiscoveryStrategy, FetchStrategy, SourceCategory, SourceType, TrustLevel
from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.fetchers.http import SafeHttpFetcher
from andromeda_ingestion.infrastructure.sources.discovery import ConfiguredSourceDiscovery


def _source(*, strategy: DiscoveryStrategy = DiscoveryStrategy.STATIC_URL, base_url: str = "https://example.com/root") -> SourceDefinition:
    return SourceDefinition(
        id="source-1",
        stable_key="example.source",
        organization="Example",
        source_category=SourceCategory.OTHER_OFFICIAL_SOURCE,
        source_type=SourceType.WEB_PAGE,
        base_url=base_url,
        discovery_strategy=strategy,
        fetch_strategy=FetchStrategy.HTTP,
        trust_level=TrustLevel.UNVERIFIED,
        allowed_hosts=["example.com"],
        metadata={"max_discovery_items": 2},
    )


class FakeDiscoveryFetcher:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies

    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact:
        return FetchedArtifact(
            requested_url=item.canonical_url,
            final_url=item.canonical_url,
            status_code=200,
            content_type="application/xml" if "sitemap" in item.document_kind else "text/html",
            body=self.bodies[item.canonical_url],
        )


@pytest.mark.asyncio
async def test_sitemap_discovery_is_bounded_and_same_origin() -> None:
    source = _source(strategy=DiscoveryStrategy.SITEMAP, base_url="https://example.com/sitemap.xml")
    fetcher = FakeDiscoveryFetcher(
        {
            source.base_url: b"<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://evil.example/b</loc></url><url><loc>https://example.com/c</loc></url></urlset>"
        }
    )

    result = await ConfiguredSourceDiscovery(fetcher, max_items=10).discover(source)

    assert [item.canonical_url for item in result] == ["https://example.com/a", "https://example.com/c"]
    assert all(item.discovery_method == "SITEMAP" for item in result)


@pytest.mark.asyncio
async def test_html_link_discovery_deduplicates_fragments_and_external_hosts() -> None:
    source = _source(strategy=DiscoveryStrategy.HTML_LINK_DISCOVERY)
    fetcher = FakeDiscoveryFetcher(
        {
            source.base_url: b'<a href="/a#one">A</a><a href="https://example.com/a#two">A2</a><a href="https://evil.example/b">B</a>'
        }
    )

    result = await ConfiguredSourceDiscovery(fetcher, max_items=10).discover(source)

    assert [item.canonical_url for item in result] == ["https://example.com/a"]


@pytest.mark.asyncio
async def test_safe_fetcher_rejects_private_dns_and_does_not_fetch() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok", request=request))
    client = httpx.AsyncClient(transport=transport)
    fetcher = SafeHttpFetcher(Settings(app_env="test"), client=client, resolve_host=lambda _host: ["10.0.0.1"])
    source = _source(base_url="https://example.com/document")
    item = DiscoveredItem(
        id="item-1",
        source_id=source.id,
        canonical_url=source.base_url,
        document_kind="document",
        discovered_at=datetime.now(UTC),
        discovery_method="STATIC_URL",
    )

    with pytest.raises(UpstreamError, match="private") as error:
        await fetcher.fetch(source, item)
    assert error.value.code == "FETCH_SSRF_REJECTED"
    await client.aclose()


@pytest.mark.asyncio
async def test_safe_fetcher_maps_4xx_and_retries_5xx() -> None:
    statuses = [404, 500, 500]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(statuses.pop(0), content=b"error", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(app_env="test", fetch_retries=1)
    fetcher = SafeHttpFetcher(settings, client=client, resolve_host=lambda _host: ["93.184.216.34"])
    source = _source()
    item = DiscoveredItem(
        id="item-1",
        source_id=source.id,
        canonical_url=source.base_url,
        document_kind="document",
        discovered_at=datetime.now(UTC),
        discovery_method="STATIC_URL",
    )

    with pytest.raises(UpstreamError) as client_error:
        await fetcher.fetch(source, item)
    assert client_error.value.code == "FETCH_CLIENT_ERROR"

    item = item.model_copy(update={"canonical_url": "https://example.com/retry"})
    with pytest.raises(UpstreamError) as server_error:
        await fetcher.fetch(source, item)
    assert server_error.value.code == "FETCH_SERVER_ERROR"
    await client.aclose()
