"""Validated environment configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Andromeda Ingestion Platform"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./andromeda_ingestion.db"
    artifact_storage_root: str = "./var/artifacts"
    fixture_root: str = "./fixtures"
    knowledge_core_url: str = "http://127.0.0.1:8001"
    knowledge_core_role: str = "EDITOR"
    knowledge_core_token: str | None = None
    api_docs_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=list)
    auto_seed: bool = False
    mock_ai_enabled: bool = True
    ai_provider: str = "mock"
    ai_endpoint: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "configured-structured-extractor"
    max_request_body_bytes: Annotated[int, Field(gt=0, le=10_000_000)] = 1_048_576
    max_artifact_bytes: Annotated[int, Field(gt=0, le=100_000_000)] = 30_000_000
    fetch_timeout_seconds: Annotated[float, Field(gt=0.1, le=120)] = 30.0
    fetch_total_budget_seconds: Annotated[float, Field(gt=0.1, le=600)] = 90.0
    fetch_max_redirects: Annotated[int, Field(ge=0, le=10)] = 5
    fetch_retries: Annotated[int, Field(ge=0, le=5)] = 2
    max_discovery_items: Annotated[int, Field(gt=0, le=10_000)] = 200
    max_prepared_chunks: Annotated[int, Field(gt=0, le=10_000)] = 500
    confidence_review_threshold: Annotated[float, Field(ge=0, le=1)] = 0.8
    job_max_attempts: Annotated[int, Field(ge=1, le=20)] = 3
    enable_security_headers: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
