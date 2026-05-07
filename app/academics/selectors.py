"""
academics/selectors.py
======================
CQRS-Lite Read Layer for Academics
Back To Front Development

SECURITY:
    - Verifies Authorization before executing the payload query.
    - Prevents IDOR by strictly filtering on the authenticated User's assignments.

PERFORMANCE:
    - Strictly limits SQL Execution to O(1) Time Complexity regardless of Roster Size.
    - Returns python dictionaries via .values() to skip costly ORM Model Instantiation.
"""

from typing import Any, Dict, List

from django.core.exceptions import PermissionDenied

from academics.models import Enrollment, TeacherAssignment


def get_fast_grid_roster(
    teacher_user,
    cohort_uuid: str,
    subject_uuid: str,
) -> List[Dict[str, Any]]:
    """
    Retrieves the class roster for the Fast-Grid interface.
    Executes in exactly 2 DB Queries:
        1. Auth Verification (TeacherAssignment check)
        2. Roster Payload (Enrollment Inner Join Student)

    Returns raw dictionaries to bypass ORM instantiation overhead.
    """

    # 1. Authorization Gate (Query 1)
    # Uses .exists() which is a highly optimized SELECT 1 query.
    is_authorized = TeacherAssignment.objects.filter(
        teacher=teacher_user,
        cohort_id=cohort_uuid,
        subject_id=subject_uuid,
    ).exists()

    if not is_authorized:
        raise PermissionDenied(
            "Teacher is not assigned to this cohort/subject combination."
        )

    # 2. Roster Payload (Query 2)
    # Using .values() to execute an Inner Join on the DB side.
    roster_data = (
        Enrollment.objects.filter(cohort_id=cohort_uuid, student__is_active=True)
        .order_by("student__last_name", "student__first_name")
        .values(
            "student__id",
            "student__first_name",
            "student__last_name",
            "student__admission_number",
        )
    )

    return [
        {
            "id": str(row["student__id"]),
            "first_name": row["student__first_name"],
            "last_name": row["student__last_name"],
            "admission_number": row["student__admission_number"],
        }
        for row in roster_data
    ]
