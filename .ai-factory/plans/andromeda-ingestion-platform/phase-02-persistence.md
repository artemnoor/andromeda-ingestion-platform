# Phase 2: Persistence and immutable evidence

Plan: [index.md](index.md)  
Tasks: 3  
Depends on: Phase 1 / Tasks 1-2

## Objective

Persist ingestion metadata and lifecycle state in PostgreSQL while keeping raw
bytes behind a replaceable storage port. An empty database must reach a working
schema through Alembic only.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../max_test/alembic/versions/0001_core_knowledge.py` | FK/index/check style | Follow existing migration discipline without sharing tables |
| `../max_test/src/andromeda_core/infrastructure/db/session.py` | async engine normalization | Reuse async SQLite/PostgreSQL test approach conceptually |
| `../andromeda-reference/backend/src/andromeda/ingestion/contracts/raw.py` | `RawSourceSnapshot` hash/body semantics | Preserve immutable evidence and source locator invariants |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_ingestion/infrastructure/db/models.py` | create | normalized metadata tables and JSONB extension columns |
| `src/andromeda_ingestion/infrastructure/db/session.py` | create | async engine/session and migration URL normalization |
| `src/andromeda_ingestion/infrastructure/db/repositories/*.py` | create | source/artifact/profile/extraction/pipeline/job/change/audit adapters |
| `src/andromeda_ingestion/infrastructure/storage/filesystem.py` | create | checksum-addressed immutable local body storage |
| `alembic/versions/0001_ingestion_core.py` | create | tables, FKs, checks, unique keys and targeted indexes |
| `tests/integration/test_persistence.py` | create | migration/repository/storage behavior |

## Task 3: Implement metadata persistence and artifact storage

### Intent

Make ingestion restartable and auditable. Database records identify every
artifact/extraction/candidate/job; the body is recoverable from storage, not
silently lost when Core or AI is unavailable.

### Implementation Steps

1. Create tables `source_definitions`, `discovered_items`, `raw_artifacts`,
   `prepared_documents`, `extraction_profiles`, `extractions`,
   `extraction_candidates`, `pipeline_runs`, `jobs`, `change_candidates` and
   `audit_events` with UUID/string IDs, UTC timestamps, row versions and JSONB
   payload columns.
2. Add unique constraints for source stable key, discovery source+canonical URL,
   source+canonical URL+checksum, extraction artifact+profile+input fingerprint,
   candidate extraction+natural key, job idempotency key and change fingerprint.
3. Add indexes for pipeline state, jobs due for retry, artifact source/retrieved
   time, extraction status, candidates awaiting publish/review and change kind.
4. Implement `FilesystemArtifactStorage` writing to a temporary path then using
   atomic replace; storage key is a digest-derived path, and `get` verifies the
   stored bytes checksum before returning them.
5. Implement repository methods with optimistic `row_version` updates and
   idempotent upserts. Never expose SQLAlchemy models outside infrastructure.
6. Provide `create_engine`, `session_factory` and `get_session`; do not call
   `Base.metadata.create_all()` in startup.
7. Add migration downgrade for local/test rollback and migration check command.

### Required Interfaces and Contracts

- `RawArtifact` metadata includes requested/final URL, content type/status,
  checksum, etag/last-modified, storage key, byte size, previous artifact ID,
  version and `is_current`.
- Artifact identity is `(source_id, canonical_url, checksum)`; identical body
  returns existing row and does not overwrite stored bytes.
- `pipeline_runs` stores transition history, attempts, error code, correlation
  ID and idempotency key; no transition is implicit in a repository write.
- JSONB is limited to provider/raw/profile/candidate payloads; query-critical
  identity/state/timestamps are columns.

### Error Handling and Logging

- Duplicate natural identities return the existing domain object and emit
  `DEBUG` `idempotency_hit`.
- Checksum mismatch in storage raises `ARTIFACT_CHECKSUM_MISMATCH`, logs
  artifact ID/storage key/checksum prefixes, and never serves bytes.
- Optimistic update with stale row version returns `CONCURRENT_UPDATE`/409.
- Database exceptions are logged with operation/entity IDs but not SQL params
  containing document content or secrets.

### Tests

- `tests/integration/test_migrations.py`: upgrade from empty DB and downgrade.
- `tests/integration/test_persistence.py`: source/artifact/extraction/job
  round-trips, unique identities, row-version conflict and due retry query.
- `tests/unit/test_filesystem_storage.py`: atomic write, checksum verification,
  missing key and path traversal rejection.

### Acceptance Criteria

- `alembic upgrade head` on empty SQLite/PostgreSQL completes.
- Repeating an artifact insert with same source/url/checksum returns one row
  and one body.
- Raw body is recoverable after extraction failure and never included in API
  logs or Core payloads except evidence quotes bounded by policy.

### Verification

- `alembic check` with the test database URL.
- `pytest -q tests/integration/test_migrations.py tests/integration/test_persistence.py tests/unit/test_filesystem_storage.py`

## Phase Risks and Mitigations

- Risk: DB and filesystem become inconsistent. Mitigation: persist metadata only
  after verified storage write; orphan cleanup command reports, never deletes,
  unknown files automatically.
- Risk: concurrent retries duplicate candidates. Mitigation: unique keys plus
  optimistic row-version update and idempotency tests.

## Phase Completion Checklist

- Task 3 acceptance evidence exists and index checkbox is updated.
