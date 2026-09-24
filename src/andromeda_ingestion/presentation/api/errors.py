"""Stable public error envelope."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from andromeda_ingestion.domain.errors import DomainError
from andromeda_ingestion.infrastructure.observability.correlation import correlation_id_context
from andromeda_ingestion.infrastructure.observability.metrics import metrics
from andromeda_ingestion.presentation.api.schemas import ApiErrorResponse

logger = logging.getLogger("andromeda_ingestion.api")


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}, "trace_id": correlation_id_context.get()}}


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    metrics.increment("ingestion_api_errors_total", {"code": exc.code})
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, exc.details))


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    metrics.increment("ingestion_api_errors_total", {"code": "VALIDATION_FAILED"})
    details = {"fields": [{"path": list(error.get("loc", [])), "type": error.get("type")} for error in exc.errors()]}
    return JSONResponse(status_code=422, content=error_payload("VALIDATION_FAILED", "Request validation failed.", details))


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    metrics.increment("ingestion_api_errors_total", {"code": "INTERNAL_ERROR"})
    logger.exception("unhandled_request_error", exc_info=exc)
    return JSONResponse(
        status_code=500, content=error_payload("INTERNAL_ERROR", "An internal error occurred. Use the trace ID for support.")
    )


API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Stable ingestion domain error envelope."},
    403: {"model": ApiErrorResponse, "description": "The caller does not have the required role."},
    404: {"model": ApiErrorResponse, "description": "The requested entity was not found."},
    409: {"model": ApiErrorResponse, "description": "Concurrent update or idempotency conflict."},
    422: {"model": ApiErrorResponse, "description": "Request or candidate validation failed."},
    500: {"model": ApiErrorResponse, "description": "Unexpected error with a trace ID."},
    503: {"model": ApiErrorResponse, "description": "An external fetch/AI/Core dependency is unavailable."},
}
