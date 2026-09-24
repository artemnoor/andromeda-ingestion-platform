# Andromeda Ingestion Platform

## Назначение

Andromeda Ingestion Platform — самостоятельный модульный backend для discovery,
fetch, immutable evidence storage, content preparation, provider-neutral AI
extraction, validation, change detection и безопасной публикации typed
Observation Candidates в Andromeda Knowledge Core.

Сервис добывает и интерпретирует документы, но не принимает нормативные
решения. Knowledge Core остаётся единственным владельцем canonical Facts,
Ontology, Rules и Derived Knowledge.

## Технологии

- Python 3.12+;
- FastAPI и Pydantic v2;
- SQLAlchemy 2.x async и PostgreSQL;
- Alembic;
- pytest, pytest-asyncio, Hypothesis;
- httpx и optional Playwright adapter;
- filesystem ArtifactStorage для development, S3-compatible seam для future;
- Ruff, mypy и CI quality gates;
- structured JSON logging, correlation IDs и Prometheus metrics;
- Docker Compose.

## Архитектура

Модульный monolith с Explicit Architecture и ports/adapters. Domain layer не
зависит от FastAPI, SQLAlchemy, сети, файловой системы или AI SDK. Application
use cases оркестрируют pipeline. Infrastructure реализует persistence,
fetchers, artifact storage, AI adapters и Knowledge Core HTTP adapter.

Подробные правила находятся в `.ai-factory/ARCHITECTURE.md`.

## Границы ответственности

- Ingestion сохраняет raw artifacts immutable и не превращает AI output в Truth.
- AI output всегда проходит schema, ontology, type, temporal, evidence и
  confidence validation.
- Core вызывается только через versioned HTTP contracts; shared database и
  импорт Core ORM запрещены.
- Документ трактуется как untrusted data: prompt injection не может менять
  instructions, конфигурацию или выполнять tool calls.
- Повторный fetch/extraction/publish идемпотентен и воспроизводим.
- Любое publish failure сохраняет extraction и job state для retry.
