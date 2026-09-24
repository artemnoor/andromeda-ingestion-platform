"""Content preparation port."""

from __future__ import annotations

from typing import Protocol

from ..contracts import PreparedDocument, RawArtifact


class DocumentPreparationPort(Protocol):
    async def prepare(self, artifact: RawArtifact, body: bytes) -> PreparedDocument: ...
