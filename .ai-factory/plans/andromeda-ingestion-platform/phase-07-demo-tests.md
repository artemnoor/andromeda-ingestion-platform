# Phase 7: Demo, evaluation and verification

Plan: [index.md](index.md)  
Tasks: 10-11  
Depends on: Phase 6 / Tasks 8-9

## Objective

Ship a repeatable BMSTU vertical slice and evidence that the architecture works
for unchanged/changed documents, unknown concepts, ambiguous rules, Core outage,
what is mock versus live, and provider replacement.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../andromeda-reference/backend/tests/fixtures/tracer/raw/source_manifest.json` | raw source manifest/hash pattern | Donor fixture integrity pattern |
| `../andromeda-reference/backend/tests/ingestion/test_bmstu_source_capture.py` | source capture scenarios | Donor BMSTU access cases to adapt, not copy parser architecture |
| `../max_test/tests/integration/test_acceptance.py` | Core end-to-end style | Align live Core smoke and evidence assertions |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `fixtures/bmstu/*`, `fixtures/golden/*` | create | small sanitized deterministic fixture set and expected output |
| `scripts/seed_demo.py`, `scripts/run_demo.py`, `scripts/evaluate_golden.py` | create | idempotent seed and runnable vertical slice/evaluation |
| `tests/fixtures.py`, `tests/e2e/test_bmstu_vertical_slice.py` | create | full pipeline scenarios |
| `tests/contract/test_core_openapi.py`, `scripts/live_core_contract.py` | create | actual Core contract check |
| `benchmarks/benchmark_ingestion.py` | create | synthetic pipeline stage measurements |

## Task 10: Add BMSTU fixtures, seed and demo commands

### Intent

Make the service understandable and manually runnable without network or paid
AI. Fixtures represent program, curriculum, admission/regulation, olympiad and
unknown/change cases while keeping evidence locators deterministic.

### Implementation Steps

1. Add `fixtures/bmstu/source_manifest.json` with SHA-256, official canonical
   URLs, content types, source kind and captured timestamps for sanitized HTML,
   JSON, text/PDF preparation samples and changed regulation variants.
2. Add `fixtures/golden/bmstu_program.expected.json`,
   `bmstu_regulation.expected.json` and `bmstu_changed.expected.json`; include
   exact property/relation/rule AST/evidence expectations.
3. Implement `seed_demo.py` to register BMSTU official source definitions and
   extraction profiles idempotently; no canonical Core facts are written by
   local seed.
4. Implement `run_demo.py` that runs BMSTU program and regulation pipelines
   using FixtureFetcher + MockAI + MockCore by default and prints IDs/states,
   candidates, evidence, changes and Core acknowledgments without raw bodies.
5. Add optional `--core-url` mode using `KnowledgeCoreHttpAdapter`; document
   which calls are mock and which are live.

### Required Interfaces and Contracts

- Manifest hash mismatch fails closed before AI.
- Demo output includes `source_id`, `artifact_id`, `extraction_id`, candidate
  statuses, `evidence.locator`, pipeline state and Core observation IDs.
- Seed is repeatable and uses natural keys/idempotency; it never silently
  replaces a profile version.

### Error Handling and Logging

- `ERROR` on fixture hash mismatch/path escape; `WARNING` on optional fixture
  gaps; `INFO` per stage/candidate counts; raw bodies never printed.

### Tests

- `tests/e2e/test_bmstu_vertical_slice.py`: program facts/relations, regulation
  rule DSL/evidence, unknown concept/review, changed threshold and idempotency.
- `tests/integration/test_seed.py`: seed twice yields same IDs/counts.

### Acceptance Criteria

- A clean local DB plus seed can demonstrate A-F from the Definition of Done.
- BMSTU can be replaced by a second source definition in a fixture-only test
  without editing the pipeline service.

### Verification

- `python scripts/seed_demo.py --database-url sqlite+aiosqlite:///./demo.db`
- `python scripts/run_demo.py --mode mock`
- Expected: `PUBLISHED` mock run, `SKIPPED_UNCHANGED` second run, `MODIFIED`
  change on changed regulation, review for unknown/ambiguous candidate.

## Task 11: Add the verification suite and benchmarks

### Intent

Prove behavior through the public seams, not only internal helper tests.

### Implementation Steps

1. Add unit coverage for contracts, checksum, preparation, validation, entity
   resolution, change detection, state transitions, Core adapter and security.
2. Add repository/API integration coverage on SQLite and migration check on
   disposable PostgreSQL when Docker is available.
3. Add E2E scenarios: unchanged zero AI, changed artifact, invalid AI no publish,
   low confidence review, unknown concept Core proposal/review, Core unavailable
   durable retry, duplicate retry, evidence chain and prompt injection.
4. Add property-based invariants with Hypothesis: same input same fingerprint,
   overlay/content does not mutate base artifact, illegal state transitions are
   rejected, candidate natural identity is stable.
5. Add live Core contract script/test that starts/uses actual Core HTTP API and
   records result; skip only when URL is not configured, never claim it passed.
6. Add benchmark over synthetic sources/artifacts/extractions measuring fetch
   policy, preparation, validation, change lookup and publish mapping, with
   median/p95 output.

### Required Interfaces and Contracts

- CI remains external-AI-free; live tests are opt-in with explicit URL.
- Test fixtures use the same public application ports as production wiring.
- Benchmark does not mutate a real Core or require network.

### Error Handling and Logging

- Tests assert safe logs for security cases and preserve correlation IDs.
- Benchmark logs only aggregate durations and counts.

### Tests

- `pytest -q` full suite; `ruff check`; `mypy`; `alembic check`.
- `pytest -q --hypothesis-show-statistics` for property tests.
- `python benchmarks/benchmark_ingestion.py --sources 10 --artifacts 100`.

### Acceptance Criteria

- Full suite passes with no AI key.
- Live Core smoke passes when local Core is running; otherwise output clearly
  says skipped/unavailable.
- Golden evaluation reports non-zero coverage and expected mock baseline.

### Verification

- `pytest -q`
- `ruff check src scripts tests alembic benchmarks`
- `mypy src`
- `alembic check`
- benchmark command above.

## Phase Risks and Mitigations

- Risk: mock tests hide provider differences. Mitigation: strict provider port,
  output contract tests and optional live adapter checks.
- Risk: fixture output is mistaken for live source evidence. Mitigation: every
  fixture metadata includes `fixture=true`, docs label mock/live explicitly.

## Phase Completion Checklist

- Tasks 10-11 have runnable commands and honest mock/live evidence.
