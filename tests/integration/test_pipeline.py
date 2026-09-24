from __future__ import annotations

from pathlib import Path

from andromeda_ingestion.infrastructure.sources.registry import demo_source_definitions


def _source_payload(source, fixture_path: str | None = None) -> dict:
    return {
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
        "metadata": {**source.metadata, **({"fixture_path": fixture_path} if fixture_path else {})},
    }


def test_bmstu_program_end_to_end_and_idempotent_fetch(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[0]
    created = client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"})
    assert created.status_code == 201, created.text
    discovered = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"})
    assert discovered.status_code == 200, discovered.text
    item_id = discovered.json()[0]["id"]
    pipeline = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )
    assert pipeline.status_code == 200, pipeline.text
    body = pipeline.json()
    assert body["state"] == "PUBLISHED"
    assert body["artifact_id"]
    extraction = client.get(f"/api/v1/extractions/{body['extraction_id']}")
    assert extraction.status_code == 200, extraction.text
    assert any(item["candidate_kind"] == "fact" for item in extraction.json()["candidates"])
    provider = client.app.state.adapters.ai_router.provider
    assert provider.calls == 1
    fetched_again = client.post(f"/api/v1/sources/{source.id}/fetch", json={"item_id": item_id}, headers={"X-Role": "EDITOR"})
    assert fetched_again.status_code == 200
    assert fetched_again.json()["unchanged"] is True
    repeated_pipeline = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "university_program"},
        headers={"X-Role": "EDITOR"},
    )
    assert repeated_pipeline.json()["state"] == "PUBLISHED"
    assert provider.calls == 1


def test_regulation_unknown_concept_goes_to_review(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[3]
    assert client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"}).status_code == 201
    discovered = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()
    pipeline = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": discovered[0]["id"], "profile_code": "regulatory_document"},
        headers={"X-Role": "EDITOR"},
    )
    assert pipeline.json()["state"] == "NEEDS_REVIEW"
    candidates = client.get(f"/api/v1/extractions/{pipeline.json()['extraction_id']}/candidates").json()
    assert any(item["candidate_kind"] == "unknown_concept" and item["status"] == "NEEDS_REVIEW" for item in candidates)


def test_changed_regulation_creates_change_candidate(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[1]
    assert client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"}).status_code == 201
    item_id = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()[0]["id"]
    client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "regulatory_document", "idempotency_key": "regulation-v1"},
        headers={"X-Role": "EDITOR"},
    ).json()
    update = _source_payload(source, str(fixture_root / "bmstu" / "admission-regulation-2026-amended.pdf"))
    assert client.post("/api/v1/sources", json=update, headers={"X-Role": "EDITOR"}).status_code == 201
    item_id_2 = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()[0]["id"]
    second = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id_2, "profile_code": "regulatory_document", "idempotency_key": "regulation-v2"},
        headers={"X-Role": "EDITOR"},
    ).json()
    assert second["state"] == "PUBLISHED"
    changes = client.get("/api/v1/changes?kind=MODIFIED").json()
    assert any(item["target_key"] == "rule:admission.additional_exam_bonus" for item in changes)


def test_ambiguous_normative_rule_is_review_bound(app_client, fixture_root: Path):
    client, _ = app_client
    source = demo_source_definitions(fixture_root)[4]
    assert client.post("/api/v1/sources", json=_source_payload(source), headers={"X-Role": "EDITOR"}).status_code == 201
    item_id = client.post(f"/api/v1/sources/{source.id}/discover", headers={"X-Role": "EDITOR"}).json()[0]["id"]
    pipeline = client.post(
        "/api/v1/pipelines/run",
        json={"source_id": source.id, "item_id": item_id, "profile_code": "regulatory_document"},
        headers={"X-Role": "EDITOR"},
    ).json()
    assert pipeline["state"] == "NEEDS_REVIEW"
    candidates = client.get(f"/api/v1/extractions/{pipeline['extraction_id']}/candidates").json()
    assert any(item["candidate_kind"] == "rule" and item["status"] == "NEEDS_REVIEW" for item in candidates)
