"""Evidence-backed change detection between extraction versions."""

from __future__ import annotations

from typing import Any

from andromeda_ingestion.domain.changes.fingerprints import fingerprint
from andromeda_ingestion.domain.common import ChangeKind
from andromeda_ingestion.domain.contracts import ExtractionResult


class ChangeDetectionService:
    def compare(self, previous: ExtractionResult | None, current: ExtractionResult) -> list[dict[str, Any]]:
        if previous is None:
            return []
        before = self._index(previous)
        after = self._index(current)
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            old = before.get(key)
            new = after.get(key)
            if old is None and new is not None:
                changes.append(self._change(ChangeKind.ADDED, key, None, new))
            elif old is not None and new is None:
                changes.append(self._change(ChangeKind.REMOVED, key, old, None))
            elif old is not None and new is not None and fingerprint(old) != fingerprint(new):
                kind = ChangeKind.AMBIGUOUS if self._ambiguous(new) else ChangeKind.MODIFIED
                changes.append(self._change(kind, key, old, new))
        return changes

    @staticmethod
    def _index(result: ExtractionResult) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for fact in result.facts:
            payload = fact.model_dump(mode="json")
            values[f"fact:{fact.subject.stable_key}:{fact.property_code}"] = payload
        for relation in result.relations:
            payload = relation.model_dump(mode="json")
            values[f"relation:{relation.subject.stable_key}:{relation.relation_type_code}:{relation.target.stable_key}"] = payload
        for rule in result.rules:
            payload = rule.model_dump(mode="json")
            values[f"rule:{rule.logical_key}"] = payload
        for concept in result.unknown_concepts:
            payload = concept.model_dump(mode="json")
            values[f"unknown:{concept.name}"] = payload
        return values

    @staticmethod
    def _ambiguous(value: dict[str, Any]) -> bool:
        confidence = float(value.get("confidence", 1))
        return confidence < 0.8 or value.get("confidence_status") in {"UNCERTAIN", "CONFLICTING"}

    @staticmethod
    def _change(kind: ChangeKind, key: str, old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
        evidence = (new or old or {}).get("evidence", [])
        return {
            "candidate_id": fingerprint([kind.value, key, old, new])[:32],
            "kind": kind.value,
            "target_key": key,
            "before_fingerprint": fingerprint(old) if old is not None else None,
            "after_fingerprint": fingerprint(new) if new is not None else None,
            "before_payload": old,
            "after_payload": new,
            "confidence": (new or old or {}).get("confidence", 0.5),
            "reason": f"Extraction candidate {kind.value.lower()} compared with previous artifact version",
            "evidence": evidence,
            "fingerprint": fingerprint([kind.value, key, old, new]),
        }
