# ADR 0003: Provider-neutral structured extraction

Status: accepted

The application depends on `DocumentUnderstandingPort` and an explicit router.
MockAI is the default for CI; an HTTP JSON adapter and future Jev/local/model
adapters implement the same contract. Prompts, schema and provider metadata are
versioned in extraction profiles rather than embedded in route handlers.

