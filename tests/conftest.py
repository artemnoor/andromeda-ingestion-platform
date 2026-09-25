from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from andromeda_ingestion.application.container import AdapterContainer
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.db.models import Base
from andromeda_ingestion.infrastructure.db.session import create_engine
from andromeda_ingestion.main import create_app


@pytest.fixture
def app_client(tmp_path: Path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'ingestion.db').as_posix()}"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        artifact_storage_root=str(tmp_path / "artifacts"),
        mock_ai_enabled=True,
        ai_provider="mock",
        ai_endpoint=None,
        ai_api_key=None,
        auto_seed=False,
    )
    engine = create_engine(settings)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    app = create_app(settings, AdapterContainer.from_settings(settings))
    with TestClient(app) as client:
        yield client, settings


@pytest.fixture(autouse=True)
def isolate_live_ai_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ordinary tests independent from a developer's live ``.env``.

    A Settings instance created directly by a unit test would otherwise load
    the local Polza key and provider defaults from ``.env``. The explicit
    empty values prevent accidental live calls even in tests that do not use
    ``app_client``. Live evaluation belongs in the opt-in script only.
    """

    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_ENDPOINT", "")
    monkeypatch.setenv("AI_API_KEY", "")
    monkeypatch.setenv("MOCK_AI_ENABLED", "true")


@pytest.fixture
def fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"
