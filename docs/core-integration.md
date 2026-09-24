# Knowledge Core integration

The platform uses only `KnowledgeCorePort`. The production adapter calls the
existing Core routes:

| Ingestion operation | Core route |
|---|---|
| ontology snapshot | GET /api/v1/ontology/snapshot |
| register logical source | POST /api/v1/sources with X-Role |
| register immutable document metadata | POST /api/v1/source-documents with checksum and artifact storage reference |
| publish candidate observation | `POST /api/v1/observations` with `Idempotency-Key` and `X-Correlation-ID` |
| publish first-class rule candidate | `POST /api/v1/rules/candidates` with `Idempotency-Key` and `X-Correlation-ID` |

Facts and relations still use the generic observation envelope. Rules use the
dedicated first-class `CandidateRule` endpoint, where Core validates the Rule
DSL, records immutable source-document provenance, creates ontology proposals
for unknown semantic references, and leaves the rule as `DRAFT` or
`NEEDS_REVIEW`. Ingestion never activates a rule and never writes Core tables.

The Core source_document_id points to metadata only. Raw bytes never cross the
boundary and remain behind Ingestion's ArtifactStoragePort. The mock adapter
mirrors source/document registration and observation idempotency for CI. Live
Core smoke is optional and requires a running Core URL/database; no external AI
key is required for the ingestion test suite.
