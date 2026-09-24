# Observability

Logs are JSON structured and include correlation IDs, route, status and duration.
Potential secrets, authorization values, prompts, bodies and raw payloads are
redacted or bounded.

`/metrics` exposes Prometheus-compatible counters/histograms for HTTP errors,
request duration and can be extended with fetch/AI/validation/publish timings.
Pipeline rows and audit events retain job/source/artifact/extraction IDs and
transition history, so a failed Core publish can be retried without losing the
extraction.

Operational probes are `/health` (liveness) and `/ready` (database readiness).

