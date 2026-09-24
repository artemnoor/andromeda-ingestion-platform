# Andromeda Ingestion Platform

Standalone evidence-first ingestion service for Andromeda Knowledge Core.

The service discovers documents, fetches and preserves immutable raw artifacts,
prepares locator-aware content, sends schema-guided data to a provider-neutral AI
port, validates typed candidates, detects changes, and publishes only
Observations through the Core API. It never writes Core tables, activates a
Rule/Ontology, or treats an AI response as canonical truth.

## Quick start

Requirements: Python 3.12+ for the supported runtime and Docker Desktop for the
PostgreSQL path. The current development shell used for verification also
supports Python 3.11 with the installed dependency set.

```powershell
Copy-Item .env.example .env
docker compose up --build
docker compose exec api python -m scripts.seed_demo
```

Open [Swagger UI](http://localhost:8010/docs), [OpenAPI](http://localhost:8010/openapi.json), [health](http://localhost:8010/health), or [metrics](http://localhost:8010/metrics).

The compose profile uses deterministic MockAI and an in-memory Core contract
double, so it is runnable without paid credentials. Set `APP_ENV=production`,
`MOCK_AI_ENABLED=false`, `AI_PROVIDER=http-json`, `AI_ENDPOINT`,
`AI_API_KEY`, and `KNOWLEDGE_CORE_URL` to use external adapters.

## Local verification

```powershell
$env:PYTHONPATH = "src;."
$env:DATABASE_URL = "sqlite+aiosqlite:///./var/local.db"
alembic upgrade head
python -m scripts.seed_demo
python -m scripts.run_demo
pytest -q
ruff check src tests alembic scripts
mypy src
python scripts/evaluate_golden.py
```

SQLite is a development/test adapter. PostgreSQL is the intended production
metadata store. The application does not call `create_all()` during startup;
the clean path is `alembic upgrade head`.

## Architecture boundary

```mermaid
flowchart LR
  Internet[Official web / PDF / API] --> Discovery[Source Registry + Discovery]
  Discovery --> Fetch[Bounded Fetch Layer]
  Fetch --> Raw[(Immutable Raw Artifact Storage)]
  Raw --> Prepare[Locator-aware Preparation]
  Prepare --> AI[Provider-neutral AI Extraction]
  AI --> Validate[Schema + Ontology + Confidence Validation]
  Validate --> Candidates[Evidence-backed Candidates]
  Candidates --> Core[Knowledge Core HTTP API]
  Core --> Semantic[Future Semantic clients]
```

The code is an Explicit Architecture modular monolith. Domain contracts and
ports point inward; FastAPI, SQLAlchemy, httpx, filesystem and AI SDKs are
adapters. There is no shared database with Knowledge Core.

## API groups

| Group | Purpose |
|---|---|
| `/api/v1/sources` | registry, discovery and source item fetch |
| `/api/v1/discovery` | explicit discovery runs |
| `/api/v1/artifacts` | immutable artifact metadata, preparation and extraction |
| `/api/v1/extractions` | typed result, candidates and validation |
| `/api/v1/pipelines` | restartable end-to-end state machine |
| `/api/v1/changes` | evidence-backed ADDED/MODIFIED/REMOVED candidates |
| `/api/v1/profiles` | versioned extraction profiles and prompt metadata |
| `/api/v1/jobs` | idempotent synchronous job facade and retry boundary |
| `/health`, `/ready`, `/metrics` | operations |

Mutating routes require `X-Role: EDITOR` (profile administration requires
`ADMIN`). This is a local replaceable identity boundary, not production
authentication. A host gateway should authenticate users and inject the role.

## Demo scenarios

The repeatable fixtures cover BMSTU program HTML, regulation PDF, unchanged
checksum, amended threshold `>=90` → `>=85`, unknown concepts, ambiguous dates,
and prompt-injection text inside HTML. The included MockAI is deterministic and
is not a claim about live model quality. Golden evaluation reports rule,
threshold, locator and unknown-concept accuracy.

## Repository map

```text
src/andromeda_ingestion/
  domain/             contracts, state policy, ports, closed DSL validator
  application/        use cases and orchestration
  infrastructure/     SQLAlchemy, storage, fetchers, profiles, AI/Core adapters
  presentation/api/   FastAPI routes, schemas and error envelope
alembic/              migration environment and versioned schema
fixtures/             sanitized deterministic BMSTU/golden fixtures
tests/                unit, API, integration, security and golden tests
docs/                 architecture, contracts, operations and ADRs
```

See [docs/architecture.md](docs/architecture.md) for the full design and
[docs/core-integration.md](docs/core-integration.md) for the exact existing
Knowledge Core compatibility mapping.

