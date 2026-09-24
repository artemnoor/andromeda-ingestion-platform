# Contracts

All cross-layer and Core-facing payloads have `schema_version`. The principal
contracts are `SourceDefinition`, `DiscoveredItem`, `FetchedArtifact`,
`RawArtifact`, `PreparedDocument`, `ExtractionProfile`, `LLMExtractionPayload`,
`ExtractionResult`,
`CandidateFact`, `CandidateRelation`, `CandidateRule`,
`UnknownConceptCandidate`, `ChangeCandidate`, `ObservationCandidate`,
`SourceRegistration` and `CorePublishResult`.

Evidence is mandatory for every candidate. A locator can contain page, section,
paragraph, table/row, selector, fragment or text range and always points back to
the immutable artifact ID and source URL.

Contract evolution rules:

- additive fields and new enum values require a compatibility review;
- semantic changes require a new profile/contract version;
- unknown concepts become review proposals, not dynamic JSON properties;
- idempotency keys identify a refresh stream; checksums are checked on every
  refresh and are stable across stage retries;
- SourceRegistration separates the logical Core source ID from the immutable
  Core source-document metadata ID;
- raw bytes and storage keys are Ingestion-internal and are represented across
  the boundary only as metadata/evidence references.
- `LLMExtractionPayload` is semantic-only; `ExtractionResult` ingestion metadata
  is created deterministically by the application adapter.
