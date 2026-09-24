# Adding an AI provider

Implement `DocumentUnderstandingPort` (and optional specialized ports) in
`infrastructure/ai`. Accept `ExtractionContext`, keep profile instructions and
untrusted document data separate, request strict JSON, validate into
`ExtractionResult`, and never call Core admin routes.

Register the adapter in the provider router/configuration. Application services,
repository contracts, candidates, evidence and tests remain unchanged. Add a
mock or recorded contract test so CI never depends on paid credentials. Live
provider tests must be opt-in and must not log secrets or full document bodies.

