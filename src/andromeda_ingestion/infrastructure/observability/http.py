"""HTTP correlation, security headers and request duration middleware."""

from __future__ import annotations

import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .correlation import correlation_id_context, normalize_correlation_id
from .logging import log_event
from .metrics import metrics


class CorrelationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, enable_security_headers: bool = True) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.enable_security_headers = enable_security_headers

    async def dispatch(self, request: Request, call_next: object) -> Response:
        correlation_id = normalize_correlation_id(request.headers.get("X-Correlation-ID"))
        token = correlation_id_context.set(correlation_id)
        started = perf_counter()
        try:
            response = await call_next(request)  # type: ignore[operator]
            duration = perf_counter() - started
            response.headers["X-Correlation-ID"] = correlation_id
            if self.enable_security_headers:
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            metrics.observe(
                "ingestion_http_request_duration_seconds", duration, {"method": request.method, "status": str(response.status_code)}
            )
            log_event(
                logging.INFO,
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 3),
                correlation_id=correlation_id,
            )
            return response
        finally:
            correlation_id_context.reset(token)
