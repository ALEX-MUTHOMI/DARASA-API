from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CompilationFreshness:
    is_stale: bool
    reasons: tuple[str, ...]


def detect_stale_compilation(
    *,
    compilation_status: str | None,
    compiled_at: datetime | None,
    assessment_updated_at: datetime | None = None,
    latest_batch_submitted_at: datetime | None = None,
    latest_correction_requested_at: datetime | None = None,
) -> CompilationFreshness:
    reasons: list[str] = []
    if compilation_status == "stale":
        reasons.append("compilation_marked_stale")
    if compiled_at is None:
        reasons.append("compilation_missing_timestamp")
    if compiled_at is not None and assessment_updated_at is not None:
        if assessment_updated_at > compiled_at:
            reasons.append("assessment_changed_after_compilation")
    if compiled_at is not None and latest_batch_submitted_at is not None:
        if latest_batch_submitted_at > compiled_at:
            reasons.append("submission_after_compilation")
    if compiled_at is not None and latest_correction_requested_at is not None:
        if latest_correction_requested_at > compiled_at:
            reasons.append("correction_after_compilation")
    return CompilationFreshness(is_stale=bool(reasons), reasons=tuple(reasons))
