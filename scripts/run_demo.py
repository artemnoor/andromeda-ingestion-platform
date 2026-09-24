"""Run the full deterministic BMSTU ingestion vertical slice without HTTP."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from andromeda_ingestion.application.container import AdapterContainer
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.db.session import create_engine, create_session_factory
from andromeda_ingestion.infrastructure.sources.registry import demo_source_definitions


async def demo(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    root = Path(__file__).resolve().parents[1]
    adapters = AdapterContainer.from_settings(settings)
    output: dict = {}
    async with factory() as session:
        services = adapters.services(session)
        sources = demo_source_definitions(root / "fixtures")
        await services.source.create_or_update(sources[0])
        await services.source.create_or_update(sources[1])
        items = await services.source.discover(sources[0].id)
        first = await services.pipeline.run(sources[0].id, items[0]["id"], profile_code="university_program", correlation_id="demo-program")
        output["program_pipeline"] = first
        regulation_items = await services.source.discover(sources[1].id)
        regulation = await services.pipeline.run(
            sources[1].id, regulation_items[0]["id"], profile_code="regulatory_document", correlation_id="demo-regulation"
        )
        output["regulation_pipeline"] = regulation
    await engine.dispose()
    return output


def main() -> None:
    print(json.dumps(asyncio.run(demo()), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
