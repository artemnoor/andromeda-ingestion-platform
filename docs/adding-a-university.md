# Adding a university

1. Add source definitions for official pages, APIs and normative documents.
2. Select a discovery strategy and configure host allowlists/refresh policy.
3. Reuse HTTP/API/fixture fetchers; implement a custom access adapter only when
   the transport truly differs.
4. Choose or add an extraction profile with ontology concepts and output schema.
5. Add sanitized fixtures and golden expectations.
6. Run discovery, pipeline, evidence and Core contract tests.

Do not add a `UniversityParser` for semantic policy. If the document introduces
a concept not expressible by the Core ontology, emit `UnknownConceptCandidate`
and let the Core review workflow handle ontology evolution.

