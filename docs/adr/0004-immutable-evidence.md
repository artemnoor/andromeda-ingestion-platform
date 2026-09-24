# ADR 0004: Immutable raw evidence before interpretation

Status: accepted

Every fetch is checksum-addressed and written to artifact storage before
preparation or AI extraction. A new checksum creates a new version. Locators and
excerpts remain linked to the exact artifact, making extraction reproducible and
reviewable even after a source changes.

