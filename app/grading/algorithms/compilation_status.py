"""Determine deterministic compilation status.

Compilation status is a fact about submitted academic records, not a report
state.  Keeping this logic side-effect-free lets services and tests agree on
when a compilation is complete, partial, blocked, failed, or stale.
"""

from __future__ import annotations

from typing import Any


PENDING = "pending"
COMPLETE = "complete"
PARTIAL = "partial"
FAILED = "failed"
STALE = "stale"
BLOCKED = "blocked"


def determine_compilation_status(
    *,
    missing_marks: list[dict[str, Any]],
    invalid_records: list[dict[str, Any]] | None = None,
    has_submitted_records: bool,
) -> str:
    if invalid_records:
        return FAILED
    if not has_submitted_records:
        return BLOCKED
    if missing_marks:
        return PARTIAL
    return COMPLETE
