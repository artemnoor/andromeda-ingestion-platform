"""Source discovery port."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DiscoveredItem, SourceDefinition


class SourceDiscoveryPort(Protocol):
    async def discover(self, source: SourceDefinition) -> list[DiscoveredItem]: ...
