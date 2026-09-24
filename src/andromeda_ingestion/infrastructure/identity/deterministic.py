"""Safe deterministic entity resolution for high-confidence aliases."""

from __future__ import annotations

import re

from andromeda_ingestion.domain.contracts import CandidateEntity, OntologySnapshot
from andromeda_ingestion.domain.ports.ai import EntityResolutionPort


class DeterministicEntityResolver(EntityResolutionPort):
    async def resolve(self, entity: CandidateEntity, ontology: OntologySnapshot) -> dict[str, object]:
        normalized = self._normalize(entity.display_name)
        for item in ontology.object_types:
            aliases = [str(value) for value in item.get("aliases", [])]
            if normalized in {self._normalize(alias) for alias in aliases}:
                return {
                    "status": "RESOLVED",
                    "stable_key": item.get("stable_key", entity.stable_key),
                    "confidence": 0.98,
                    "method": "alias",
                }
        return {"status": "UNRESOLVED", "stable_key": entity.stable_key, "confidence": 0.82, "method": "candidate_stable_key"}

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9а-я]+", " ", value.casefold()).strip()
