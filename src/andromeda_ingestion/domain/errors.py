"""Stable domain and boundary errors."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code


class NotFoundError(DomainError):
    def __init__(self, entity: str, identifier: str) -> None:
        super().__init__("NOT_FOUND", f"{entity} was not found.", {"entity": entity, "id": identifier}, 404)


class ValidationError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details, 422)


class ConflictError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details, 409)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "The caller does not have the required role.") -> None:
        super().__init__("FORBIDDEN", message, status_code=403)


class UpstreamError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status_code: int = 503) -> None:
        super().__init__(code, message, details, status_code)


class StorageError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details, 500)
