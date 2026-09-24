# Архитектура: Explicit Modular Monolith

## Обзор

Andromeda Ingestion Platform использует Explicit Architecture внутри
модульного монолита. Стабильным центром являются domain contracts для source
definitions, raw artifacts, prepared documents, extraction candidates,
validation, change detection и pipeline state machine. FastAPI, PostgreSQL,
filesystem, HTTP, browser и AI providers — внешние детали, подключаемые через
ports.

Сервис намеренно остаётся одним deployable unit: orchestration, retries и
state transitions пока не требуют брокера или worker-кластера. Ports позволяют
вынести тяжёлый fetch/AI execution позже без изменения domain и Core contract.

## Структура

```text
src/andromeda_ingestion/
├── domain/
│   ├── common.py                 # IDs, time, confidence and shared values
│   ├── sources/                  # registry and discovery semantics
│   ├── artifacts/                # immutable raw evidence metadata
│   ├── preparation/              # prepared document and evidence fragments
│   ├── extraction/               # typed candidate contracts and profiles
│   ├── validation/               # deterministic candidate validation
│   ├── changes/                  # change classification and fingerprints
│   ├── pipelines/                # explicit state machine and failures
│   └── ports/                    # outbound interfaces only
├── application/
│   ├── discovery/
│   ├── fetching/
│   ├── preparation/
│   ├── extraction/
│   ├── validation/
│   ├── publishing/
│   ├── orchestration/
│   └── jobs/
├── infrastructure/
│   ├── config.py
│   ├── db/                       # SQLAlchemy models, session, repositories
│   ├── fetchers/                 # HTTP, file, API, browser adapters
│   ├── storage/                  # filesystem artifact adapter
│   ├── ai/                       # mock, Jev and provider-neutral adapters
│   ├── knowledge_core/           # HTTP contract adapter
│   └── observability/
├── presentation/api/             # thin FastAPI inbound adapter
└── main.py                       # composition root
alembic/                          # migration scripts
tests/                            # unit, integration, contract and E2E tests
fixtures/                         # immutable mock source documents/golden data
docs/                              # architecture, contracts and operations
```

## Dependency rules

Dependencies point inward:

```text
FastAPI presentation → application use cases → domain contracts/logic
Postgres/HTTP/AI/filesystem adapters ─────────→ domain ports
Composition root ────────────────────────────→ all concrete adapters
```

- Domain не импортирует FastAPI, Pydantic Settings, SQLAlchemy, httpx,
  Playwright, конкретный AI SDK или Knowledge Core ORM.
- Application не знает HTML selectors, PDF implementation details и provider
  SDK; оно вызывает deep ports.
- Routes не содержат orchestration, SQL или parsing; они валидируют input,
  вызывают use case и сериализуют typed result.
- Infrastructure adapters не экспортируются как межмодульные contracts.
- Source-specific code ограничен SourceDefinition/discovery/fetch adapter;
  semantic extraction выполняется через ExtractionProfile + AI port.
- Core интеграция использует только HTTP DTO с `schema_version`; shared DB и
  прямые table writes запрещены.

## Основные seams

- `SourceDiscoveryPort`: где искать документы.
- `HttpFetcherPort`, `BrowserFetcherPort`, `FileFetcherPort`,
  `ApiFetcherPort`: как получить bytes, без knowledge semantics.
- `ArtifactStoragePort`: где хранить immutable body.
- `DocumentPreparationPort`: как получить fragments/tables/links с locators.
- `DocumentUnderstandingPort` и extraction ports: как provider возвращает
  strictly typed, untrusted candidates.
- `EntityResolutionPort`: как сопоставить candidate с canonical identity.
- `KnowledgeCorePort`: как publish observation envelopes и получить ontology
  snapshot через versioned API.

Каждый seam имеет deterministic mock adapter и contract tests. Один adapter
может быть простым, но публичный interface должен оставаться небольшим и
глубоким: сложность retries, limits, security и mapping скрыта внутри adapter.

## Pipeline invariants

1. Каждый fetched body сначала записывается как immutable `RawArtifact` с
   checksum; identical checksum переводит pipeline в `SKIPPED_UNCHANGED`.
2. `PreparedDocument` сохраняет locator back to artifact; candidate evidence
   не может ссылаться только на свободный текст.
3. AI output — untrusted proposal; invalid schema, unknown concept и low
   confidence никогда не публикуются как canonical Fact/Rule.
4. Pipeline transitions persisted and auditable; retryable errors have bounded
   attempts and exponential backoff, permanent errors stop at `FAILED`.
5. Publish is idempotent by contract version, artifact/extraction fingerprint
   and observation natural identity.
6. Untrusted document content is delimited from system instructions; no AI
   output is executed as Python, shell, URL navigation or Core admin action.

## Persistence strategy

PostgreSQL хранит registry, artifact metadata, pipeline/job state, extraction
results, candidates, changes, profiles и audit events. Raw body хранится через
`ArtifactStoragePort`; development implementation — filesystem, production
может заменить его S3-compatible adapter. JSONB разрешён для raw metadata,
profile schemas, typed candidate payloads и provider diagnostics; identity,
state, checksum, version, retries, timestamps и queryable foreign keys — это
нормальные колонки с targeted indexes. Alembic — единственный production
schema path; startup не вызывает `create_all()`.

## Security and observability

Mutation/admin routes имеют explicit role seam (`READER`, `EDITOR`,
`REVIEWER`, `ADMIN`, `SYSTEM`) and are replaceable by host identity provider.
URL fetch is allowlisted, HTTPS-only by default, bounded by redirects/body/time
and protected from SSRF. Raw document text is data, not instructions. Logs use
correlation/job/artifact IDs and never include secrets, full raw bodies or
prompts with credentials. Metrics cover fetch, preparation, AI, validation,
publish, retry and review rates.

## Запрещённые паттерны

- parser-per-table architecture for semantic interpretation;
- direct Core database imports or shared PostgreSQL schema;
- arbitrary Python/eval/tool execution from AI output;
- automatic ontology/rule activation;
- treating source trust or AI confidence as canonical truth;
- unbounded retries, browser fallback for every URL or silent data loss;
- hidden global mutable state, god service and business logic in routes;
- Kafka/Redis/Neo4j/microservices without measured requirement.
