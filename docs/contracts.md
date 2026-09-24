# Contracts

All cross-layer and Core-facing payloads have `schema_version`. The principal
contracts are `SourceDefinition`, `DiscoveredItem`, `FetchedArtifact`,
`RawArtifact`, `PreparedDocument`, `ExtractionProfile`, `ExtractionResult`,
`CandidateFact`, `CandidateRelation`, `CandidateRule`,
`UnknownConceptCandidate`, `ChangeCandidate`, `ObservationCandidate` and
`CorePublishResult`.

Evidence is mandatory for every candidate. A locator can contain page, section,
paragraph, table/row, selector, fragment or text range and always points back to
the immutable artifact ID and source URL.

Contract evolution rules:

- additive fields and new enum values require a compatibility review;
- semantic changes require a new profile/contract version;
- unknown concepts become review proposals, not dynamic JSON properties;
- idempotency keys and checksums are stable across retries.

