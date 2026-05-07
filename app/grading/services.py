"""
grading/services.py
===================
High-Velocity Write Engine for the Fast-Grid
Back To Front Development

PERFORMANCE:
    - Guaranteed O(1) query execution for arbitrary payload sizes.
    - Uses `update_conflicts=True` for PostgreSQL ON CONFLICT behavior.

SECURITY:
    - Cross-Tenant IDOR protection via batch Validation against TeacherAssignments.
"""

from typing import Any, Dict, List
from uuid import UUID

from academics.models import Enrollment
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from grading.algorithms import CBCTranslator
from grading.models import GradeRecord


class BatchGradeService:
    """
    Handles bulk grade submissions from the Fast-Grid interface.
    """

    @staticmethod
    @transaction.atomic
    def submit_fast_grid_payload(
        teacher_user,
        assessment_uuid: str | UUID,
        subject_uuid: str | UUID,
        payload_list: List[Dict[str, Any]],
    ) -> int:
        """
        Processes an arbitrary number of grades in exactly 2 queries:
            Query 1: O(1) Bulk Authorization Check
            Query 2: O(1) Bulk Upsert (ON CONFLICT DO UPDATE)

        payload_list format:
        [{"student_uuid": "abc-123", "raw_score": 85.5, "remarks": "Excellent"}]
        """
        if not payload_list:
            return 0

        requested_student_ids = {str(p["student_uuid"]) for p in payload_list}

        authorized_student_ids_query = Enrollment.objects.filter(
            student_id__in=requested_student_ids,
            cohort__teacher_assignments__teacher=teacher_user,
            cohort__teacher_assignments__subject_id=subject_uuid,
        ).values_list("student_id", flat=True)

        authorized_student_ids = {str(sid) for sid in authorized_student_ids_query}

        unauthorized_ids = requested_student_ids - authorized_student_ids
        if unauthorized_ids:
            raise PermissionDenied(
                "Teacher is not authorized to grade one or more submitted records."
            )

        records_to_upsert = []
        for payload in payload_list:
            try:
                raw_score = float(payload["raw_score"])
            except (ValueError, TypeError):
                raise ValidationError("Invalid raw_score format.")

            cbc_score = CBCTranslator.translate_percentage(raw_score)

            records_to_upsert.append(
                GradeRecord(
                    student_id=payload["student_uuid"],
                    subject_id=subject_uuid,
                    assessment_id=assessment_uuid,
                    raw_score=raw_score,
                    cbc_score=cbc_score,
                    remarks=payload.get("remarks", ""),
                    version=1,
                )
            )

        GradeRecord.objects.bulk_create(
            records_to_upsert,
            update_conflicts=True,
            unique_fields=["student", "subject", "assessment"],
            update_fields=["raw_score", "cbc_score", "remarks", "version"],
        )

        return len(records_to_upsert)
