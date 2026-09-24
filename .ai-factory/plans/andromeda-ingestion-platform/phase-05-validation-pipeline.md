# Phase 5: Validation, changes and pipeline state

Plan: [index.md](index.md)  
Tasks: 6-7  
Depends on: Phase 4 / Task 5; Task 7 also depends on Phase 2 / Task 3

## Objective

Turn untrusted extraction into validated Observation Candidates and durable
change/job state without claiming canonical truth. Make runs restartable,
bounded and explainable.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../max_test/src/andromeda_core/application/knowledge_service.py` | observation status/proposal logic | Core decides acceptance; ingestion must stop at observation boundary |
| `../max_test/src/andromeda_core/application/change_service.py` | change classification | Align candidate kinds with Core change vocabulary |
| `../andromeda-reference/backend/src/andromeda/ingestion/contracts/source.py` | gap severity | Low-confidence/ambiguous source states must remain visible |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_ingestion/application/validation/service.py` | create | ordered validators and review policy |
| `src/andromeda_ingestion/domain/validation/*.py` | create | typed validation reports and policies |
| `src/andromeda_ingestion/infrastructure/identity/*.py` | create | deterministic alias resolver and provider seam |
| `src/andromeda_ingestion/application/changes/service.py` | create | compare extraction candidates and persist changes |
| `src/andromeda_ingestion/application/orchestration/service.py` | create | explicit state machine and stage execution |
| `src/andromeda_ingestion/application/jobs/service.py` | create | bounded retry scheduling |
| `tests/unit/test_validation.py`, `tests/unit/test_change_detection.py` | create | negative/edge tests |
| `tests/integration/test_pipeline_state.py` | create | restart/failure/idempotency behavior |

## Task 6: Implement validation, entity resolution, evidence policy and golden evaluation

### Intent

Validate in a fixed order: schema → ontology → type → reference/entity
resolution → temporal → evidence → confidence. Failed/ambiguous output is
reviewable data, never silently discarded or accepted.

### Implementation Steps

1. Implement `ValidationReport` with per-candidate errors/warnings, status,
   stable codes and `review_required`.
2. Validate candidate property/relation/rule shapes against a supplied ontology
   snapshot; unknown concepts become `UnknownConceptCandidate` and route to
   review rather than creating definitions.
3. Validate typed values, date/effective intervals, source document metadata,
   evidence artifact IDs/locators and bounded quotes. Regulatory documents
   require title/issuer/number/publication/effective metadata; ambiguous
   effective date yields `NEEDS_REVIEW`.
4. Implement `DeterministicEntityResolver` aliases for BMSTU/HSE examples and
   `EntityResolutionPort` for Jev/AI/Core lookup; retain confidence and
   alternatives instead of selecting a low-confidence duplicate.
5. Apply configurable thresholds per candidate kind/property. Confidence is
   per candidate, not per document; low score or conflicting evidence is review.
6. Build golden evaluator comparing fixture expectations and report precision/
   recall-style counts for entity/fact/relation/rule/evidence/unknown/change.

### Required Interfaces and Contracts

- Validated candidates carry `validation_status` (`VALIDATED`, `NEEDS_REVIEW`,
  `REJECTED`) and a report; original extraction remains immutable.
- Validation cannot call Core admin actions or activate rules.
- Entity resolution result includes canonical key, candidate type, confidence,
  match method and alternatives.

### Error Handling and Logging

- Errors: `ONTOLOGY_MISMATCH`, `WRONG_PROPERTY_TYPE`, `INVALID_REFERENCE`,
  `INVALID_TEMPORAL_INTERVAL`, `MISSING_EVIDENCE`, `LOW_CONFIDENCE`,
  `UNKNOWN_CONCEPT`, `AMBIGUOUS_EXTRACTION`.
- `INFO` logs report counts/status; `WARNING` logs review reasons; `ERROR`
  logs only unexpected validator failures. Never log candidate quotes by default.

### Tests

