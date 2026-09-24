"""Explicit pipeline transition policy."""

from __future__ import annotations

from collections.abc import Mapping

from ..common import PipelineState
from ..errors import ConflictError

ALLOWED_TRANSITIONS: Mapping[PipelineState, frozenset[PipelineState]] = {
    PipelineState.DISCOVERED: frozenset({PipelineState.FETCHING, PipelineState.FAILED}),
    PipelineState.FETCHING: frozenset({PipelineState.FETCHED, PipelineState.RETRYABLE, PipelineState.FAILED}),
    PipelineState.FETCHED: frozenset({PipelineState.PREPARING, PipelineState.SKIPPED_UNCHANGED, PipelineState.FAILED}),
    PipelineState.PREPARING: frozenset({PipelineState.PREPARED, PipelineState.RETRYABLE, PipelineState.FAILED}),
    PipelineState.PREPARED: frozenset({PipelineState.EXTRACTING, PipelineState.FAILED}),
    PipelineState.EXTRACTING: frozenset({PipelineState.EXTRACTED, PipelineState.RETRYABLE, PipelineState.FAILED}),
    PipelineState.EXTRACTED: frozenset({PipelineState.VALIDATING, PipelineState.FAILED}),
    PipelineState.VALIDATING: frozenset({PipelineState.VALIDATED, PipelineState.NEEDS_REVIEW, PipelineState.FAILED}),
    PipelineState.VALIDATED: frozenset({PipelineState.PUBLISHING, PipelineState.NEEDS_REVIEW, PipelineState.FAILED}),
    PipelineState.PUBLISHING: frozenset(
        {PipelineState.PUBLISHED, PipelineState.NEEDS_REVIEW, PipelineState.RETRYABLE, PipelineState.FAILED}
    ),
    PipelineState.RETRYABLE: frozenset(
        {PipelineState.FETCHING, PipelineState.PREPARING, PipelineState.EXTRACTING, PipelineState.PUBLISHING, PipelineState.FAILED}
    ),
    PipelineState.NEEDS_REVIEW: frozenset({PipelineState.VALIDATING, PipelineState.PUBLISHING, PipelineState.FAILED}),
    PipelineState.PUBLISHED: frozenset(),
    PipelineState.SKIPPED_UNCHANGED: frozenset(),
    PipelineState.FAILED: frozenset({PipelineState.FETCHING, PipelineState.PREPARING, PipelineState.EXTRACTING, PipelineState.PUBLISHING}),
}


def assert_transition(current: PipelineState, target: PipelineState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ConflictError(
            "INVALID_PIPELINE_TRANSITION",
            "Pipeline state transition is not allowed.",
            {"current": current.value, "target": target.value},
        )
