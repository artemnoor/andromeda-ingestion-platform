# Phase 1: Foundation and seams

Plan: [index.md](index.md)  
Tasks: 1-2  
Depends on: none

## Objective

Create a standalone Python/FastAPI project whose runtime, error, logging and
domain seams are usable before any persistence adapter is selected.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../max_test/src/andromeda_core/presentation/api/errors.py` | `error_payload`, exception handlers | Reuse the stable Core error envelope shape and trace ID semantics |
| `../max_test/src/andromeda_core/infrastructure/observability/http.py` | `CorrelationMiddleware` | Donor pattern for request correlation |
| `../andromeda-reference/backend/src/andromeda/ingestion/ports.py` | `SourceAdapter` | Old contract is too broad; split into deep new ports |
| `.ai-factory/ARCHITECTURE.md` | dependency rules | New service must remain independent from Core ORM and provider SDKs |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `pyproject.toml`, `.env.example`, `.gitignore`, `README.md` | create | pinned runtime/dev dependencies and local commands |
| `src/andromeda_ingestion/main.py` | create | composition root and lifespan |
| `src/andromeda_ingestion/infrastructure/config.py` | create | validated settings |
| `src/andromeda_ingestion/presentation/api/errors.py` | create | stable error envelope |
| `src/andromeda_ingestion/infrastructure/observability/*` | create | JSON logs, correlation IDs, Prometheus metrics |
| `alembic.ini`, `alembic/env.py`, `alembic/versions/` | create | migration bootstrap (schema in Task 3) |

## Task 1: Bootstrap the standalone service

### Intent

Provide a runnable ASGI app with documented configuration and observable
request boundaries. Later modules must be wired through this composition root,
not through module globals or route-level constructors.

### Implementation Steps

1. Create `Settings` with `app_env`, `app_name`, `log_level`, async
   `database_url`, `artifact_storage_root`, `knowledge_core_url`, optional
   `knowledge_core_token`, `api_docs_enabled`, CORS origins, request/body,
   fetch limits, retry limits, confidence thresholds and `role` settings.
2. Implement `create_app(settings, container=None)` with lifespan, health
   (`/health`, `/ready`) and `/metrics`; defer DB readiness check to the
   repository port.
3. Add middleware that normalizes `X-Correlation-ID`, records request duration,
   method/path/status and never logs request bodies, authorization headers or
   raw artifacts.
4. Add `DomainError` subclasses with stable codes/statuses and handlers for
   validation, upstream, conflict and unexpected errors. Return the Core-shaped
   `{error: {code, message, details, trace_id}}` envelope.
5. Keep route composition empty/minimal until Task 9; health and OpenAPI must
   work immediately.

### Required Interfaces and Contracts

- `Settings` is the only config source; environment names are mirrored in
  `.env.example`.
- `CorrelationMiddleware` stores a request ID in a context variable and passes
  it to application logs/metrics.
- `DomainError(code, message, details, status_code)` never exposes traceback or
  upstream response bodies to clients.
- `create_app` is deterministic and testable with injected repositories/adapters.

### Error Handling and Logging

- `DEBUG`: stage transitions and adapter names; safe IDs only.
- `INFO`: app start/stop and request completion over configured threshold.
- `WARNING`: rejected correlation IDs, disabled optional adapters and retryable
  boundaries.
- `ERROR`: unhandled exception with trace ID and exception type; no secrets,
  prompt contents or document body.

### Tests

- `tests/unit/test_config.py`: settings parsing and bounded values.
- `tests/api/test_health.py`: health/ready/metrics and OpenAPI availability.
- `tests/api/test_errors.py`: stable error payload and no internal leakage.
- `tests/unit/test_observability.py`: correlation propagation and safe fields.

### Acceptance Criteria

- `python -m uvicorn andromeda_ingestion.main:app` starts with SQLite defaults.
- `/docs`, `/openapi.json`, `/health`, `/ready`, `/metrics` respond with typed
  or documented payloads.
- A forced exception returns `INTERNAL_ERROR` with a trace ID and no traceback.

### Verification

- `pytest -q tests/unit tests/api/test_health.py tests/api/test_errors.py`
- Expected result: all foundation tests pass.

## Task 2: Define domain contracts and ports

### Intent

Define the smallest stable interfaces that decouple source access, evidence,
AI extraction and Core publishing. These contracts are the integration product;
SQL rows and provider payloads are implementations.

### Implementation Steps

1. Add `domain/common.py` enums for source categories/types, trust,
   confidence, pipeline states, job states, failure codes and change kinds.
2. Add typed Pydantic contracts under `domain/sources`, `artifacts`,
   `preparation`, `extraction`, `validation`, `changes` and `pipelines`.
3. Model `EvidenceLocator`/`EvidenceRef` with page/section/paragraph/table/
   row/selector/text range and artifact ID; reject evidence-free candidates.
4. Model `CandidateFact`, `CandidateRelation`, `CandidateRule`,
   `UnknownConceptCandidate`, `ChangeCandidate`, `ObservationCandidate` and
   `ExtractionResult` with `schema_version`, profile/provider metadata and
   strict `extra="forbid"` validation.
5. Add ports for discovery, four fetchers, artifact storage, preparation, all
   AI tasks, entity resolution, Core, repositories and clock/id generation.
6. Add pure state transition guard and natural identity/fingerprint helpers.

### Required Interfaces and Contracts

- `SourceDiscoveryPort.discover(source: SourceDefinition) -> list[DiscoveredItem]`.
- Fetch ports return `FetchedArtifact` bytes + safe response metadata and do not
  contain admission/program semantics.
- `ArtifactStoragePort.put/get/exists` uses a storage key and checksum.
- `DocumentUnderstandingPort.extract(context: ExtractionContext) -> ExtractionResult`;
  specialized ports may be composed by the router but share typed outputs.
- `KnowledgeCorePort.get_ontology_snapshot`, `register_source` and
  `publish_observation` are the only Core calls.
- Every external contract has `schema_version = "1.0"` in the first release.

### Error Handling and Logging

- Contract validation errors include field paths and stable `VALIDATION_FAILED`.
- State guards raise `INVALID_PIPELINE_TRANSITION` with current/target state.
- Fingerprinting logs only algorithm, lengths and digest prefixes.

### Tests

- `tests/unit/test_domain_contracts.py`: strict schemas, locator requirements,
  temporal intervals, confidence bounds and union round-trip.
- `tests/unit/test_pipeline_state.py`: legal transitions and rejection of
  publish-before-validation / retry-after-terminal combinations.
- `tests/unit/test_fingerprints.py`: stable ordering and same-input equality.

### Acceptance Criteria

- Domain package imports without importing FastAPI, SQLAlchemy, httpx,
  Playwright or any AI SDK.
- A candidate can be serialized/deserialized without losing evidence,
  schema/profile/provider metadata or `schema_version`.

### Verification

- `python -c "import ast, pathlib; ..."` boundary check for forbidden imports.
- `pytest -q tests/unit/test_domain_contracts.py tests/unit/test_pipeline_state.py tests/unit/test_fingerprints.py`

## Phase Risks and Mitigations

- Risk: contracts become a universal JSON blob. Mitigation: strict typed models,
  normal columns for identity/state and bounded extensible metadata only.
- Risk: one adapter leaks provider details into domain. Mitigation: import
  boundary test and MockAI through the same port.

## Phase Completion Checklist

- Tasks 1-2 satisfy their acceptance criteria.
- `index.md` checkboxes are updated after verification.
