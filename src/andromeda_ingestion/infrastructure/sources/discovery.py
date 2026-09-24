"""Generic discovery adapters; they discover URLs, not semantic truth."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import DiscoveredItem, SourceDefinition


class StaticSourceDiscovery:
    async def discover(self, source: SourceDefinition) -> list[DiscoveredItem]:
        configured = source.metadata.get("discovered_items")
        if not configured:
            configured = [{"url": source.base_url, "document_kind": source.metadata.get("document_kind", "document")}]
        return [
            DiscoveredItem(
                id=uuid4().hex,
                source_id=source.id,
                canonical_url=str(item.get("url", source.base_url)),
                document_kind=str(item.get("document_kind", "document")),
                relevance_score=Decimal(str(item.get("relevance_score", "1"))),
                discovered_at=utc_now(),
                discovery_method="STATIC_URL",
                metadata={"profile_code": source.metadata.get("profile_code", "generic"), **dict(item.get("metadata", {}))},
            )
            for item in configured
        ]
