"""Allowlisted local file adapter for controlled imports."""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path

from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError


class LocalFileFetcher:
    def __init__(self, root: str | Path, max_bytes: int) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes

    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact:
        raw = source.metadata.get("local_path")
        if not isinstance(raw, str):
            raise UpstreamError("FETCH_FAILED", "Local file source has no local_path", {"source_id": source.id})
        path = Path(raw).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Local file path escapes the configured import root", {"path": str(path)}) from exc
        if not path.is_file():
            raise UpstreamError("FETCH_FAILED", "Local import file does not exist", {"path": str(path)})
        body = path.read_bytes()
        if not body or len(body) > self.max_bytes:
            raise UpstreamError("FETCH_BODY_TOO_LARGE", "Local import is empty or exceeds configured artifact limit", {"path": str(path)})
        return FetchedArtifact(
            requested_url=item.canonical_url,
            final_url=item.canonical_url,
            status_code=200,
            content_type=mimetypes.guess_type(path.name)[0],
            body=body,
            elapsed_ms=time.perf_counter() * 0,
        )
