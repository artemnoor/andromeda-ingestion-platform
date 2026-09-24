# ADR 0005: Modular monolith before distributed workers

Status: accepted

Explicit ports allow fetchers, AI providers, storage and Core integration to be
extracted later. Kafka, Redis, Kubernetes and microservices are intentionally
not required for the first production-oriented vertical slice; jobs and state
machines define the future worker seam.

