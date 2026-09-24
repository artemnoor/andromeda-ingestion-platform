# Phase 6: Knowledge Core integration and API

Plan: [index.md](index.md)  
Tasks: 8-9  
Depends on: Phase 5 / Tasks 6-7

## Objective

Expose a stable ingestion API and publish only evidence-backed Observation
envelopes to the real Knowledge Core HTTP contract. Preserve Core ownership of
ontology, facts, rules, review and activation.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../max_test/src/andromeda_core/presentation/api/admin/knowledge.py` | `POST /sources`, `POST /observations` | Current publish seam and role requirements |
| `../max_test/src/andromeda_core/presentation/api/schemas.py` | `SourceCreate`, `ObservationCreate` | Exact payload fields and strict extra handling |
| `../max_test/src/andromeda_core/application/knowledge_service.py` | observation idempotency/unknown concept | Core owns proposal/review promotion logic |
| `../max_test/src/andromeda_core/presentation/api/dependencies.py` | `X-Role` | HTTP adapter must use configured integration role, never admin activation |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_ingestion/domain/ports/knowledge_core.py` | create | versioned Core port |
| `src/andromeda_ingestion/infrastructure/knowledge_core/http.py` | create | timeout/retry/error mapping and payload adapter |
| `src/andromeda_ingestion/application/publishing/service.py` | create | source registration and candidate publication |
| `src/andromeda_ingestion/presentation/api/routes/*.py` | create | typed admin/operations routes |
| `src/andromeda_ingestion/presentation/api/schemas.py` | create | request/response/error schemas/examples |
| `tests/unit/test_core_adapter.py`, `tests/integration/test_publishing.py` | create | contract/error/idempotency tests |

## Task 8: Implement the Knowledge Core HTTP contract adapter

### Intent

Create an anti-corruption adapter against the current Core API. It must never
import Core Python modules or database models and must retain candidates locally
if Core is down.

### Implementation Steps

1. Define `KnowledgeCorePort` with `get_ontology_snapshot`, `register_source`
   and `publish_observation`; include `schema_version`, correlation ID,
   idempotency key and configured role in the adapter contract.
2. Implement `KnowledgeCoreHttpAdapter` using `httpx.AsyncClient` with connect/
   read/write/pool timeouts, bounded retry for network/429/5xx, no retry for
   4xx validation/role errors, and stable mapping to `CORE_UNAVAILABLE`,
   `CORE_VALIDATION_FAILED`, `CORE_FORBIDDEN`, `CORE_CONFLICT`.
3. Map SourceDefinition/RawArtifact to Core `SourceCreate`; use canonical URL,
   checksum, publisher/trust metadata and artifact ID in `external_identifier`
   or `content_metadata`.
4. Map each validated candidate to Core `ObservationCreate`: subject candidate,
   property/relation candidate, typed value, evidence locator, confidence,
   ontology version and idempotency key. Rule/change candidates are carried in
   `raw_payload` with `candidate_kind`, DSL AST and extraction metadata; they do
   not call `/rules/{id}/activate` or any Core admin activation operation.
5. Treat Core response as acknowledgment only; persist Core IDs/status in local
   candidate rows. A Core review/proposal response remains `NEEDS_REVIEW`.
6. Add a compatibility probe that reads `/openapi.json` or performs documented
   endpoint checks and fails closed if required fields/statuses drift.

### Required Interfaces and Contracts

- Current Core paths: `GET /api/v1/ontology/versions/{id}` or configured active
  ontology lookup, `POST /api/v1/sources`, `POST /api/v1/observations`.
- Current mutation role: `X-Role: EDITOR` for source/observation; ingestion is
  never allowed to use `REVIEWER` for activation.
- Publish is one candidate per idempotency key; duplicate acknowledgment is a
  success with existing Core observation ID.
- No direct write endpoint for change candidates is assumed; raw payload is the
  compatibility envelope and docs must state this limitation.

### Error Handling and Logging

- Log Core host/path/status/latency/correlation and response code, never auth
  token, response body, source quote or raw candidate payload.
- Retryable Core errors set candidate/job retry state; non-retryable 4xx makes
  candidate `NEEDS_REVIEW` or `REJECTED` with local validation evidence.

### Tests

- `tests/unit/test_core_adapter.py`: exact payloads, role/header, retries,
  timeout, error mapping and no activation call.
