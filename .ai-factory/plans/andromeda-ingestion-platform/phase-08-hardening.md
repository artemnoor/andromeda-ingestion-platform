# Phase 8: Production hardening and documentation

Plan: [index.md](index.md)  
Tasks: 12-13  
Depends on: Phase 7 / Tasks 10-11

## Objective

Make the standalone service operable by a new developer and safe to evolve:
Docker, CI, migrations, security boundaries, observability and documentation
must describe the actual implementation and its limitations.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../max_test/docker-compose.yml`, `Dockerfile` | local Postgres/migration flow | Donor local development pattern; adapt service-only compose |
| `../max_test/.github/workflows/ci.yml` | lint/type/test/migration gates | Donor CI quality gates |
| `../andromeda-reference/docs/ingestion-adapters.md` | operational ingestion docs | Donor source gap/provenance terminology |
| `.ai-factory/ARCHITECTURE.md` | security/observability rules | Hardening must preserve boundaries |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example` | create | app/Postgres/artifact storage local runtime |
| `.github/workflows/ci.yml` | create | lint/type/test/migration/security checks |
| `docs/*.md`, `docs/adr/*.md` | create | architecture, contracts, operations and decisions |
| `README.md` | modify | launch/demo/test/limitations and integration guide |
| `docs/security.md`, `docs/observability.md` | create | threat model, metrics and safe logging |
| `scripts/check_boundaries.py` | create | static no-direct-Core/AI/domain dependency check |

## Task 12: Add Docker, CI, security and operational hardening

### Intent

Provide clean startup and quality gates without claiming full production auth or
external AI readiness where the first release only has seams/mocks.

### Implementation Steps

1. Add non-root Dockerfile with pinned dependencies, healthcheck and command
   `alembic upgrade head && uvicorn ...`; no `create_all()`.
2. Add Compose Postgres + app + local artifact volume, health/readiness ordering,
   variable-based password and no committed secrets.
3. Add CI for Ruff, mypy, pytest, migration check, static import boundary and
   optional pip-audit; cache only dependencies, not secrets/artifacts.
4. Add security headers, bounded request body, CORS allowlist, role seam,
   SSRF/DNS/redirect policy, path traversal protection, prompt injection
   isolation, error redaction and idempotency/optimistic concurrency checks.
5. Add metrics for fetch duration/status, artifact unchanged count, preparation,
   AI duration/provider/error/token usage, validation review rate, publish
   result, retries and pipeline duration/state.
6. Document external AI keys as optional and keep MockAI default for CI/local.

### Required Interfaces and Contracts

- `.env.example` lists every setting; actual `.env` is ignored.
- Health is liveness-only; readiness checks DB and artifact storage, while Core
  availability is reported as dependency metric and does not lose local data.
- CI must pass without Docker Hub/external AI; PostgreSQL job can be service
  container when runner supports it.

### Error Handling and Logging

- Startup fails fast on invalid security limits/config, but Core outage does not
  prevent ingestion app from starting.
- JSON logs include `correlation_id`, `job_id`, `source_id`, `artifact_id`,
  `extraction_id`, stage and duration; redact `Authorization`, secrets, raw body,
  prompt and provider response.

### Tests

- `tests/security/test_security_boundaries.py`: imports, path traversal, URL
  policy, prompt injection, redaction, role boundary and request size.
- `docker compose config`; migration check; CI workflow YAML syntax.
- `pip-audit` if network/tool is available; report limitations honestly.

### Acceptance Criteria

- `cp .env.example .env; docker compose up --build` reaches healthy app and
  `/docs` after migrations (or Docker registry limitation is explicitly recorded).
- CI commands are reproducible locally and no secrets are required.

### Verification

- `docker compose config`
- `python scripts/check_boundaries.py`
- `pytest -q tests/security`

## Task 13: Complete documentation and final acceptance gates

### Intent

Give future contributors enough context to add a university/provider without
reading implementation internals, and close every required acceptance scenario.

### Implementation Steps

1. Write `docs/architecture.md`, `ingestion-pipeline.md`, `source-registry.md`,
   `extraction.md`, `ai-boundaries.md`, `core-integration.md`, `contracts.md`,
   `change-detection.md`, `security.md`, `observability.md`,
   `adding-a-university.md`, `adding-an-ai-provider.md`.
2. Add ADRs for PostgreSQL metadata + object storage seam, AI-first extraction,
   no shared Core DB, observation boundary, profile versioning, mock-first
   provider policy and modular monolith.
3. Add Mermaid diagrams for overall architecture, pipeline, AI boundary, Core
   publish, change/retry flow and failure states.
4. Update README with tree, endpoint matrix, environment, commands, BMSTU demo,
   Core integration payload, mock/live limitations and deployment notes.
5. Run final acceptance script that asserts A-H, records test/lint/type/migration/
   benchmark/live-Core results and fails on any unsupported claim.

### Required Interfaces and Contracts

- Docs state `schema_version`, current Core paths, role headers, error envelope,
  candidate-to-observation compatibility mapping and future dedicated endpoint
  need.
- REUSE/ADAPT/REIMPLEMENT/DROP matrix is present and references donor paths.
- Every command in README is runnable from clean checkout with documented env.

### Error Handling and Logging

- Documentation examples use redacted values and fixture URLs; no tokens or
  real user data.
- Final acceptance output distinguishes `PASS`, `SKIPPED_EXTERNAL`, and
  `FAILED`; skipped live AI/Core is not reported as passed.

### Tests

- `tests/docs/test_documentation_contract.py` checks required docs/diagrams,
  endpoint names and env variables.
- Full `pytest`, Ruff, mypy, Alembic, Docker config and acceptance script.

### Acceptance Criteria

- New developer can understand boundaries, add a source/provider/profile and run
  mock vertical slice from README.
- A reviewer can trace one candidate from source URL → raw artifact checksum →
  fragment locator → extraction/profile/provider → validation → Core observation.
- No TODO/pseudocode/empty adapter remains in production paths.

### Verification

- `python scripts/final_acceptance.py`
- `pytest -q && ruff check src scripts tests alembic benchmarks && mypy src && alembic check`

## Phase Risks and Mitigations

- Risk: docs drift from contracts. Mitigation: documentation contract test and
  OpenAPI snapshot check.
- Risk: Docker image cannot be pulled in a restricted environment. Mitigation:
  run all local checks, report the external limitation, and avoid claiming a
  successful image build without evidence.

## Phase Completion Checklist

- Tasks 12-13 complete only after commands and acceptance scenarios are run.
