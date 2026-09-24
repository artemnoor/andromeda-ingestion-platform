<!-- aif:plan-mode:ultra -->
# Ultra Implementation Plan: Andromeda Ingestion Platform

Mode: ultra  
Branch: none (standalone project directory is not initialized as git yet)  
Created: 2026-09-24

## Original Request

AI PLAN ULTRA.

Создать новый самостоятельный production-oriented сервис Andromeda Ingestion
Platform, который выполняет source discovery, fetch, immutable raw evidence
storage, content preparation, provider-neutral structured AI extraction,
validation, evidence-backed candidate formation, change detection и безопасную
публикацию в Andromeda Knowledge Core через стабильные versioned API contracts.
Сервис не должен превращать AI output в canonical truth, активировать Rules или
Ontology, иметь общий доступ к БД Core, зависеть от сайтов/парсеров/LLM в Core
или быть построен как набор parser-per-table algorithms. Нужны BMSTU vertical
slice, MockAI, golden evaluation, retries/idempotency, prompt-injection boundary,
FastAPI/Swagger, PostgreSQL/Alembic, Docker, tests, CI, observability и полная
документация. Перед реализацией изучить `artemnoor/andromeda` и
`artemnoor/andromeda-knowledge-core`, классифицировать старые компоненты как
REUSE/ADAPT/REIMPLEMENT/DROP и проверить интеграцию с реальным Core API.

## Settings

- Testing: yes
- Logging: verbose
- Docs: yes (mandatory completion checkpoint)
- Artifact language: ru with mixed technical terms
- Roadmap linkage: none; standalone service has no roadmap artifact yet

## Requirements Reconciliation

Authority: the current user request is the behavioral authority; the existing
Knowledge Core OpenAPI/routes are the integration contract; legacy Andromeda is
donor/reference evidence only and never overrides the new boundaries.

| Decision / supported combination | Source path and section | Verification evidence |
|---|---|---|
| Ingestion publishes Observation Candidates, never canonical Facts/Rules | Original Request §§2, 13, 22; Knowledge Core `src/andromeda_core/presentation/api/admin/knowledge.py` | E2E candidate remains unaccepted until Core workflow; no Core ORM import |
| Same source + same checksum skips AI and publish | Original Request §§7, 28, 45(C); old `docs/ingestion-adapters.md` | pipeline test asserts `SKIPPED_UNCHANGED` and zero AI calls |
| Changed artifact creates new extraction and change candidate | Original Request §§14, 45(D) | changed fixture E2E and persisted `MODIFIED` change |
| Low confidence/unknown concept is review-bound | Original Request §§12, 18, 45(E/F); Core `KnowledgeService.create_observation` | Core review/proposal contract test |
| Core interaction is HTTP-only and versioned | Original Request §§24-25; Core `/api/v1/sources`, `/api/v1/observations`, `X-Role` seam | mocked adapter contract tests plus live local Core smoke |
| HTTP fetch must be bounded and SSRF-safe | Original Request §37; donor `backend/src/andromeda/ingestion/fetch_policy.py` | private-IP, redirect, size, retry tests |
| AI receives schema/context separately from untrusted document data | Original Request §§11, 37; prompt-injection reference | malicious fixture cannot change profile/provider/tool behavior |
| BMSTU/HSE semantic parsers are not copied as the new architecture | Original Request §§3, 32; donor `backend/src/andromeda/ingestion/universities/*` | REUSE matrix in docs and architecture boundary test |

## Architecture and Decisions

- Use Explicit Architecture in a modular monolith; no Kafka, Redis, Neo4j or
  microservices in the first release.
- Keep domain contracts framework/provider independent. Pydantic is allowed for
  typed serializable contracts; SQLAlchemy/httpx/Playwright/AI SDKs stay outside.
- Persist source registry, artifact metadata, prepared/extraction metadata,
  candidate rows, changes and jobs in PostgreSQL. Raw bytes go through
  `ArtifactStoragePort`; filesystem is the development adapter.
- Use extraction profiles as versioned data. Provider routing is a small policy
  registry, not prompt strings embedded in application services.
- Map every candidate to Core's existing Observation envelope. Rule/relation/
  change candidates use typed `raw_payload` plus evidence until Core exposes a
  dedicated candidate endpoint; no direct DB fallback is permitted.
- Treat all AI results as untrusted. No eval, shell, URL navigation, config
  mutation, rule activation or ontology activation is available to AI adapters.
- Use explicit pipeline transition guards, bounded retries, idempotency keys,
  optimistic row versions and audit records.

