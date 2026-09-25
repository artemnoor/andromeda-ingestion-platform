"""Opt-in, real-network BMSTU → DeepSeek → HTTP Knowledge Core evaluation.

This command is intentionally not called by pytest, CI, or package startup.
It requires ``--confirm-live-ai`` because each uncached extraction can incur
provider charges. It runs the configured ``run_live`` entries in the curated
official-source manifest, or one selected entry when ``--source`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
MANIFEST = ROOT / "fixtures" / "real_sources" / "bmstu" / "evaluation.json"
DEFAULT_CORE_URL = "http://127.0.0.1:18100"
DEFAULT_INGESTION_URL = "http://127.0.0.1:18101"
EXPECTED_MODEL = "deepseek/deepseek-v4.1-flash"


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _request(
    client: httpx.Client,
    base_url: str,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    role: str | None = None,
    params: dict[str, str] | None = None,
    allow_not_found: bool = False,
) -> Any:
    headers = {"X-Role": role} if role else {}
    response = client.request(
        method,
        f"{base_url.rstrip('/')}{path}",
        json=json_body,
        headers=headers,
        params=params,
    )
    if response.status_code == 404 and allow_not_found:
        return None
    if response.is_error:
        # Never echo response bodies: upstream error payloads are not needed in
        # the report and can contain provider or source-controlled text.
        raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc


def _validate_live_settings() -> dict[str, Any]:
    from andromeda_ingestion.infrastructure.config import Settings

    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]  # Pydantic Settings runtime option
    endpoint = urlparse(settings.ai_endpoint or "")
    checks = {
        "provider": settings.ai_provider == "polza",
        "endpoint_host": endpoint.hostname == "polza.ai",
        "endpoint_path": endpoint.path.startswith("/api/v1"),
        "api_key_present": bool(settings.ai_api_key),
        "model": settings.ai_model == EXPECTED_MODEL,
        "timeout_seconds": settings.ai_timeout_seconds >= 180,
        "structured_output": settings.ai_structured_output_mode == "json_object",
        "mock_ai_disabled": not settings.mock_ai_enabled,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Live configuration check failed: " + ", ".join(failed))
    return {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "timeout_seconds": settings.ai_timeout_seconds,
        "structured_output_mode": settings.ai_structured_output_mode,
        "mock_ai_enabled": settings.mock_ai_enabled,
        "endpoint_host": endpoint.hostname,
        "api_key_present": bool(settings.ai_api_key),
    }


def _ensure_core_ontology(client: httpx.Client, core_url: str) -> dict[str, Any]:
    snapshot = _request(client, core_url, "GET", "/api/v1/ontology/snapshot")
    if snapshot.get("ontology_version_id"):
        if not snapshot.get("object_types"):
            raise RuntimeError("Core has an active but empty ontology; refusing to mutate it")
        return snapshot

    versions = _request(client, core_url, "GET", "/api/v1/ontology/versions")
    version_code = "bmstu-live-evaluation-2026-v1"
    version = next((item for item in versions if item.get("version_code") == version_code), None)
    if version is None:
        payload: dict[str, Any] = {"version_code": version_code, "change_type": "BACKWARD_COMPATIBLE"}
        if versions:
            payload["previous_version_id"] = versions[0]["id"]
        version = _request(client, core_url, "POST", "/api/v1/ontology/versions", json_body=payload, role="EDITOR")

    ontology_id = str(version["id"])
    definitions = _request(client, core_url, "GET", f"/api/v1/ontology/versions/{ontology_id}")
    object_types = {
        "University": "University",
        "Program": "Educational program",
        "Curriculum": "Curriculum",
        "Subject": "Subject",
        "Exam": "Entrance examination",
        "AdmissionCampaign": "Admission campaign",
        "AdmissionBenefit": "Admission benefit",
        "Document": "Official document",
    }
    existing_types = {item.get("code") for item in definitions.get("object_types", [])}
    for code, name in object_types.items():
        if code not in existing_types:
            _request(
                client,
                core_url,
                "POST",
                f"/api/v1/ontology/versions/{ontology_id}/object-types",
                json_body={"code": code, "name": name, "description": "Curated baseline for BMSTU live evaluation"},
                role="EDITOR",
            )

    properties = [
        ("program.code", "string", ["Program"]),
        ("program.name", "string", ["Program"]),
        ("program.duration_years", "integer", ["Program"]),
        ("admission.minimum_score", "integer", ["Program"]),
        ("admission.budget_places", "integer", ["Program"]),
        ("admission.tuition_per_year", "integer", ["Program"]),
        ("admission.individual_achievement_points", "integer", ["Program"]),
    ]
    existing_properties = {item.get("code") for item in definitions.get("properties", [])}
    for code, value_type, allowed_types in properties:
        if code not in existing_properties:
            _request(
                client,
                core_url,
                "POST",
                f"/api/v1/ontology/versions/{ontology_id}/properties",
                json_body={
                    "code": code,
                    "value_type": value_type,
                    "allowed_object_types": allowed_types,
                    "description": "Curated baseline for BMSTU live evaluation",
                },
                role="EDITOR",
            )

    relations = [
        ("OFFERS", "offers", ["University"], ["Program"]),
        ("HAS_CURRICULUM", "has curriculum", ["Program"], ["Curriculum"]),
        ("REQUIRES_EXAM", "requires entrance examination", ["Program"], ["Exam"]),
    ]
    existing_relations = {item.get("code") for item in definitions.get("relation_types", [])}
    for code, name, source_types, target_types in relations:
        if code not in existing_relations:
            _request(
                client,
                core_url,
                "POST",
                f"/api/v1/ontology/versions/{ontology_id}/relation-types",
                json_body={
                    "code": code,
                    "name": name,
                    "allowed_source_types": source_types,
                    "allowed_target_types": target_types,
                    "cardinality": "MANY_TO_MANY",
                    "description": "Curated baseline for BMSTU live evaluation",
                },
                role="EDITOR",
            )

    if version.get("status") != "ACTIVE":
        _request(
            client,
            core_url,
            "POST",
            f"/api/v1/ontology/versions/{ontology_id}/activate",
            role="REVIEWER",
            params={"expected_version": str(version.get("row_version", 1))},
        )
    snapshot = _request(client, core_url, "GET", "/api/v1/ontology/snapshot")
    if snapshot.get("ontology_version_id") != ontology_id or not snapshot.get("object_types"):
        raise RuntimeError("Core ontology bootstrap did not produce an active ontology snapshot")
    return snapshot


def _register_source(client: httpx.Client, ingestion_url: str, entry: dict[str, Any]) -> dict[str, Any]:
    host = urlparse(entry["url"]).hostname
    payload = {
        "stable_key": entry["stable_key"],
        "organization": entry.get("organization") or _organization_for_entry(entry),
        "source_category": "UNIVERSITY",
        "source_type": entry["source_type"],
        "base_url": entry["url"],
        "discovery_strategy": "STATIC_URL",
        "fetch_strategy": "HTTP",
        "content_type": "application/pdf" if entry["source_type"] == "PDF" else "text/html",
        "trust_level": "OFFICIAL_PRIMARY",
        "refresh_policy": {"mode": "on_demand", "change_detection": "sha256"},
        "allowed_hosts": [host],
        "metadata": {
            "dataset_id": "bmstu-admissions-2026-2027-v1",
            "document_kind": entry["document_kind"],
            "profile_code": entry["profile_code"],
            "max_discovery_items": 1,
            "discovered_items": [
                {
                    "url": entry["url"],
                    "document_kind": entry["document_kind"],
                    "metadata": {"profile_code": entry["profile_code"]},
                }
            ],
        },
    }
    return _request(client, ingestion_url, "POST", "/api/v1/sources", json_body=payload, role="EDITOR")


def _organization_for_entry(entry: dict[str, Any]) -> str:
    host = urlparse(entry["url"]).hostname
    if host == "kf.bmstu.ru":
        return "Калужский филиал МГТУ им. Н.Э. Баумана"
    return "МГТУ им. Н.Э. Баумана"


def _ensure_source_profile(client: httpx.Client, ingestion_url: str, entry: dict[str, Any]) -> None:
    instructions = entry.get("profile_instructions")
    if not instructions:
        return
    from andromeda_ingestion.domain.contracts import LLMExtractionPayload
    from andromeda_ingestion.infrastructure.ai.profiles import CORE_RULE_DSL_SCHEMA

    profile_code = str(entry["profile_code"])
    prompt_version = str(
        entry.get("profile_prompt_version")
        or ("bmstu-admission-minimums-2026-v1" if profile_code == "bmstu_admission_minimums_2026" else f"{profile_code}-v1")
    )
    existing = _request(
        client,
        ingestion_url,
        "GET",
        f"/api/v1/profiles/{profile_code}",
        allow_not_found=True,
    )
    if existing:
        if existing.get("prompt_version") != prompt_version:
            raise RuntimeError(f"Profile {profile_code} exists with a different prompt version; refusing silent overwrite")
        return
    _request(
        client,
        ingestion_url,
        "POST",
        "/api/v1/profiles",
        json_body={
            "profile_code": profile_code,
            "version": 1,
            "expected_document_types": [entry["document_kind"]],
            "expected_ontology_concepts": ["University", "Program", "AdmissionCampaign", "Exam", "Rule"],
            "output_schema": LLMExtractionPayload.model_json_schema(),
            "instructions": instructions,
            "validation_rules": {"require_evidence": True, "low_confidence_threshold": 0.8},
            "ai_strategy": "structured_json",
            "prompt_version": prompt_version,
            "metadata": {"rule_dsl_schema": CORE_RULE_DSL_SCHEMA, "evaluation_dataset": "bmstu-admissions-2026-2027-v1"},
        },
        role="ADMIN",
    )


def _verify_evidence(candidates: list[dict[str, Any]], chunks: list[dict[str, Any]], artifact: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for candidate in candidates:
        for evidence in candidate.get("evidence", []):
            locator = evidence.get("locator", {})
            quote = evidence.get("quote") or locator.get("quote") or ""
            page = locator.get("page")
            same_page = [
                item
                for item in chunks
                if page is None or item.get("locator", {}).get("page") == page
            ]
            quote_match = bool(quote) and any(_normalize(quote) in _normalize(item.get("text", "")) for item in same_page)
            checks.append(
                {
                    "candidate_id": candidate.get("id"),
                    "candidate_kind": candidate.get("candidate_kind"),
                    "artifact_id_matches": locator.get("artifact_id") == artifact.get("id"),
                    "source_url_matches": locator.get("source_url") in {artifact.get("canonical_url"), artifact.get("final_url")},
                    "page": page,
                    "page_matches": page is None or bool(same_page),
                    "quote_present_in_exact_prepared_artifact": quote_match,
                    "quote": quote,
                }
            )
    exact = sum(
        bool(item["artifact_id_matches"] and item["source_url_matches"] and item["page_matches"] and item["quote_present_in_exact_prepared_artifact"])
        for item in checks
    )
    return {"verified": exact, "total": len(checks), "accuracy": exact / len(checks) if checks else None, "assertions": checks[:10]}


def _walk(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _rule_meets_expectation(rule: dict[str, Any], expectation: dict[str, Any]) -> bool:
    threshold = expectation.get("threshold")
    operator = expectation.get("operator")
    for node in _walk(rule.get("conditions", {})):
        right = node.get("right")
        values = [right.get("value") if isinstance(right, dict) else right, node.get("value"), node.get("threshold")]
        if node.get("operator") == operator and any(str(item) == str(threshold) for item in values):
            return True
    return False


def _semantic_values(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Walk extracted data while excluding evidence text and locator metadata."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in {"evidence", "quote", "locator", "excerpt_hash", "source_note"}:
                continue
            yield from _semantic_values(child, (*path, key))
    elif isinstance(value, list):
        for child in value:
            yield from _semantic_values(child, path)
    else:
        yield path, value


def _golden_metrics(entry: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    result = extraction.get("result_json", {})
    records = [
        record
        for collection in ("entities", "facts", "relations", "rules", "unknown_concepts", "changes")
        for record in result.get(collection, [])
        if isinstance(record, dict)
    ]
    checks: list[dict[str, Any]] = []
    for expected in entry.get("golden_expectations", []):
        expected_value = _normalize(expected["value"])
        contextual_terms = (
            [
                term
                for term in re.split(r"[^\w]+", _normalize(expected.get("field", "")))
                if len(term) > 2 and term not in {"minimum", "score", "official", "program", "study", "year", "points"}
            ]
            if expected.get("kind") in {"number", "identifier"}
            else []
        )
        matched_records: list[int] = []
        for index, record in enumerate(records):
            semantic = list(_semantic_values(record))
            exact_value = any(
                isinstance(value, (str, int, float, bool)) and _normalize(value) == expected_value
                for _path, value in semantic
            )
            serialized = _normalize(" ".join(str(value) for _path, value in semantic))
            context_matches = not contextual_terms or all(term in serialized for term in contextual_terms)
            if exact_value and context_matches:
                matched_records.append(index)
        checks.append({**expected, "passed": bool(matched_records), "matched_records": matched_records[:3]})
    numeric = [item for item in checks if item["kind"] == "number"]
    numeric_correct = sum(bool(item["passed"]) for item in numeric)
    return {
        "field_accuracy": sum(bool(item["passed"]) for item in checks) / len(checks) if checks else None,
        "field_checks": checks,
        "numeric_accuracy": numeric_correct / len(numeric) if numeric else None,
        "numeric_correct": numeric_correct,
        "numeric_total": len(numeric),
    }


def _rule_comparisons(node: Any) -> list[tuple[str, str, str]]:
    comparisons: list[tuple[str, str, str]] = []
    for item in _walk(node):
        if not isinstance(item, dict) or item.get("kind") != "comparison":
            continue
        left = item.get("left")
        right = item.get("right")
        if not isinstance(left, dict) or left.get("kind") != "fact" or not isinstance(right, dict):
            continue
        if right.get("kind") != "literal" or "value" not in right:
            continue
        comparisons.append((_normalize(left.get("exam_subject", "")), str(item.get("operator", "")), str(right["value"])))
    return comparisons


def _condition_matches_expectation(rule: dict[str, Any], expectation: dict[str, Any]) -> bool:
    conditions = rule.get("conditions")
    if not isinstance(conditions, dict) or conditions.get("kind") != "logical" or conditions.get("operator") != "and":
        return False
    args = conditions.get("args")
    if not isinstance(args, list):
        return False

    def expected_tuple(item: dict[str, Any]) -> tuple[str, str, str]:
        return (_normalize(item["subject"]), str(item["operator"]), str(item["threshold"]))

    actual_all: list[tuple[str, str, str]] = []
    actual_any: list[tuple[str, str, str]] = []
    for child in args:
        if isinstance(child, dict) and child.get("kind") == "logical" and child.get("operator") == "or":
            actual_any.extend(_rule_comparisons(child))
        else:
            actual_all.extend(_rule_comparisons(child))
    expected_all = [expected_tuple(item) for item in expectation.get("all_conditions", [])]
    expected_any = [expected_tuple(item) for item in expectation.get("any_conditions", [])]
    return (
        set(actual_all) == set(expected_all)
        and len(actual_all) == len(expected_all)
        and set(actual_any) == set(expected_any)
        and len(actual_any) == len(expected_any)
    )


def _rule_condition_metrics(entry: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    expectations = entry.get("rule_condition_expectations", [])
    checks: list[dict[str, Any]] = []
    for expectation in expectations:
        matching = [
            rule
            for rule in rules
            if _normalize((rule.get("scope") or {}).get("section", "")) == _normalize(expectation["section"])
        ]
        passed = len(matching) == 1 and _condition_matches_expectation(matching[0], expectation)
        checks.append({"section": expectation["section"], "passed": passed, "matching_rules": len(matching)})
    return {
        "correct": sum(bool(item["passed"]) for item in checks),
        "total": len(checks),
        "accuracy": sum(bool(item["passed"]) for item in checks) / len(checks) if checks else None,
        "checks": checks,
    }


def _rule_effect_matches_expectation(rule: dict[str, Any], expectation: dict[str, Any]) -> bool:
    effects = rule.get("effects")
    if not isinstance(effects, list):
        return False
    return any(
        isinstance(effect, dict)
        and effect.get("type") == expectation.get("type")
        and effect.get("target") == expectation.get("target")
        and effect.get("value") == expectation.get("value")
        for effect in effects
    )


def _fact_expectation_metrics(entry: dict[str, Any], extraction_result: dict[str, Any]) -> dict[str, Any]:
    facts = extraction_result.get("facts", [])
    checks: list[dict[str, Any]] = []
    for expectation in entry.get("fact_expectations", []):
        matching = [
            fact
            for fact in facts
            if fact.get("property_code") == expectation["property_code"]
            and fact.get("metadata", {}).get("section") == expectation["section"]
            and str(fact.get("metadata", {}).get("program_code", "")) == str(expectation["program_code"])
        ]
        value = matching[0].get("value") if len(matching) == 1 else None
        minimums = value.get("minimums") if isinstance(value, dict) else None
        expected_minimums = expectation["minimums"]
        passed = (
            len(matching) == 1
            and isinstance(value, dict)
            and value.get("section") == expectation["section"]
            and str(value.get("program_code", "")) == str(expectation["program_code"])
            and isinstance(minimums, list)
            and [
                (str(item.get("subject")), item.get("minimum"), str(item.get("printed_marker")))
                for item in minimums
            ]
            == [
                (str(item["subject"]), item["minimum"], str(item["printed_marker"]))
                for item in expected_minimums
            ]
        )
        checks.append({"section": expectation["section"], "passed": passed, "matching_facts": len(matching)})
    return {
        "correct": sum(bool(item["passed"]) for item in checks),
        "total": len(checks),
        "accuracy": sum(bool(item["passed"]) for item in checks) / len(checks) if checks else None,
        "checks": checks,
    }


def _evaluate_one(
    client: httpx.Client,
    core_url: str,
    ingestion_url: str,
    entry: dict[str, Any],
    run_date: str,
) -> dict[str, Any]:
    _ensure_source_profile(client, ingestion_url, entry)
    source = _register_source(client, ingestion_url, entry)
    source_id = str(source["id"])
    discovered = _request(client, ingestion_url, "POST", f"/api/v1/sources/{source_id}/discover", role="EDITOR")
    item = next((row for row in discovered if row.get("canonical_url") == entry["url"]), None)
    if item is None:
        raise RuntimeError(f"Configured official URL was not discovered for {entry['id']}")

    pipeline_started = perf_counter()
    pipeline = _request(
        client,
        ingestion_url,
        "POST",
        "/api/v1/pipelines/run",
        json_body={
            "source_id": source_id,
            "item_id": item["id"],
            "profile_code": entry["profile_code"],
            "idempotency_key": f"live-bmstu:{entry['id']}:{run_date}"
            + (f":{entry['run_version']}" if entry.get("run_version") else ""),
        },
        role="EDITOR",
    )
    pipeline_elapsed_seconds = round(perf_counter() - pipeline_started, 3)
    state = pipeline.get("state")
    if state not in {"PUBLISHED", "NEEDS_REVIEW", "SKIPPED_UNCHANGED"}:
        details: dict[str, Any] = {
            "evaluation_source_id": entry["id"],
            "source_id": source_id,
            "source_url": entry["url"],
            "pipeline_id": pipeline.get("id"),
            "pipeline_state": state,
            "pipeline_elapsed_seconds": pipeline_elapsed_seconds,
            "profile_code": entry["profile_code"],
            "profile_prompt_version": entry.get("profile_prompt_version"),
            "artifact_id": pipeline.get("artifact_id"),
        }
        artifact_id = pipeline.get("artifact_id")
        if artifact_id:
            try:
                failed_artifact = _request(client, ingestion_url, "GET", f"/api/v1/artifacts/{artifact_id}")
                prepared_failed = _request(
                    client, ingestion_url, "POST", f"/api/v1/artifacts/{artifact_id}/prepare", role="EDITOR"
                )
                failed_chunks = prepared_failed.get("content_chunks", [])
                details["artifact"] = {
                    "requested_url": failed_artifact.get("requested_url"),
                    "canonical_url": failed_artifact.get("canonical_url"),
                    "final_url": failed_artifact.get("final_url"),
                    "http_status": failed_artifact.get("http_status"),
                    "content_type": failed_artifact.get("content_type"),
                    "byte_size": failed_artifact.get("byte_size"),
                    "checksum": failed_artifact.get("checksum"),
                    "retrieved_at": failed_artifact.get("retrieved_at"),
                }
                details["preparation"] = {
                    "content_chunk_count": len(failed_chunks),
                    "prepared_character_count": sum(len(str(chunk.get("text", ""))) for chunk in failed_chunks),
                    "truncated_chunk_count": sum(bool(chunk.get("truncated")) for chunk in failed_chunks),
                }
            except Exception:
                details["artifact_metadata_available"] = False
        raise SourceRunFailure(str(pipeline.get("error_code") or "PIPELINE_FAILED"), details)

    artifact_id = str(pipeline.get("artifact_id") or "")
    if not artifact_id:
        raise RuntimeError(f"Pipeline {entry['id']} did not return an artifact ID")
    artifact = _request(client, ingestion_url, "GET", f"/api/v1/artifacts/{artifact_id}")
    if artifact.get("http_status") != 200 or not re.fullmatch(r"[a-f0-9]{64}", str(artifact.get("checksum", ""))):
        raise RuntimeError(f"Artifact for {entry['id']} lacks an HTTP 200 result or SHA-256 checksum")
    if urlparse(str(artifact.get("final_url", ""))).hostname not in {urlparse(entry["url"]).hostname}:
        raise RuntimeError(f"Artifact for {entry['id']} ended on a non-allowlisted host")

    extraction_id = pipeline.get("extraction_id")
    reused_extraction = state == "SKIPPED_UNCHANGED"
    if not extraction_id:
        extracted = _request(
            client,
            ingestion_url,
            "POST",
            f"/api/v1/artifacts/{artifact_id}/extract",
            json_body={"profile_code": entry["profile_code"]},
            role="EDITOR",
        )
        extraction_id = (extracted.get("extraction") or {}).get("id")
        reused_extraction = bool(extracted.get("cached"))
    if not extraction_id:
        raise RuntimeError(f"No persisted extraction could be read for {entry['id']}")

    extraction_bundle = _request(client, ingestion_url, "GET", f"/api/v1/extractions/{extraction_id}")
    extraction = extraction_bundle.get("extraction", {})
    candidates = extraction_bundle.get("candidates", [])
    if extraction.get("provider") != "polza" or extraction.get("model") != EXPECTED_MODEL:
        raise RuntimeError(f"Extraction {entry['id']} was not produced by the configured live provider/model")

    prepared = _request(client, ingestion_url, "POST", f"/api/v1/artifacts/{artifact_id}/prepare", role="EDITOR")
    evidence = _verify_evidence(candidates, prepared.get("content_chunks", []), artifact)
    golden = _golden_metrics(entry, extraction)
    fact_expectations = _fact_expectation_metrics(entry, extraction.get("result_json", {}))

    core_observations: list[dict[str, Any]] = []
    core_rules: list[dict[str, Any]] = []
    for candidate in candidates:
        observation_id = candidate.get("core_observation_id")
        if observation_id:
            observation = _request(client, core_url, "GET", f"/api/v1/observations/{observation_id}")
            source_document_id = observation.get("source_document_id")
            observation_evidence = observation.get("evidence_json") or {}
            evidence_items = observation_evidence.get("items", []) if isinstance(observation_evidence, dict) else []
            core_observations.append(
                {
                    "id": observation_id,
                    "status": observation.get("status"),
                    "source_id": observation.get("source_id"),
                    "source_document_id": source_document_id,
                    "has_source_document": bool(source_document_id),
                    "evidence_count": len(evidence_items),
                }
            )
        rule_id = candidate.get("core_rule_id")
        if rule_id:
            rule = _request(client, core_url, "GET", f"/api/v1/rules/{rule_id}")
            if rule.get("status") == "ACTIVE":
                raise RuntimeError(f"Safety violation: ingestion activated Core rule {rule_id}")
            provenance_id = rule.get("provenance_id") or candidate.get("core_provenance_id")
            provenance = _request(client, core_url, "GET", f"/api/v1/provenance/{provenance_id}") if provenance_id else {}
            source_document = provenance.get("source_document") or {}
            provenance_source = provenance.get("source") or {}
            core_rules.append(
                {
                    "id": rule_id,
                    "status": rule.get("status"),
                    "logical_key": rule.get("logical_key"),
                    "scope": rule.get("scope"),
                    "conditions": rule.get("conditions"),
                    "effects": rule.get("effects"),
                    "exceptions": rule.get("exceptions", []),
                    "priority": rule.get("priority"),
                    "valid_from": rule.get("valid_from"),
                    "valid_to": rule.get("valid_to"),
                    "confidence": rule.get("confidence"),
                    "provenance_id": provenance_id,
                    "source_document_id": source_document.get("id"),
                    "document_checksum_matches": source_document.get("document_checksum") == artifact.get("checksum"),
                    "source_checksum_matches": provenance_source.get("checksum") == artifact.get("checksum"),
                    "source_trust_level": (provenance_source.get("trust_metadata") or {}).get("trust_level"),
                    "condition_meets_golden": _rule_meets_expectation(rule, entry["rule_expectation"])
                    if entry.get("rule_expectation")
                    else None,
                    "effect_meets_golden": _rule_effect_matches_expectation(rule, entry["rule_effect_expectation"])
                    if entry.get("rule_effect_expectation")
                    else None,
                    "candidate_evidence": candidate.get("evidence", []),
                }
            )

    rule_conditions = _rule_condition_metrics(entry, core_rules)
    reviews = _request(client, core_url, "GET", "/api/v1/reviews", params={"status": "NEEDS_REVIEW"})
    proposals = _request(client, core_url, "GET", "/api/v1/ontology/proposals", params={"status": "PROPOSED"})
    registered_sources = _request(client, core_url, "GET", "/api/v1/sources")
    core_source: dict[str, Any] = next(
        (row for row in registered_sources if row.get("external_identifier") == entry["stable_key"]),
        {},
    )
    trust_metadata = core_source.get("trust_metadata") or {}
    source_trust_matches = trust_metadata.get("trust_level") == "OFFICIAL_PRIMARY"
    source_checksum_matches = core_source.get("checksum") == artifact.get("checksum")
    unknown_candidates = [row for row in candidates if row.get("candidate_kind") == "unknown_concept"]
    candidate_counts: dict[str, int] = {}
    review_count = 0
    for candidate in candidates:
        kind = str(candidate.get("candidate_kind", "unknown"))
        candidate_counts[kind] = candidate_counts.get(kind, 0) + 1
        if candidate.get("status") == "NEEDS_REVIEW":
            review_count += 1

    report = {
        "evaluation_source_id": entry["id"],
        "source_id": source_id,
        "source_key": entry["stable_key"],
        "source_url": entry["url"],
        "trust_level": "OFFICIAL_PRIMARY",
        "core_source": {
            "id": core_source.get("id"),
            "trust_level": trust_metadata.get("trust_level"),
            "trust_level_matches": source_trust_matches,
            "checksum_matches_artifact": source_checksum_matches,
            "content_metadata_artifact_id_matches": (core_source.get("content_metadata") or {}).get("artifact_id")
            == artifact.get("id"),
        },
        "pipeline_id": pipeline.get("id"),
        "pipeline_state": state,
        "artifact": {
            "id": artifact.get("id"),
            "requested_url": artifact.get("requested_url"),
            "canonical_url": artifact.get("canonical_url"),
            "final_url": artifact.get("final_url"),
            "http_status": artifact.get("http_status"),
            "content_type": artifact.get("content_type"),
            "byte_size": artifact.get("byte_size"),
            "checksum": artifact.get("checksum"),
            "retrieved_at": artifact.get("retrieved_at"),
            "metadata": artifact.get("metadata"),
        },
        "extraction": {
            "id": extraction.get("id"),
            "provider": extraction.get("provider"),
            "model": extraction.get("model"),
            "profile_id": extraction.get("profile_id"),
            "duration_ms": extraction.get("duration_ms"),
            "token_usage": extraction.get("token_usage", {}),
            "estimated_cost": extraction.get("estimated_cost"),
            "warnings_count": len(extraction.get("warnings", [])),
            "reused_cached_extraction": reused_extraction,
        },
        "candidate_counts": candidate_counts,
        "typed_candidate_count": len(candidates),
        "empty_semantic_output": not any(
            extraction.get("result_json", {}).get(key)
            for key in ("entities", "facts", "relations", "rules", "unknown_concepts", "changes")
        ),
        "candidate_review_rate": review_count / len(candidates) if candidates else None,
        "evidence_quality": evidence,
        "golden_metrics": golden,
        "core_observations": core_observations,
        "core_rules": core_rules,
        "rule_condition_metrics": rule_conditions,
        "fact_expectation_metrics": fact_expectations,
        "unknown_concept_candidates": len(unknown_candidates),
        "candidate_review_cases": [
            {
                "candidate_id": item.get("id"),
                "candidate_kind": item.get("candidate_kind"),
                "status": item.get("status"),
                "property_code": item.get("property_code"),
                "core_observation_id": item.get("core_observation_id"),
                "core_rule_id": item.get("core_rule_id"),
                "review_id": item.get("review_id"),
                "proposal_id": item.get("proposal_id"),
            }
            for item in candidates
            if item.get("status") == "NEEDS_REVIEW" or item.get("review_id") or item.get("proposal_id")
        ],
        "open_review_count_in_core": len(reviews),
        "ontology_proposal_count_in_core": len(proposals),
    }
    return report


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = _validate_live_settings()
    dataset = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = [entry for entry in dataset["sources"] if entry.get("run_live")]
    if args.source:
        entries = [entry for entry in entries if entry["stable_key"] == args.source or entry["id"] == args.source]
    if not entries:
        raise RuntimeError("No live-run source matched the requested BMSTU evaluation selection")

    timeout = httpx.Timeout(connect=15, read=config["timeout_seconds"] + 90, write=30, pool=15)
    source_failures: list[dict[str, str]] = []
    with httpx.Client(timeout=timeout) as client:
        for base_url, _label in ((args.core_url, "Knowledge Core"), (args.ingestion_url, "Ingestion")):
            for endpoint in ("/health", "/ready"):
                _request(client, base_url, "GET", endpoint)
        ontology = _ensure_core_ontology(client, args.core_url)
        reports: list[dict[str, Any]] = []
        for entry in entries:
            try:
                reports.append(
                    _evaluate_one(client, args.core_url, args.ingestion_url, entry, datetime.now(UTC).date().isoformat())
                )
            except Exception as exc:
                message = str(exc)
                pipeline_error = re.search(r"stopped in [A-Z_]+: ([A-Z_0-9]+)", message)
                http_error = re.search(r"returned HTTP (\d{3})", message)
                safe_code = (
                    str(getattr(exc, "code", ""))
                    or (pipeline_error.group(1) if pipeline_error else "")
                    or (f"HTTP_{http_error.group(1)}" if http_error else type(exc).__name__)
                )
                source_failures.append(
                    {
                        "source_key": entry["stable_key"],
                        "failure_code": safe_code,
                        **(exc.details if isinstance(exc, SourceRunFailure) else {}),
                    }
                )
        ontology_after = _request(client, args.core_url, "GET", "/api/v1/ontology/snapshot")

    failures: list[str] = []
    regulation = next((item for item in reports if item["evaluation_source_id"] == "bmstu-admission-appendix-1-2026"), None)
    if regulation and not regulation["core_rules"]:
        failures.append("the live regulation extraction did not produce a Core CandidateRule")
    if regulation and any(item.get("condition_meets_golden") is False for item in regulation["core_rules"]):
        failures.append("no Core CandidateRule matched the official >= 46 threshold golden")
    if regulation and any(item.get("effect_meets_golden") is False for item in regulation["core_rules"]):
        failures.append("Core CandidateRule effects differ from the reviewed non-admission golden")
    if regulation and regulation["rule_condition_metrics"]["total"] and regulation["rule_condition_metrics"]["accuracy"] != 1:
        failures.append("regulatory rule conditions differ from the reviewed section-specific goldens")
    if regulation and regulation["fact_expectation_metrics"]["total"] and regulation["fact_expectation_metrics"]["accuracy"] != 1:
        failures.append("Mytishchi branch values differ from the reviewed structured-fact golden")
    for item in reports:
        if item["empty_semantic_output"]:
            failures.append(f"live extraction returned no typed candidates for {item['source_key']}")
        golden = item["golden_metrics"]
        if golden["field_accuracy"] is not None and golden["field_accuracy"] < 1:
            failures.append(f"structured field goldens did not all match for {item['source_key']}")
        if golden["numeric_accuracy"] is not None and golden["numeric_accuracy"] < 1:
            failures.append(f"numeric goldens did not all match for {item['source_key']}")
        if not item["core_source"]["trust_level_matches"] or not item["core_source"]["checksum_matches_artifact"]:
            failures.append(f"Core source trust/checksum metadata failed for {item['source_key']}")
        quality = item["evidence_quality"]
        if quality["total"] and quality["verified"] != quality["total"]:
            failures.append(f"evidence validation failed for {item['source_key']}")
        for rule in item["core_rules"]:
            if not rule["document_checksum_matches"] or not rule["source_document_id"]:
                failures.append(f"Core provenance chain is incomplete for {rule['id']}")
            if rule["status"] not in {"DRAFT", "NEEDS_REVIEW"}:
                failures.append(f"Core rule {rule['id']} is not safely held for review")
            if rule["source_trust_level"] != "OFFICIAL_PRIMARY" or not rule["source_checksum_matches"]:
                failures.append(f"Core rule source provenance metadata failed for {rule['id']}")
        if any(not row["has_source_document"] or not row["evidence_count"] for row in item["core_observations"]):
            failures.append(f"Core observation provenance/evidence is incomplete for {item['source_key']}")
    ontology_before_codes = {
        key: sorted(item.get("code", "") for item in ontology.get(collection, []))
        for key, collection in (("types", "object_types"), ("properties", "properties"), ("relations", "relation_types"))
    }
    ontology_after_codes = {
        key: sorted(item.get("code", "") for item in ontology_after.get(collection, []))
        for key, collection in (("types", "object_types"), ("properties", "properties"), ("relations", "relation_types"))
    }
    if ontology_before_codes != ontology_after_codes:
        failures.append("active Core ontology changed during candidate publication")
    failures.extend(f"{item['source_key']} did not complete: {item['failure_code']}" for item in source_failures)

    report = {
        "dataset_id": dataset["dataset_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": config,
        "knowledge_core": {
            "url": args.core_url,
            "ontology_version_id": ontology.get("ontology_version_id"),
            "version_code": ontology.get("version_code"),
            "object_type_count": len(ontology.get("object_types", [])),
            "property_count": len(ontology.get("properties", [])),
            "relation_type_count": len(ontology.get("relation_types", [])),
        },
        "live_source_count": len(reports),
        "live_sources_attempted": len(entries),
        "evaluation_source_count": len(dataset["sources"]),
        "sources": reports,
        "failed_sources": source_failures,
        "ontology_changed_during_run": ontology_before_codes != ontology_after_codes,
        "failed_assertions": failures,
    }
    output_path = Path(args.report).resolve() if args.report else ROOT / "reports" / f"live-bmstu-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(output_path)
    if failures:
        raise LiveEvaluationFailure(report)
    return report


class LiveEvaluationFailure(RuntimeError):
    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__("One or more live-evaluation acceptance checks failed")
        self.report = report


class SourceRunFailure(RuntimeError):
    def __init__(self, code: str, details: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in live BMSTU ingestion and Knowledge Core evaluation")
    parser.add_argument("--confirm-live-ai", action="store_true", help="Explicitly authorize paid live AI calls")
    parser.add_argument("--core-url", default=DEFAULT_CORE_URL)
    parser.add_argument("--ingestion-url", default=DEFAULT_INGESTION_URL)
    parser.add_argument("--source", help="Run only the live source matching this dataset id or stable key")
    parser.add_argument("--report", help="Optional report path; default is ignored reports/live-bmstu-*.json")
    args = parser.parse_args()
    if not args.confirm_live_ai:
        parser.error("--confirm-live-ai is required; this command can incur provider charges")
    try:
        report = run(args)
    except LiveEvaluationFailure as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc), "secrets_printed": False}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
