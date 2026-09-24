# Knowledge Core integration

The platform uses only `KnowledgeCorePort`. The production adapter calls the
existing Core routes:

| Ingestion operation | Core route |
|---|---|
| ontology snapshot | `GET /api/v1/ontology/versions`, then `GET /api/v1/ontology/versions/{id}` |
| register source/artifact provenance | `POST /api/v1/sources` with `X-Role` |
| publish candidate observation | `POST /api/v1/observations` with `Idempotency-Key` and `X-Correlation-ID` |

The existing Core currently exposes a generic Observation envelope rather than a
dedicated `CandidateRule`/`CandidateRelation` ingestion endpoint. Therefore this
service maps facts to `property_candidate`, relations to `relation_candidate`,
and rules/changes/unknown concepts to typed `property_candidate` + `raw_payload`
with full evidence. Core still decides whether an observation becomes canonical
knowledge or a review/proposal. This is an intentional compatibility adapter,
not a direct-DB shortcut. A future Core contract can add dedicated candidate
routes without changing the ingestion domain/application code.

The mock adapter mirrors this contract for CI. Live Core smoke is optional and
requires a running Core URL/database; no external AI key is required for the
ingestion test suite.

