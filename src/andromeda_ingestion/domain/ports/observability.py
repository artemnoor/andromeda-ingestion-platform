"""Small observability seam used by application services."""

from __future__ import annotations

from typing import Protocol


class MetricsPort(Protocol):
    def increment(self, name: str, labels: dict[str, str] | None = None, value: float = 1) -> None: ...

    def observe(self, name: str, duration_seconds: float, labels: dict[str, str] | None = None) -> None: ...
