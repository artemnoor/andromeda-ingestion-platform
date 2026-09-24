"""Idempotent local demo seed."""

from __future__ import annotations

import asyncio
from pathlib import Path

from andromeda_ingestion.infrastructure.ai.profiles import DEFAULT_PROFILES
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.db.repositories import SqlAlchemyIngestionRepository
from andromeda_ingestion.infrastructure.db.session import create_engine, create_session_factory
from andromeda_ingestion.infrastructure.sources.registry import demo_source_definitions


async def seed(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
    async with factory() as session:
        repo = SqlAlchemyIngestionRepository(session)
        for source in demo_source_definitions(fixture_root):
            await repo.upsert_source(source.model_dump(mode="python"))
        for profile in DEFAULT_PROFILES:
            await repo.upsert_profile(profile.model_dump(mode="python"))
        await repo.commit()
    await engine.dispose()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
