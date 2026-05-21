from __future__ import annotations

from typing import Any


def snapshot_context_fingerprint(*, subject_lines: list[dict[str, Any]]) -> str:
    parts = [
        "|".join(
            [
                str(item.get("assessment_id", "")),
                str(item.get("compilation_run_id", "")),
                str(item.get("curriculum_version_id", "")),
                str(item.get("school_grading_schema_version", "")),
            ]
        )
        for item in subject_lines
    ]
    return ";".join(sorted(parts))


def snapshot_is_context_preserving(
    *,
    subject_line: dict[str, Any],
    compiled_snapshot: Any,
) -> bool:
    return (
        str(subject_line.get("compiled_learner_snapshot_id"))
        == str(compiled_snapshot.id)
        and str(subject_line.get("curriculum_version_id"))
        == str(compiled_snapshot.curriculum_version_id)
        and str(subject_line.get("learning_area_id"))
        == str(compiled_snapshot.learning_area_id)
    )
