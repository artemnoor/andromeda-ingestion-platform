"""Structured JSON logging without raw evidence or secrets."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_KEY_MARKERS = (
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "prompt",
    "body",
    "raw_content",
    "raw_payload",
    "credential",
)
_SAFE_METRIC_KEYS = {"api_key_present", "token_usage", "prompt_tokens", "completion_tokens", "total_tokens"}
_STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _safe(value: Any, key: str | None = None) -> Any:
    normalized_key = key.casefold() if key else ""
    if normalized_key and normalized_key not in _SAFE_METRIC_KEYS and any(
        marker in normalized_key for marker in _SENSITIVE_KEY_MARKERS
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 512:
        return f"{value[:512]}…"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", {})
        if isinstance(context, dict):
            safe_context = _safe(context)
            if isinstance(safe_context, dict):
                payload.update(safe_context)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_FIELDS and key not in {"context", "message"} and not key.startswith("_")
        }
        safe_extras = _safe(extras)
        if isinstance(safe_extras, dict):
            payload.update(safe_extras)
        if record.exc_info:
            exception_type = record.exc_info[0].__name__ if record.exc_info[0] is not None else "Exception"
            payload["exception"] = {"type": exception_type, "message": str(record.exc_info[1])}
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def log_event(level: int, message: str, **context: Any) -> None:
    logging.getLogger("andromeda_ingestion").log(level, message, extra={"context": _safe(context)})
