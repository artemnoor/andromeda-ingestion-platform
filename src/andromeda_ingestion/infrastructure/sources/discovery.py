"""Bounded source discovery adapters.

Discovery is deliberately limited to URL enumeration. It never interprets a
document as knowledge; that remains the responsibility of later pipeline
stages.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from urllib.parse import urldefrag, urljoin, urlparse
from uuid import uuid4
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from andromeda_ingestion.domain.common import DiscoveryStrategy, utc_now
from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError


class DiscoveryFetcher(Protocol):
    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact: ...


class StaticSourceDiscovery:
    """Return administrator-configured URLs without making network requests."""

    async def discover(self, source: SourceDefinition) -> list[DiscoveredItem]:
        configured = source.metadata.get("discovered_items")
        if not configured:
            configured = [{"url": source.base_url, "document_kind": source.metadata.get("document_kind", "document")}]
        return [
            _item(
                source,
                str(item.get("url", source.base_url)),
                str(item.get("document_kind", "document")),
                "STATIC_URL",
                Decimal(str(item.get("relevance_score", "1"))),
                dict(item.get("metadata", {})),
            )
            for item in configured[: _max_items(source)]
        ]


class ConfiguredSourceDiscovery:
    """Dispatch configured discovery through the safe HTTP fetcher."""

    def __init__(self, fetcher: DiscoveryFetcher, max_items: int = 200) -> None:
        self.fetcher = fetcher
        self.max_items = max_items

    async def discover(self, source: SourceDefinition) -> list[DiscoveredItem]:
        strategy = DiscoveryStrategy(str(source.discovery_strategy))
        if strategy == DiscoveryStrategy.STATIC_URL:
            return await StaticSourceDiscovery().discover(source)
        if strategy == DiscoveryStrategy.SITEMAP:
            return await self._sitemap(source)
        if strategy == DiscoveryStrategy.HTML_LINK_DISCOVERY:
            return await self._html_links(source)
        raise UpstreamError(
            "DISCOVERY_FAILED",
            "The configured discovery strategy is not implemented",
            {"strategy": strategy.value},
            status_code=422,
        )

    async def _sitemap(self, source: SourceDefinition) -> list[DiscoveredItem]:
        sitemap_url = str(source.metadata.get("sitemap_url", source.base_url))
        seed = _item(source, sitemap_url, "sitemap", "SITEMAP")
        artifact = await self.fetcher.fetch(source, seed)
        try:
            root = ElementTree.fromstring(artifact.body)
        except ElementTree.ParseError as exc:
            raise UpstreamError("DISCOVERY_FAILED", "Sitemap XML is invalid", {"url": sitemap_url}) from exc

        locations = [element.text.strip() for element in root.iter() if _xml_local_name(element.tag) == "loc" and element.text]
        if _xml_local_name(root.tag) == "sitemapindex":
            expanded: list[str] = []
            for location in locations[: self._limit(source)]:
                child = await self.fetcher.fetch(source, _item(source, location, "sitemap", "SITEMAP"))
                try:
                    child_root = ElementTree.fromstring(child.body)
                except ElementTree.ParseError as exc:
                    raise UpstreamError("DISCOVERY_FAILED", "Nested sitemap XML is invalid", {"url": location}) from exc
                expanded.extend(
                    element.text.strip()
                    for element in child_root.iter()
                    if _xml_local_name(element.tag) == "loc" and element.text
                )
            locations = expanded
        return self._urls(source, locations, "SITEMAP")

    async def _html_links(self, source: SourceDefinition) -> list[DiscoveredItem]:
        discovery_url = str(source.metadata.get("discovery_url", source.base_url))
        seed = _item(source, discovery_url, "html", "HTML_LINK_DISCOVERY")
        artifact = await self.fetcher.fetch(source, seed)
        soup = BeautifulSoup(artifact.body, "html.parser")
        urls = [urljoin(discovery_url, str(anchor["href"])) for anchor in soup.find_all("a", href=True)]
        return self._urls(source, urls, "HTML_LINK_DISCOVERY")

    def _urls(self, source: SourceDefinition, urls: list[str], method: str) -> list[DiscoveredItem]:
        result: list[DiscoveredItem] = []
        seen: set[str] = set()
        for raw_url in urls:
            url, _ = urldefrag(raw_url.strip())
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            host = parsed.hostname.lower().rstrip(".")
            if not _same_allowed_host(source, host) or url in seen:
                continue
            seen.add(url)
            result.append(_item(source, url, "document", method))
            if len(result) >= self._limit(source):
                break
        return result

    def _limit(self, source: SourceDefinition) -> int:
        configured = source.metadata.get("max_discovery_items", self.max_items)
        try:
            return max(1, min(self.max_items, int(configured)))
        except (TypeError, ValueError):
            return self.max_items


def _item(
    source: SourceDefinition,
    url: str,
    document_kind: str,
    method: str,
    relevance_score: Decimal = Decimal("1"),
    metadata: dict[str, object] | None = None,
) -> DiscoveredItem:
    return DiscoveredItem(
        id=uuid4().hex,
        source_id=source.id,
        canonical_url=url,
        document_kind=document_kind,
        relevance_score=relevance_score,
        discovered_at=utc_now(),
        discovery_method=method,
        metadata={"profile_code": source.metadata.get("profile_code", "generic"), **(metadata or {})},
    )


def _max_items(source: SourceDefinition) -> int:
    configured = source.metadata.get("max_discovery_items", 200)
    try:
        return max(1, int(configured))
    except (TypeError, ValueError):
        return 200


def _same_allowed_host(source: SourceDefinition, host: str) -> bool:
    configured = {value.lower().rstrip(".") for value in source.allowed_hosts}
    base_host = (urlparse(source.base_url).hostname or "").lower().rstrip(".")
    allowed = configured or ({base_host} if base_host else set())
    return host in allowed or any(host.endswith(f".{item}") for item in allowed)


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
