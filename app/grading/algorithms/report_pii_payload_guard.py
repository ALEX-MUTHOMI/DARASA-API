from __future__ import annotations

from typing import Any


FORBIDDEN_REPORT_PAYLOAD_KEYS = frozenset(
    {
        "raw_marks",
        "learner_names",
        "guardian_data",
        "guardian_phone",
        "teacher_private_notes",
        "report_text",
        "nlp_output",
        "raw_grade_grid",
    }
)


def assert_report_payload_is_reference_safe(payload: dict[str, Any]) -> None:
    keys = {str(key) for key in payload.keys()}
    forbidden = keys & FORBIDDEN_REPORT_PAYLOAD_KEYS
    if forbidden:
        raise ValueError("Report payload contains forbidden sensitive fields.")
