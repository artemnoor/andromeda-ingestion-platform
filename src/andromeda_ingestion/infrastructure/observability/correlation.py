"""Correlation ID context."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

correlation_id_context: ContextVar[str] = ContextVar("ingestion_correlation_id", default="-")


def normalize_correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())
