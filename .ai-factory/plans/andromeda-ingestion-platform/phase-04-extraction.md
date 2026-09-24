# Phase 4: Preparation, profiles and AI extraction

Plan: [index.md](index.md)  
Tasks: 5  
Depends on: Phase 3 / Task 4

## Objective

Transform immutable artifacts into evidence-located prepared content and typed,
provider-neutral extraction results. Deterministic parsing is used only for
trivial structured formats; semantic meaning is profile-guided AI output.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../andromeda-reference/backend/src/andromeda/ingestion/contracts/raw.py` | `SourceLocator`, typed raw records | Locator fields and strict values are useful donor invariants |
| `../andromeda-reference/backend/src/andromeda/ingestion/universities/hse/parser/*.py` | table/document parsing | Explicitly classified DROP for semantic architecture, retained as donor edge cases |
| `../max_test/src/andromeda_core/presentation/api/schemas.py` | `ObservationCreate`, `RuleCreate` | Extraction context must align with Core ontology/rule payload shapes |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_ingestion/application/preparation/service.py` | create | content type dispatch and persistence |
| `src/andromeda_ingestion/infrastructure/preparation/*.py` | create | HTML/PDF/JSON/CSV/plain text adapters |
| `src/andromeda_ingestion/application/extraction/service.py` | create | profile lookup, router, result persistence |
| `src/andromeda_ingestion/domain/extraction/profiles.py` | create | profile contracts and versions |
| `src/andromeda_ingestion/infrastructure/ai/*.py` | create | provider router, deterministic, mock, Jev seam |
| `tests/unit/test_preparation.py`, `tests/unit/test_ai_boundary.py` | create | locators, profiles, prompt injection |

## Task 5: Implement preparation, profiles, provider router and MockAI

### Intent

Make AI extraction replaceable and reproducible. The adapter sees a schema-
guided `ExtractionContext`, not an unbounded prompt string; documents remain
untrusted data inside a delimited content field.

### Implementation Steps

1. Implement `HtmlPreparer` with BeautifulSoup-safe text extraction, headings,
   links and tables; every chunk has `artifact_id`, source URL, selector and
   character range. Strip control chars and cap per-chunk/total content.
2. Implement `PdfPreparer` with pypdf page extraction and page/line locators;
   on encrypted/malformed PDF return `PREPARATION_FAILED` with bounded metadata.
3. Implement JSON/CSV/plain-text preparers that retain JSON path/row/column
   evidence and reject oversized nesting/rows. No arbitrary template execution.
4. Persist `PreparedDocument` with `preparation_version`, structural hints,
   chunks, tables and content fingerprint; unchanged prepared input is reused.
5. Define versioned `ExtractionProfile` data for `bmstu_program`, `curriculum`,
   `admission_rules`, `individual_achievements`, `olympiads`, `tuition`,
   `admission_statistics`, `regulatory_document` and `news_change`.
6. Implement `AIProviderRouter` selecting deterministic/mock/Jev/LLM by profile
   strategy and provider availability. The first release uses deterministic
   structured JSON and MockAI; generic adapters return the same contract.
7. Implement `MockAIAdapter` keyed by fixture/profile/fingerprint. It returns
   CandidateFact/Relation/Rule/UnknownConcept/Change data with exact evidence,
   including a changed regulation and prompt-injection fixture.
8. Persist `ExtractionResult` and candidate rows with input/output fingerprints,
   provider/model/profile/prompt version, duration/token usage/cost metadata,
   warnings and raw provider response only when explicitly configured for safe
   test mode (never production logs).

### Required Interfaces and Contracts

- `PreparedDocument` contains sections, tables, links, chunks and
  `structural_hints`; all fragments carry an `EvidenceLocator`.
- `ExtractionContext` contains an ontology snapshot, profile output schema and
  trusted instructions separately from `<document_data>` chunks.
- `ExtractionResult` is strict Pydantic JSON; unknown keys are rejected before
  persistence. No provider may return executable code/tool calls.
- Prompt/version metadata is persisted for reproducibility; secrets and full
  prompts are not logged.

### Error Handling and Logging

- `PREPARATION_FAILED`, `AI_TIMEOUT`, `AI_RATE_LIMIT`, `AI_INVALID_OUTPUT` and
  `AI_PROVIDER_UNAVAILABLE` are stable codes; only retryable classes schedule
  retries.
- `DEBUG`: profile/provider selection and chunk counts; `INFO`: extraction
  completion/duration/fingerprint; `WARNING`: truncation, fallback and
  provider validation warnings; `ERROR`: exception type and IDs only.
- Document content is never interpolated into system instructions; raw content
  is bounded, delimited and labelled untrusted.

### Tests

- `tests/unit/test_preparation.py`: HTML/PDF/JSON/CSV locators, truncation,
  malformed input and control character stripping.
- `tests/unit/test_profiles.py`: versioned schemas and profile selection.
- `tests/unit/test_ai_boundary.py`: MockAI output validation, malicious source
  text, no tool/shell/config side effects, provider replacement through port.
- `tests/integration/test_extraction.py`: artifact → prepared document →
  profile/router/MockAI → persisted extraction/candidates.

### Acceptance Criteria

- BMSTU program page produces typed candidates with source selectors/paths.
- BMSTU regulation fixture produces a `CandidateRule` with Rule DSL AST,
  document title/issuer/effective-date evidence and no executable code.
- A document saying “ignore previous instructions” changes neither profile,
  provider, config nor persistence behavior.
- Replacing MockAI with another adapter requires composition-root wiring only.

### Verification

- `pytest -q tests/unit/test_preparation.py tests/unit/test_profiles.py tests/unit/test_ai_boundary.py tests/integration/test_extraction.py`
- `python scripts/evaluate_golden.py` reports metrics for entities/facts/
  relations/rules/evidence/unknown concepts/change detection.

## Phase Risks and Mitigations

- Risk: LLM output is syntactically valid but semantically unsafe. Mitigation:
  strict contract + later ontology/type/evidence/confidence validation; never
  publish directly.
- Risk: PDF/HTML preprocessing loses provenance. Mitigation: every chunk must
  carry locator and tests assert round-trip to artifact.

## Phase Completion Checklist

- Task 5 passes mock/golden tests and stores reproducibility metadata.
