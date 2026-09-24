"""Deterministic local fixture fetcher for development and CI."""

from __future__ import annotations

import time
from pathlib import Path

from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError


class FixtureFileFetcher:
    def __init__(self, max_bytes: int, root: str | Path = "./fixtures") -> None:
        self.max_bytes = max_bytes
        self.root = Path(root).resolve()

    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact:
        started = time.perf_counter()
        raw_path = source.metadata.get("fixture_path")
        if not isinstance(raw_path, str):
            raise UpstreamError("FETCH_FAILED", "Fixture source has no fixture_path", {"source_id": source.id})
        path = Path(raw_path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Fixture path escapes the configured fixture root", {"path": str(path)}) from exc
        if not path.is_file():
            raise UpstreamError("FETCH_FAILED", "Fixture file does not exist", {"path": str(path)})
        body = path.read_bytes()
        if len(body) > self.max_bytes:
            raise UpstreamError("FETCH_BODY_TOO_LARGE", "Fixture exceeds configured artifact limit", {"limit": self.max_bytes})
        if not body:
            raise UpstreamError("FETCH_FAILED", "Fixture is empty", {"path": str(path)})
        content_type = source.content_type or ("application/pdf" if path.suffix.lower() == ".pdf" else "text/html")
        return FetchedArtifact(
            requested_url=item.canonical_url,
            final_url=item.canonical_url,
            status_code=200,
            content_type=content_type,
            headers={"content-type": content_type},
            body=body,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            access_mode="fixture",
        )