- `tests/integration/test_publishing.py`: source registration + observation
  publication with httpx MockTransport, duplicate publish and outage recovery.
- `tests/contract/test_core_openapi.py`: load committed contract snapshot and
  assert current paths/request fields/statuses.
- `scripts/live_core_contract.py`: runnable against a local Core URL; no API key
  required when Core uses its documented local role seam.

### Acceptance Criteria

- All Core communication crosses one adapter and is mockable.
- Evidence and candidate kind survive the Core Observation `raw_payload`.
- Core outage does not delete local extraction/artifact.
- Live local Core smoke receives BMSTU candidate through the actual HTTP route.

### Verification

- `pytest -q tests/unit/test_core_adapter.py tests/integration/test_publishing.py tests/contract/test_core_openapi.py`
- `python scripts/live_core_contract.py --core-url http://127.0.0.1:18004`

## Task 9: Implement pipeline orchestration, jobs and API

### Intent

Provide thin, manually testable Swagger operations for every pipeline stage and
separate mutation/admin routes from read-only operational views.

### Implementation Steps

1. Implement `PipelineOrchestrator.run` as explicit stage calls with persisted
   transitions, injected ports and stage timing. Support `fixture` and `http`
   fetch modes, selected profile and optional artifact ID.
2. Implement `JobService` for run/retry/list/detail with idempotency and bounded
   attempts. A future worker can call the same application interface.
3. Add routers under `/api/v1`: `/sources`, `/artifacts`, `/discovery`,
   `/fetch`, `/extractions`, `/pipelines`, `/changes`, `/profiles`, `/jobs`.
4. Add typed request/response schemas with examples, enum descriptions,
   response models and `API_ERROR_RESPONSES` for 400/403/404/409/422/500.
5. Add role seam (`READER`, `EDITOR`, `REVIEWER`, `ADMIN`, `SYSTEM`): reads
   default to READER, source/profile/pipeline mutations require EDITOR, retry/
   publish require SYSTEM/EDITOR policy, and no route exposes rule activation.
6. Add pagination/limits, body-size middleware and safe URL validation at the
   inbound edge. Routes call application services only.

### Required Interfaces and Contracts

- `POST /api/v1/discovery/run` returns discovery run/items and correlation ID.
- `POST /api/v1/sources/{id}/fetch` returns artifact or `SKIPPED_UNCHANGED`.
- `POST /api/v1/artifacts/{id}/prepare`, `/extract` and `/pipelines/run` return
  typed stage/run projections.
- `GET /api/v1/extractions/{id}`, `GET /api/v1/artifacts/{id}`, `GET /api/v1/changes`.
- `POST /api/v1/jobs/{id}/retry` is idempotent and cannot retry a successful
  terminal job without an explicit conflict response.
- OpenAPI title/version/description state that candidates are not canonical
  knowledge and list all stable error codes.

### Error Handling and Logging

- Routes translate domain errors through one handler; no raw exception reaches
  client. Log route operation/correlation/entity IDs at INFO, validation fields
  at DEBUG, unexpected exceptions at ERROR.
- API responses never include raw artifact body or provider secret/prompt.

### Tests

- `tests/api/test_routes.py`: OpenAPI, schemas, role boundaries, all core routes.
- `tests/api/test_pipeline_api.py`: happy/invalid/duplicate/retry paths.
- Architecture test ensures route modules do not import SQLAlchemy repositories
  directly and application modules do not import FastAPI.

### Acceptance Criteria

- Swagger can execute source → fetch → prepare → extract → validate → publish
  demo flow with typed responses.
- Client cannot call Core activation or mutate Core tables through ingestion.
- Every route documents errors/examples and returns correlation ID on failures.

### Verification

- `pytest -q tests/api tests/architecture`
- Start app and inspect `/docs` manually or with `curl`/httpx.

## Phase Risks and Mitigations

- Risk: generic raw payload becomes an undocumented escape hatch. Mitigation:
  define candidate_kind schema, cap payload and document dedicated Core endpoint
  as a future compatibility improvement, without direct DB workaround.
- Risk: routes become orchestration code. Mitigation: route-size/import tests
  and application service composition root.

## Phase Completion Checklist

- Tasks 8-9 pass mocked and live Core contract evidence.
