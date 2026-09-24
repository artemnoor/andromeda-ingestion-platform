# Change detection

For each new artifact version, candidates are indexed by semantic natural key:

- `fact:<subject>:<property>`;
- `relation:<subject>:<type>:<target>`;
- `rule:<logical_key>`;
- `unknown:<name>`.

Stable canonical JSON fingerprints compare previous and current extraction
payloads. The result is `ADDED`, `MODIFIED`, `REMOVED`, `POSSIBLY_REPLACED` or
`AMBIGUOUS`, with before/after payloads, confidence, reason and current evidence.

```mermaid
flowchart LR
  A[checksum changed] --> E[extract current artifact]
  E --> C[compare natural-key fingerprints]
  C --> CC[ChangeCandidate]
  CC --> Core[Core Observation / review]
```

The amended BMSTU fixture changes `>= 90` to `>= 85` and produces a persisted
`MODIFIED` rule candidate without changing application business logic.

