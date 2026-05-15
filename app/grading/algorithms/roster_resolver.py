"""Roster shaping for one tenant/cohort assessment context.

The database selector fetches a bounded cohort roster; this algorithm only
normalizes ordering and row shape so grid and validation code stay consistent.
"""

from __future__ import annotations

from typing import Any


def stable_roster_rows(students: list[Any]) -> list[dict[str, Any]]:
    ordered = sorted(
        students,
        key=lambda student: (
            str(getattr(student, "admission_number", "")).lower(),
            str(getattr(student, "last_name", "")).lower(),
            str(getattr(student, "first_name", "")).lower(),
            str(getattr(student, "id", "")),
        ),
    )
    return [
        {
            "student_id": str(student.id),
            "admission_number": student.admission_number,
            "display_name": f"{student.first_name} {student.last_name}".strip(),
        }
        for student in ordered
    ]
