"""HTTP anti-corruption adapter for the existing Knowledge Core API."""

from __future__ import annotations

from typing import Any, cast

import httpx

from andromeda_ingestion.domain.contracts import CorePublishResult, ObservationCandidate, OntologySnapshot, RawArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.domain.ports.knowledge_core import KnowledgeCorePort
from andromeda_ingestion.infrastructure.config import Settings


class KnowledgeCoreHttpAdapter(KnowledgeCorePort):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_ontology_snapshot(self) -> OntologySnapshot:
        try:
            async with httpx.AsyncClient(base_url=self.settings.knowledge_core_url.rstrip("/"), timeout=10) as client:
                response = await client.get("/api/v1/ontology/versions")
                response.raise_for_status()
                versions = response.json()
                if not versions:
                    return OntologySnapshot()
                active = next((item for item in versions if item.get("status") == "ACTIVE"), versions[0])
                ontology_id = active.get("id")
                if not ontology_id:
                    return OntologySnapshot.model_validate(active)
                detail = await client.get(f"/api/v1/ontology/versions/{ontology_id}")
                detail.raise_for_status()
                payload = detail.json()
                return OntologySnapshot(
                    ontology_version_id=payload.get("id"),
                    version_code=payload.get("version_code"),
                    object_types=payload.get("object_types", []),
                    properties=payload.get("properties", []),
                    relation_types=payload.get("relation_types", []),
                    rule_dsl_schema=payload.get("rule_dsl_schema", {}),
                )
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamError(
                "CORE_UNAVAILABLE", "Knowledge Core ontology endpoint is unavailable", {"url": self.settings.knowledge_core_url}
            ) from exc

    async def register_source(self, source: SourceDefinition, artifact: RawArtifact) -> str:
        payload = {
            "source_type": str(source.source_type),
            "url": artifact.canonical_url,
            "external_identifier": f"{source.stable_key}:{artifact.checksum}",
            "publisher": source.organization,
            "retrieved_at": artifact.retrieved_at.isoformat(),
            "checksum": artifact.checksum,
            "content_metadata": {"content_type": artifact.content_type, "artifact_id": artifact.id, **artifact.metadata},
            "trust_metadata": {"trust_level": str(source.trust_level)},
            "parser_version": "andromeda-ingestion-0.1",
        }
        response = await self._request("POST", "/api/v1/sources", json=payload)
        source_id = response.get("id")
        if not source_id:
            raise UpstreamError("CORE_VALIDATION_FAILED", "Knowledge Core source response has no identifier", {})
        return str(source_id)

    async def publish_observation(
        self, source_id: str, candidate: ObservationCandidate, *, idempotency_key: str, correlation_id: str
    ) -> CorePublishResult:
        payload = {
            "source_id": source_id,
            "source_document_id": candidate.evidence[0].artifact_id,
            "subject_candidate": candidate.subject_candidate.model_dump(mode="json"),
            "property_candidate": candidate.property_candidate,
            "relation_candidate": candidate.relation_candidate,
            "value": candidate.value,
            "value_type": candidate.value_type,
            "evidence": {
                "items": [item.model_dump(mode="json") for item in candidate.evidence],
                "candidate_kind": candidate.candidate_kind,
            },
            "confidence": float(candidate.confidence),
            "confidence_status": str(candidate.confidence_status),
            "ontology_version_id": candidate.ontology_version_id,
            "raw_payload": candidate.raw_payload,
        }
        response = await self._request(
            "POST", "/api/v1/observations", json=payload, idempotency_key=idempotency_key, correlation_id=correlation_id
        )
        return CorePublishResult(
            candidate_id=candidate.candidate_id,
            core_source_id=source_id,
            core_observation_id=response.get("id"),
            status=str(response.get("status", "PUBLISHED")),
            review_id=response.get("review_id"),
            proposal_id=response.get("proposal_id"),
            details=response,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Role": self.settings.knowledge_core_role}
        if self.settings.knowledge_core_token:
            headers["Authorization"] = f"Bearer {self.settings.knowledge_core_token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        try:
            async with httpx.AsyncClient(base_url=self.settings.knowledge_core_url.rstrip("/"), timeout=20) as client:
                response = await client.request(method, path, headers=headers, json=json)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise UpstreamError("CORE_VALIDATION_FAILED", "Knowledge Core returned a non-object response", {})
                return cast(dict[str, Any], payload)
        except UpstreamError:
            raise
        except httpx.HTTPError as exc:
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            raise UpstreamError(
                "CORE_UNAVAILABLE",
                "Knowledge Core request failed",
                {"path": path, "status_code": status_code},
            ) from exc
