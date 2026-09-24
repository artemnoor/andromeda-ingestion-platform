# ADR 0006: Keep Knowledge Core behind an HTTP anti-corruption boundary

## Status

Accepted

## Context

The ingestion service and Knowledge Core have separate ownership and release
cadences. Ingestion understands source access, raw artifacts and extraction;
Core owns ontology, canonical knowledge, review and normative activation. A
shared PostgreSQL schema or imported Core ORM models would couple those
responsibilities and make either service impossible to evolve independently.

The current Core exposes a generic Observation API rather than dedicated
candidate-rule and candidate-relation endpoints.

## Decision

Ingestion depends on `KnowledgeCorePort` only. The production adapter uses the
versioned Core HTTP API for ontology snapshots, source registration and
observation publication. Candidate rules, relations, changes and unknown
concepts are transported as typed fields plus `raw_payload` and evidence until
Core exposes more specialized endpoints.

The ingestion database never stores Core tables and the ingestion process never
activates Rules, accepts Facts or mutates Ontology. A mock adapter implements
the same contract for tests and local development.

## Consequences

- Core can be upgraded or moved without changing ingestion domain/application
  code, as long as the port contract remains compatible.
- Integration failures are retryable and do not delete persisted extraction
  evidence.
- The generic Observation envelope is less convenient than a dedicated
  candidate API, so the mapping is documented and covered by live contract
  smoke tests.
- A future Core candidate endpoint can be adopted by replacing the adapter,
  not by adding a second persistence path.
