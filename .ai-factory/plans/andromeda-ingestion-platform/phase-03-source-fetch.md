# Phase 3: Source registry, discovery and fetch

Plan: [index.md](index.md)  
Tasks: 4  
Depends on: Phase 2 / Task 3

## Objective

Separate the question “where to look” from “how to get bytes”. Implement a
generic registry/discovery/fetch layer and a BMSTU definition whose university
knowledge is configuration/access metadata, not semantic parser logic.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `../andromeda-reference/backend/src/andromeda/ingestion/registry.py` | `UniversityAdapterSpec` | Reuse registry concept, remove direct adapter parsing from orchestration |
| `../andromeda-reference/backend/src/andromeda/ingestion/fetch_policy.py` | `FetchPolicy`, `validate_source_url`, redirects/retries | Donor for SSRF and bounded network behavior |
| `../andromeda-reference/backend/src/andromeda/ingestion/universities/bmstu/capture.py` | official BMSTU URLs and fixture manifest | Source metadata donor, not a semantic parser contract |
| `../andromeda-reference/docs/ingestion-adapters.md` | source gaps and snapshots | Preserve typed gaps and immutable provenance |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_ingestion/application/sources/service.py` | create | register/list/update source definitions |
| `src/andromeda_ingestion/application/discovery/service.py` | create | strategy dispatch and discovered item persistence |
| `src/andromeda_ingestion/application/fetching/service.py` | create | fetch, checksum, artifact versioning and dedup |
| `src/andromeda_ingestion/infrastructure/fetchers/*.py` | create | HTTP/API/file/browser fixture adapters |
| `src/andromeda_ingestion/infrastructure/sources/*.py` | create | static/sitemap/link/API discovery adapters and BMSTU definitions |
| `src/andromeda_ingestion/domain/ports/` | modify | concrete port signatures and fetch policy values |
| `tests/unit/test_fetch_security.py`, `tests/integration/test_source_fetch.py` | create | policy and persistence scenarios |

## Task 4: Implement source registry, discovery, fetch and BMSTU definitions

### Intent

Make new university/source support a data and access-adapter change. Fetchers
return bounded bytes and metadata only; discovery returns candidate URLs and
never publishes knowledge.

### Implementation Steps

1. Implement `SourceRegistryService` using `SourceRepositoryPort`; validate
   category/type/strategy combinations, HTTPS and allowed host metadata.
2. Implement `StaticUrlDiscovery`, `SitemapDiscovery`, `HtmlLinkDiscovery`
   and `ApiDiscovery`; cap links/items, canonicalize URLs and deduplicate by
   source+URL. AI-assisted discovery remains a typed port with Mock adapter,
   never a silent automatic trust decision.
3. Implement `SafeHttpFetcher` with HTTPS default, adapter-owned host allowlist,
   DNS resolution rejecting loopback/private/link-local/reserved targets,
   bounded redirects, body size, total time budget, retryable status classes,
   Retry-After cap and safe URL logging.
4. Implement `ApiFetcher`, `FileFetcher`, `FixtureFetcher` and an optional
   `BrowserFetcher` adapter. Browser adapter is lazy/optional and uses the same
   host/redirect/body limits; no browser dependency is imported at module load.
5. Implement `FetchService.fetch_item`: create artifact only after successful
   body hash/storage, link `previous_artifact_id` on changed content, mark
   unchanged item and emit audit/metrics.
6. Add `infrastructure/sources/bmstu.py` with official BMSTU source definitions
   for program catalog, curriculum and admission/regulation documents. Include
   access host allowlist and discovery URLs; do not add score/bonus business
   methods or table-specific semantic parsers.
7. Preserve source gaps/rejected URLs as typed diagnostics and make discovery
   restartable by idempotency key.

### Required Interfaces and Contracts

- `SourceDefinition` supports UNIVERSITY/MINISTRY/GOVERNMENT/
  OLYMPIAD_ORGANIZER/REGULATOR/OTHER_OFFICIAL_SOURCE.
- `FetchedArtifact` contains bytes only at application boundary and safe
  metadata: requested/final URL, status, content type, headers, redirects,
  elapsed time, error class and truncation flag.
- No fetcher accepts `Program`, `AdmissionRule`, `Fact` or `Rule` types.
- Host allowlists are per source definition; global policy rejects private DNS
  even when hostname is allowed.

### Error Handling and Logging

- Errors classify as `FETCH_FAILED`, `FETCH_TIMEOUT`, `FETCH_RATE_LIMIT`,
  `FETCH_SSRF_REJECTED`, `FETCH_BODY_TOO_LARGE`, `DISCOVERY_FAILED`.
- Retryable errors update job attempt/backoff; permanent URL/policy errors stop
  without retry. Log source ID, URL host, attempt, status and error code, never
  query tokens, body or authorization headers.
- `INFO` logs artifact created/unchanged; `DEBUG` logs discovery counts and
  strategy; `WARNING` logs skipped/rejected links and source gaps.

### Tests

- `tests/unit/test_fetch_security.py`: private DNS, IPv6 loopback, disallowed
  redirects, max body, timeout/retry cap, host allowlist and safe URL logs.
- `tests/unit/test_discovery.py`: static/sitemap/link/API dedup, cap and
  canonical URL behavior.
- `tests/integration/test_source_fetch.py`: BMSTU fixture registry → discovery
  → artifact with checksum and repeated unchanged fetch.

### Acceptance Criteria

- Adding HSE source definitions does not change fetch/discovery orchestration.
- BMSTU fixture and official URL metadata are registered without importing old
  `andromeda` package or Core package.
- A redirect to a private/disallowed host is never requested.
- Identical response creates no new artifact and reports `SKIPPED_UNCHANGED`.

### Verification

- `pytest -q tests/unit/test_fetch_security.py tests/unit/test_discovery.py tests/integration/test_source_fetch.py`
- Import boundary: `rg -n "from (andromeda|andromeda_core)" src/andromeda_ingestion` must return no donor/Core imports.

## Phase Risks and Mitigations

- Risk: source-specific selectors leak into core. Mitigation: only URLs,
  allowlists and access metadata live in source adapters; content semantics are
  profile/provider output.
- Risk: SSRF via redirects or DNS rebinding. Mitigation: validate every hop and
  resolve before request with bounded redirect chain.

## Phase Completion Checklist

- Task 4 is covered by policy, fixture and persistence evidence.
