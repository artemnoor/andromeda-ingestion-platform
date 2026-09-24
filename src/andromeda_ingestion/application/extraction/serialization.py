"""Conversion helpers at the persistence/application boundary."""

from __future__ import annotations

from andromeda_ingestion.domain.contracts import ExtractionProfile, ExtractionResult, OntologySnapshot, PreparedDocument, RawArtifact


def raw_artifact(data: dict) -> RawArtifact:
    return RawArtifact.model_validate(data)


def prepared_document(data: dict) -> PreparedDocument:
    return PreparedDocument.model_validate(data)


def extraction_profile(data: dict) -> ExtractionProfile:
    return ExtractionProfile.model_validate(data)


def extraction_result(data: dict) -> ExtractionResult:
    return ExtractionResult.model_validate(data)


def ontology_snapshot(data: object) -> OntologySnapshot:
    return data if isinstance(data, OntologySnapshot) else OntologySnapshot.model_validate(data or {})