## Donor Component Matrix

| Legacy area | Classification | New treatment |
|---|---|---|
| `andromeda.ingestion.contracts.raw.RawSourceSnapshot`, `SourceLocator`, source gaps | REUSE (concepts) | Re-express as new immutable artifact/evidence contracts; do not import legacy package |
| `andromeda.ingestion.fetch_policy` | ADAPT | Reimplement generic async bounded fetch policy with host allowlist and SSRF tests |
| `andromeda.ingestion.registry` | ADAPT | Keep registry idea, replace university factory with SourceDefinition + strategy registries |
| BMSTU/HSE `capture.py`, `source_metadata.py`, official host allowlists | ADAPT | Use as source-access evidence and seed definitions; keep access-specific adapters only |
| BMSTU/HSE `parser/*`, `normalizers/*`, `CanonicalSnapshot` | DROP for semantic meaning | Deterministic trivial extraction only; semantic extraction is profile + AI candidate output |
| legacy SQLAlchemy ingestion repositories and canonical projections | DROP | New metadata/state repositories; Core remains separate HTTP service |
| old provenance attribution/gap severity tests | ADAPT | Preserve locator/hash/gap principles in new evidence and validation tests |
| old Jev/provider calls | REIMPLEMENT behind `DocumentUnderstandingPort` and router | Mock is default; provider SDK never enters domain/application |
| old fixture manifests/raw bodies | REUSE as donor evidence where license/source policy allows | Copy only small sanitized BMSTU fixtures and record fixture provenance |

## Phase Index

1. [Phase 1: Foundation and seams](phase-01-foundation.md) — Tasks 1-2
2. [Phase 2: Persistence and immutable evidence](phase-02-persistence.md) — Task 3
3. [Phase 3: Source registry, discovery and fetch](phase-03-source-fetch.md) — Task 4
4. [Phase 4: Preparation, profiles and AI extraction](phase-04-extraction.md) — Task 5
5. [Phase 5: Validation, changes and pipeline state](phase-05-validation-pipeline.md) — Tasks 6-7
6. [Phase 6: Knowledge Core integration and API](phase-06-core-api.md) — Tasks 8-9
7. [Phase 7: Demo, evaluation and verification](phase-07-demo-tests.md) — Tasks 10-11
8. [Phase 8: Production hardening and documentation](phase-08-hardening.md) — Tasks 12-13

## Cross-Phase Dependencies

- Task 2 depends on Task 1 because domain contracts and ports use the shared
  settings/error/observability conventions.
- Task 3 depends on Tasks 1-2 because SQLAlchemy rows implement the domain
  persistence ports and migrations must encode their lifecycle invariants.
- Task 4 depends on Tasks 2-3 because discovery/fetch writes source/artifact
  metadata and storage keys.
- Task 5 depends on Tasks 2-4 because preparation/extraction consumes artifacts,
  profiles and source-specific context.
- Task 6 depends on Tasks 2 and 5; Task 7 depends on Tasks 3 and 6.
- Task 8 depends on Tasks 2, 3, 6 and 7; Task 9 depends on Tasks 3-8.
- Task 10 depends on all previous runtime tasks; Task 11 verifies Tasks 4-10.
- Tasks 12-13 depend on all implementation tasks and close operational gates.

## Tasks

### Phase 1: Foundation and seams

