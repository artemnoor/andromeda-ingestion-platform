"""Immutable raw artifact storage port."""

from __future__ import annotations

from typing import Protocol


class ArtifactStoragePort(Protocol):
    async def put(self, storage_key: str, body: bytes) -> str: ...

    async def get(self, storage_key: str, expected_checksum: str | None = None) -> bytes: ...

    async def exists(self, storage_key: str) -> bool: ...
