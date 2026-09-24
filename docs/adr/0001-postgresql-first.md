# ADR 0001: PostgreSQL metadata and logical graph first

Status: accepted

Use PostgreSQL for source registry, temporal artifact metadata, extraction
state, candidates, jobs and audit. The graph is represented by typed contracts
and evidence-backed edges; a graph database is not introduced initially.

This preserves transactional/idempotent workflows and matches the Knowledge
Core boundary. A graph database can be added behind a read/projection port only
after measured query evidence requires it.

