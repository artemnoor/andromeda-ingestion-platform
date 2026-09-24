"""Byte fetcher ports with no knowledge semantics."""

from __future__ import annotations

from typing import Protocol

from ..contracts import DiscoveredItem, FetchedArtifact, SourceDefinition


class HttpFetcherPort(Protocol):
    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact: ...


class BrowserFetcherPort(Protocol):
    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact: ...


class FileFetcherPort(Protocol):
    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact: ...


class ApiFetcherPort(Protocol):
    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact: ...