- `tests/unit/test_validation.py`: each ordered validator and combined failure
  precedence; unknown concept, invalid date, no evidence, low confidence.
- `tests/unit/test_entity_resolution.py`: aliases, ambiguity and no duplicate.
- `tests/unit/test_golden_evaluation.py`: known expected outputs and metric
  calculation.

### Acceptance Criteria

- Invalid output never reaches publisher.
- `RegionalEducationalCoefficient` becomes unknown concept + review payload,
  not a new property.
- An ambiguous regulatory effective date is review-bound and preserves evidence.

### Verification

- `pytest -q tests/unit/test_validation.py tests/unit/test_entity_resolution.py tests/unit/test_golden_evaluation.py`

## Task 7: Implement change detection, pipeline state machine, retries and idempotency

### Intent

Make every pipeline stage explicit and resumable. Same input is a no-op; changed
input is a new artifact/extraction and produces a typed diff candidate.

### Implementation Steps

1. Implement `ChangeDetectionService` comparing previous/current extraction
   candidate natural keys and canonical JSON fingerprints; emit ADDED,
   MODIFIED, REMOVED, POSSIBLY_REPLACED or AMBIGUOUS with evidence.
2. Implement transition table for `DISCOVERED → FETCHING → FETCHED → PREPARING
   → PREPARED → EXTRACTING → EXTRACTED → VALIDATING → VALIDATED → PUBLISHING →
   PUBLISHED`, plus `NEEDS_REVIEW`, `FAILED`, `RETRYABLE`, `SKIPPED_UNCHANGED`.
3. Persist every transition with actor/stage/timestamp/correlation/job IDs and
   reject illegal transitions. Terminal `PUBLISHED` and `SKIPPED_UNCHANGED`
   are idempotent reads.
4. Classify failure codes into retryable/non-retryable; schedule exponential
   backoff with max attempts, jitter-free deterministic tests and explicit
   `POST /jobs/{id}/retry` reset guard.
5. Use idempotency keys at source discovery, fetch pipeline, extraction and
   publish. Concurrent workers update row version conditionally and return 409
   on lost update.

### Required Interfaces and Contracts

- Pipeline command contains source/profile/idempotency/correlation and optional
  artifact override; result exposes state, artifact, extraction, changes, jobs.
- A Core outage preserves validated extraction/candidates and state `RETRYABLE`;
  it must not roll back immutable evidence.
- A changed artifact links `previous_artifact_id`; unchanged artifact does not
  invoke preparation/AI/publish.

### Error Handling and Logging

- Stage failures log `pipeline_stage_failed` with job/artifact/stage/code,
  attempt and `retryable`; no body or prompt.
- `DEBUG` transition guards; `INFO` terminal state; `WARNING` retry scheduling;
  `ERROR` exhausted failure.

### Tests

- `tests/unit/test_change_detection.py`: add/modify/remove/replaced/ambiguous
  and deterministic fingerprints.
- `tests/unit/test_pipeline_state.py`: all legal/illegal transitions.
- `tests/integration/test_pipeline_state.py`: same checksum zero AI calls,
  changed artifact, invalid AI, Core outage, retry duplicate prevention and
  optimistic concurrent update.

### Acceptance Criteria

- Pipeline can resume after each persisted stage boundary.
- Retry is bounded and does not create duplicate artifact/extraction/candidate.
- Changed admission rule produces a `MODIFIED` candidate with old/new evidence.

### Verification

- `pytest -q tests/unit/test_change_detection.py tests/integration/test_pipeline_state.py`

## Phase Risks and Mitigations

- Risk: partial publish leads to lost candidates. Mitigation: candidate rows and
  Core idempotency are persisted separately; retry only unpublished candidates.
- Risk: removal is inferred from partial document. Mitigation: emit
  `AMBIGUOUS` unless profile declares complete snapshot semantics.

## Phase Completion Checklist

- Tasks 6-7 have executable negative and restartability evidence.
