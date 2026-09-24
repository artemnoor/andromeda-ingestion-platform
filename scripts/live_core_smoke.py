"""Opt-in smoke test against a running Knowledge Core HTTP API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.sources.registry import demo_source_definitions
from andromeda_ingestion.main import create_app


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(
        app_env="production",
        mock_ai_enabled=False,
        ai_provider="mock",
        database_url="sqlite+aiosqlite:///./var/live-ingestion.db",
        artifact_storage_root="./var/live-ingestion-artifacts",
        fixture_root=str(root / "fixtures"),
        knowledge_core_url="http://127.0.0.1:8001",
    )
    source = demo_source_definitions(root / "fixtures")[1]
    with TestClient(create_app(settings)) as client:
        source_payload = {
            "id": source.id,
            "stable_key": source.stable_key,
            "organization": source.organization,
            "source_category": source.source_category,
            "source_type": source.source_type,
            "base_url": source.base_url,
            "discovery_strategy": source.discovery_strategy,
            "fetch_strategy": source.fetch_strategy,
            "content_type": source.content_type,
            "trust_level": source.trust_level,
            "allowed_hosts": source.allowed_hosts,
            "metadata": source.metadata,
        }
        headers = {"X-Role": "EDITOR", "X-Correlation-ID": "live-core-smoke"}
        assert client.post("/api/v1/sources", json=source_payload, headers=headers).status_code == 201
        item = client.post(f"/api/v1/sources/{source.id}/discover", headers=headers).json()[0]
        response = client.post(
            "/api/v1/pipelines/run",
            json={"source_id": source.id, "item_id": item["id"], "profile_code": "regulatory_document"},
            headers=headers,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
