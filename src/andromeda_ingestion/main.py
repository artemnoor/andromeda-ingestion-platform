"""Andromeda Ingestion Platform application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from andromeda_ingestion.application.container import AdapterContainer
from andromeda_ingestion.domain.errors import DomainError
from andromeda_ingestion.infrastructure.config import Settings, get_settings
from andromeda_ingestion.infrastructure.db.session import create_engine, create_session_factory
from andromeda_ingestion.infrastructure.observability.http import CorrelationMiddleware
from andromeda_ingestion.infrastructure.observability.logging import configure_logging
from andromeda_ingestion.presentation.api.errors import domain_error_handler, unhandled_error_handler, validation_error_handler
from andromeda_ingestion.presentation.api.routes import (
    artifacts,
    changes,
    discovery,
    extractions,
    health,
    jobs,
    pipelines,
    profiles,
    sources,
)


def create_app(settings: Settings | None = None, adapters: AdapterContainer | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    adapter_container = adapters or AdapterContainer.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(
        title="Andromeda Ingestion Platform",
        version="0.1.0",
        description=(
            "Evidence-first ingestion boundary for Andromeda Knowledge Core. "
            "The service discovers and preserves source evidence, prepares documents, "
            "extracts typed candidates through provider-neutral AI ports, validates them, "
            "and publishes observations through Core APIs."
        ),
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.adapters = adapter_container
    app.add_middleware(CorrelationMiddleware, enable_security_headers=settings.enable_security_headers)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"]
        )
    app.add_exception_handler(DomainError, cast(Any, domain_error_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_error_handler))
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(discovery.router)
    app.include_router(artifacts.router)
    app.include_router(extractions.router)
    app.include_router(pipelines.router)
    app.include_router(changes.router)
    app.include_router(profiles.router)
    app.include_router(jobs.router)
    return app


app = create_app()
