"""Run a real-network smoke test across Ingestion and Knowledge Core.

The script deliberately talks to both services through TCP HTTP. It does not
import either FastAPI app or call application services directly.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_migrations(repo: Path, database_url: str) -> None:
    environment = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(repo / "src")}
    config_path = (repo / "alembic.ini").as_posix()
    script_path = (repo / "alembic").as_posix()
    source_path = (repo / "src").as_posix()
    migration_code = (
        "from alembic.config import Config; from alembic import command; "
        f"config = Config({config_path!r}); "
        f"config.set_main_option('script_location', {script_path!r}); "
        f"config.set_main_option('prepend_sys_path', {source_path!r}); "
        "command.upgrade(config, 'head')"
    )
    result = subprocess.run(
        [sys.executable, "-c", migration_code],
        cwd=repo.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic failed in {repo}:\n{result.stdout}\n{result.stderr}")


def _start(repo: Path, module: str, port: int, environment: dict[str, str]) -> subprocess.Popen[bytes]:
    process_environment = {
        **os.environ,
        **environment,
        "PYTHONPATH": str(repo / "src"),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=repo,
        env=process_environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_service(client: httpx.Client, url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before becoming ready: {process.returncode}")
        try:
            if client.get(f"{url}/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"Service did not become ready: {url}")


def _post(client: httpx.Client, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(url, json=payload, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"POST {url} failed: {response.status_code} {response.text}")
    return response.json()


def _core_contract_smoke(client: httpx.Client, core_url: str) -> dict[str, Any]:
    editor = {"X-Role": "EDITOR"}
    reviewer = {"X-Role": "REVIEWER"}
    snapshot = client.get(f"{core_url}/api/v1/ontology/snapshot")
    snapshot.raise_for_status()
    ontology = _post(client, f"{core_url}/api/v1/ontology/versions", {"version_code": "http-e2e-v1"}, editor)
    ontology_id = ontology["id"]
    for code, name in [("University", "University"), ("Program", "Program"), ("AdmissionBenefit", "Admission benefit")]:
        _post(client, f"{core_url}/api/v1/ontology/versions/{ontology_id}/object-types", {"code": code, "name": name}, editor)
    for code in ["required_exam", "minimum_score", "budget_places", "tuition_per_year"]:
        _post(
            client,
            f"{core_url}/api/v1/ontology/versions/{ontology_id}/properties",
            {"code": code, "value_type": "reference", "allowed_object_types": ["Program"]},
            editor,
        )
    _post(
        client,
        f"{core_url}/api/v1/ontology/versions/{ontology_id}/relation-types",
        {"code": "HAS_CURRICULUM", "name": "has curriculum"},
        editor,
    )
    activated = client.post(f"{core_url}/api/v1/ontology/versions/{ontology_id}/activate", headers=reviewer)
    activated.raise_for_status()
    source = _post(
        client,
        f"{core_url}/api/v1/sources",
        {"source_type": "DOCUMENT", "external_identifier": "http-e2e-source", "publisher": "E2E", "checksum": "e2e-source"},
        editor,
    )
    document = _post(
        client,
        f"{core_url}/api/v1/source-documents",
        {"source_id": source["id"], "document_checksum": "e2e-document", "title": "HTTP E2E document"},
        editor,
    )
    observation = _post(
        client,
        f"{core_url}/api/v1/observations",
        {
            "source_id": source["id"],
            "source_document_id": document["id"],
            "subject_candidate": {"stable_key": "program:http-e2e", "object_type_code": "Program", "display_name": "HTTP E2E program"},
            "property_candidate": "minimum_score",
            "value": 40,
            "value_type": "integer",
            "evidence": {"page": 1},
            "confidence": 0.99,
            "ontology_version_id": ontology_id,
        },
        editor,
    )
    rule_payload = {
        "candidate_id": "http-e2e-rule-1",
        "logical_key": "http.e2e.known_rule",
        "rule_type": "admission_benefit",
        "conditions": {"kind": "comparison", "operator": ">=", "left": {"kind": "context", "path": "campaign_year"}, "right": 2027},
        "effects": [{"type": "ADD", "target": "admission_score", "value": 30}],
        "confidence": 0.99,
        "confidence_status": "HIGH_CONFIDENCE",
        "evidence": [{"page": 2, "quote": "known benefit"}],
        "source_id": source["id"],
        "source_document_id": document["id"],
        "ontology_version_id": ontology_id,
    }
    rule = _post(client, f"{core_url}/api/v1/rules/candidates", rule_payload, {**editor, "Idempotency-Key": "http-e2e-rule-1"})
    unknown = _post(
        client,
        f"{core_url}/api/v1/rules/candidates",
        {
            **rule_payload,
            "candidate_id": "http-e2e-rule-unknown",
            "conditions": {
                "kind": "exists",
                "target": {"kind": "fact", "property": "RegionalEducationalCoefficient", "id": "http-e2e-fact-unknown"},
            },
        },
        {**editor, "Idempotency-Key": "http-e2e-rule-unknown"},
    )
    if (
        not observation.get("id")
        or not rule.get("rule_id")
        or rule.get("status") != "DRAFT"
        or unknown.get("status") != "NEEDS_REVIEW"
        or not unknown.get("proposal_id")
    ):
        raise AssertionError("Core HTTP contract smoke did not produce the expected observation/rule/review results")
    provenance = client.get(f"{core_url}/api/v1/provenance/{rule['provenance_id']}")
    provenance.raise_for_status()
    if provenance.json()["source_document"]["id"] != document["id"]:
        raise AssertionError("Rule provenance does not point to the immutable source document")
    return {"ontology_id": ontology_id, "source_id": source["id"], "document_id": document["id"], "rule_id": rule["rule_id"], "review_id": unknown["review_id"]}


def _ingestion_pipeline_smoke(client: httpx.Client, ingestion_url: str, core_url: str, fixture_root: Path) -> dict[str, Any]:
    editor = {"X-Role": "EDITOR"}
    source_id = "http-e2e-ingestion-source"
    source = _post(
        client,
        f"{ingestion_url}/api/v1/sources",
        {
            "id": source_id,
            "stable_key": "http.e2e.ingestion",
            "organization": "BMSTU",
            "source_category": "UNIVERSITY",
            "source_type": "WEB_PAGE",
            "base_url": "https://admissions.bmstu.ru/programs/09.03.01",
            "discovery_strategy": "STATIC_URL",
            "fetch_strategy": "FIXTURE",
            "content_type": "text/html",
            "trust_level": "OFFICIAL_PRIMARY",
            "allowed_hosts": ["admissions.bmstu.ru"],
            "metadata": {
                "profile_code": "university_program",
                "document_kind": "program",
                "fixture_path": str(fixture_root / "bmstu" / "program.html"),
                "discovered_items": [{"url": "https://admissions.bmstu.ru/programs/09.03.01", "document_kind": "program", "relevance_score": "1.0"}],
            },
        },
        editor,
    )
    items = client.post(f"{ingestion_url}/api/v1/sources/{source['id']}/discover", headers=editor)
    items.raise_for_status()
    item_id = items.json()[0]["id"]
    pipeline = _post(
        client,
        f"{ingestion_url}/api/v1/pipelines/run",
        {"source_id": source["id"], "item_id": item_id, "profile_code": "university_program"},
        editor,
    )
    if pipeline["state"] != "PUBLISHED":
        raise AssertionError(f"Real Ingestion -> Core pipeline did not publish: {pipeline}")
    candidates = client.get(f"{ingestion_url}/api/v1/extractions/{pipeline['extraction_id']}/candidates")
    candidates.raise_for_status()
    rows = candidates.json()
    if not rows or not all(row.get("core_observation_id") for row in rows if row["candidate_kind"] in {"fact", "relation"}):
        raise AssertionError("Real HTTP pipeline did not persist Core observation identifiers on candidates")
    history = client.get(f"{ingestion_url}/api/v1/pipelines/{pipeline['id']}")
    history.raise_for_status()
    if not history.json()["transition_history"]:
        raise AssertionError("Pipeline transition history is empty")
    regulation_source_id = "http-e2e-regulation-source"
    regulation_source = _post(
        client,
        f"{ingestion_url}/api/v1/sources",
        {
            "id": regulation_source_id,
            "stable_key": "http.e2e.regulation",
            "organization": "BMSTU",
            "source_category": "UNIVERSITY",
            "source_type": "PDF",
            "base_url": "https://admissions.bmstu.ru/documents/admission-regulation-2026.pdf",
            "discovery_strategy": "STATIC_URL",
            "fetch_strategy": "FIXTURE",
            "content_type": "application/pdf",
            "trust_level": "OFFICIAL_PRIMARY",
            "allowed_hosts": ["admissions.bmstu.ru"],
            "metadata": {
                "profile_code": "regulatory_document",
                "document_kind": "regulatory_document",
                "fixture_path": str(fixture_root / "bmstu" / "admission-regulation-2026.pdf"),
                "discovered_items": [{"url": "https://admissions.bmstu.ru/documents/admission-regulation-2026.pdf", "document_kind": "regulatory_document", "relevance_score": "1.0"}],
            },
        },
        editor,
    )
    regulation_items = client.post(f"{ingestion_url}/api/v1/sources/{regulation_source['id']}/discover", headers=editor)
    regulation_items.raise_for_status()
    regulation_pipeline = _post(
        client,
        f"{ingestion_url}/api/v1/pipelines/run",
        {"source_id": regulation_source["id"], "item_id": regulation_items.json()[0]["id"], "profile_code": "regulatory_document"},
        editor,
    )
    if regulation_pipeline["state"] != "PUBLISHED":
        raise AssertionError(f"Rule candidate pipeline was expected to publish without a false effect-target review: {regulation_pipeline}")
    regulation_candidates_response = client.get(f"{ingestion_url}/api/v1/extractions/{regulation_pipeline['extraction_id']}/candidates")
    regulation_candidates_response.raise_for_status()
    regulation_candidates = regulation_candidates_response.json()
    rule_candidate = next(item for item in regulation_candidates if item["candidate_kind"] == "rule")
    if not rule_candidate.get("core_rule_id") or rule_candidate.get("core_observation_id"):
        raise AssertionError("CandidateRule crossed the real HTTP boundary as an observation or without a Core rule id")
    core_rule = client.get(f"{core_url}/api/v1/rules/{rule_candidate['core_rule_id']}")
    core_rule.raise_for_status()
    if core_rule.json()["status"] != "DRAFT":
        raise AssertionError(f"Rule candidate must remain a Core draft, got {core_rule.json()['status']}")
    provenance = client.get(f"{core_url}/api/v1/provenance/{rule_candidate['core_provenance_id']}")
    provenance.raise_for_status()
    if provenance.json().get("source_document") is None:
        raise AssertionError("Rule proposal provenance has no source document")
    return {
        "pipeline_id": pipeline["id"],
        "extraction_id": pipeline["extraction_id"],
        "candidate_count": len(rows),
        "rule_pipeline_id": regulation_pipeline["id"],
        "core_rule_id": rule_candidate["core_rule_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-dir", type=Path, default=Path(__file__).resolve().parents[2] / "max_test")
    parser.add_argument("--ingestion-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--fixture-root", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures")
    args = parser.parse_args()
    core_dir = args.core_dir.resolve()
    ingestion_dir = args.ingestion_dir.resolve()
    fixture_root = args.fixture_root.resolve()
    core_port, ingestion_port = _free_port(), _free_port()
    core_url, ingestion_url = f"http://127.0.0.1:{core_port}", f"http://127.0.0.1:{ingestion_port}"
    with tempfile.TemporaryDirectory(prefix="andromeda-http-e2e-") as temporary:
        temp = Path(temporary)
        core_db = f"sqlite+aiosqlite:///{(temp / 'core.db').as_posix()}"
        ingestion_db = f"sqlite+aiosqlite:///{(temp / 'ingestion.db').as_posix()}"
        _run_migrations(core_dir, core_db)
        _run_migrations(ingestion_dir, ingestion_db)
        core_process = _start(core_dir, "andromeda_core.main:app", core_port, {"APP_ENV": "production", "DATABASE_URL": core_db, "API_DOCS_ENABLED": "false"})
        ingestion_process = _start(
            ingestion_dir,
            "andromeda_ingestion.main:app",
            ingestion_port,
            {
                "APP_ENV": "production",
                "DATABASE_URL": ingestion_db,
                "ARTIFACT_STORAGE_ROOT": str(temp / "artifacts"),
                "FIXTURE_ROOT": str(fixture_root),
                "KNOWLEDGE_CORE_URL": core_url,
                "MOCK_AI_ENABLED": "true",
                "AI_PROVIDER": "mock",
                "API_DOCS_ENABLED": "false",
            },
        )
        try:
            with httpx.Client(timeout=15) as client:
                _wait_for_service(client, core_url, core_process)
                _wait_for_service(client, ingestion_url, ingestion_process)
                result = {"core": _core_contract_smoke(client, core_url), "ingestion": _ingestion_pipeline_smoke(client, ingestion_url, core_url, fixture_root)}
                print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            for process in (ingestion_process, core_process):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
