# Source Registry

`SourceDefinition` contains stable identity, organization/category, source and
fetch strategy, allowlisted hosts, trust metadata, refresh policy and access
metadata. `discovered_items` are URL/document candidates, not knowledge.

Supported conceptual source categories include `UNIVERSITY`, `MINISTRY`,
`GOVERNMENT`, `OLYMPIAD_ORGANIZER`, `REGULATOR` and `OTHER_OFFICIAL_SOURCE`.
The current implementation supports static URLs, bounded sitemaps and bounded
same-origin HTML link discovery. API/feed/search/AI-assisted strategies remain
explicit extension points and fail closed until their adapters are configured.

University-specific code is intentionally restricted to access configuration.
The BMSTU demo uses official-looking URLs plus local fixture paths; the semantic
profile and pipeline are generic. HSE or another university can be added by
registering source definitions, access adapters where needed, and profiles—not
by adding a new orchestration branch.