- [x] Task 1: Bootstrap standalone FastAPI service, configuration, error envelope and observability ([details](phase-01-foundation.md#task-1-bootstrap-the-standalone-service))
- [x] Task 2: Define domain contracts, candidate model, pipeline states and ports ([details](phase-01-foundation.md#task-2-define-domain-contracts-and-ports)) (depends on 1)

### Phase 2: Persistence and immutable evidence

- [x] Task 3: Implement PostgreSQL metadata persistence, Alembic migrations and filesystem artifact storage ([details](phase-02-persistence.md#task-3-implement-metadata-persistence-and-artifact-storage)) (depends on 1, 2)

### Phase 3: Source registry, discovery and fetch

- [x] Task 4: Implement generic source registry/discovery/fetch layer and BMSTU source definitions ([details](phase-03-source-fetch.md#task-4-implement-source-registry-discovery-fetch-and-bmstu-definitions)) (depends on 2, 3)

### Phase 4: Preparation, profiles and AI extraction

- [x] Task 5: Implement content preparation, versioned extraction profiles, provider router and deterministic MockAI ([details](phase-04-extraction.md#task-5-implement-preparation-profiles-provider-router-and-mockai)) (depends on 2, 4)

### Phase 5: Validation, changes and pipeline state

- [x] Task 6: Implement candidate validation, entity resolution, evidence policy and golden evaluation ([details](phase-05-validation-pipeline.md#task-6-implement-validation-entity-resolution-evidence-policy-and-golden-evaluation)) (depends on 2, 5)
- [x] Task 7: Implement change detection, explicit pipeline state machine, retries and idempotency ([details](phase-05-validation-pipeline.md#task-7-implement-change-detection-pipeline-state-machine-retries-and-idempotency)) (depends on 3, 6)

### Phase 6: Knowledge Core integration and API

- [x] Task 8: Implement versioned KnowledgeCorePort HTTP adapter and safe candidate publishing ([details](phase-06-core-api.md#task-8-implement-the-knowledge-core-http-contract-adapter)) (depends on 2, 3, 6, 7)
- [x] Task 9: Implement application orchestration, jobs and complete FastAPI/Swagger API ([details](phase-06-core-api.md#task-9-implement-pipeline-orchestration-jobs-and-api)) (depends on 3-8)

### Phase 7: Demo, evaluation and verification

- [x] Task 10: Add BMSTU fixtures, repeatable seed and runnable demo commands ([details](phase-07-demo-tests.md#task-10-add-bmstu-fixtures-seed-and-demo-commands)) (depends on 4, 5, 8, 9)
- [x] Task 11: Add unit, integration, API, contract, E2E, live-Core and benchmark verification ([details](phase-07-demo-tests.md#task-11-add-the-verification-suite-and-benchmarks)) (depends on 1-10)

### Phase 8: Production hardening and documentation

- [x] Task 12: Add Docker Compose, CI, security gates and operational configuration ([details](phase-08-hardening.md#task-12-add-docker-ci-security-and-operational-hardening)) (depends on 1-11)
- [x] Task 13: Complete architecture/contracts/operations documentation and final acceptance gates ([details](phase-08-hardening.md#task-13-complete-documentation-and-final-acceptance-gates)) (depends on 1-12)

## Commit Plan

- **Commit 1** (after Tasks 1-2): `feat: establish ingestion domain contracts and application seams`
- **Commit 2** (after Task 3): `feat: add ingestion metadata persistence and artifact storage`
- **Commit 3** (after Tasks 4-5): `feat: add source fetch and provider-neutral extraction pipeline`
- **Commit 4** (after Tasks 6-7): `feat: add validation change detection and restartable jobs`
- **Commit 5** (after Tasks 8-9): `feat: integrate Knowledge Core and expose ingestion API`
- **Commit 6** (after Tasks 10-11): `test: prove BMSTU vertical slice and Core contract`
- **Commit 7** (after Tasks 12-13): `docs: harden and document production operations`

## Definition of Done

- Empty PostgreSQL database reaches head through Alembic and starts without
  `create_all()`.
- Swagger documents typed source/artifact/discovery/fetch/extraction/pipeline/
  change/profile/job routes and stable error envelopes.
- BMSTU fixture pipeline produces immutable artifact, prepared locators,
  schema-validated candidates and Core Observation publication via HTTP.
- Same checksum performs zero AI calls; changed content creates a new artifact,
  extraction and `MODIFIED` change candidate.
- Invalid AI output, low confidence, unknown concept, Core outage, duplicate
  retry and prompt injection each have automated evidence.
- No new university requires changes to orchestration, Core contract or Rule
  Engine; only definitions/adapters/profiles differ.
- `ruff`, `mypy`, migration check, tests, Docker config validation and local
  Core contract smoke pass, with external AI explicitly optional.

## Verification record

- `pytest -q`: 13 passed; only dependency deprecation warnings remain.
- `ruff check src tests scripts alembic benchmarks`: passed.
- `mypy src`: passed for 97 source files.
- `alembic upgrade head` and `alembic check`: passed on a clean SQLite
  development database; PostgreSQL schema is represented by the same Alembic
  metadata and Compose configuration.
- MockAI BMSTU program/regulation demo: published candidate observations,
  unchanged checksum skip, amended rule change, unknown concept review and
  ambiguous rule review all passed.
- Real local Knowledge Core HTTP smoke: ontology read, source registration and
  observation publication returned 2xx; Core correctly retained the result as
  review-bound.
- Golden evaluation: rule, threshold, evidence locator and unknown-concept
  metrics were 1.0 for the included fixtures.
- Docker Compose config validation passed. Image build was attempted but the
  local Docker proxy could not reach Docker Hub to pull `python:3.12-slim`.
