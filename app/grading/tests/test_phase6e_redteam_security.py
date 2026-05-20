from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from grading.algorithms.pii_safe_correction_payload import (
    assert_pii_safe_event_payload,
)
from grading.services import (
    build_grade_record,
    build_submission_batch,
    create_correction_request,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _record(school, assessment, teacher_user, teacher_assignment, student):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key=f"phase6e-security-{student.id}",
    )
    return build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=student,
        raw_score=Decimal("68.00"),
    )


def test_correction_rejects_mass_assignment_and_xss_reason(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    record = _record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )

    with pytest.raises(ValidationError):
        create_correction_request(
            actor=teacher_user,
            tenant=school,
            grade_record_id=record.id,
            payload={
                "reason": "Safe reason.",
                "proposed_raw_score": "70.00",
                "status": "approved",
            },
        )

    with pytest.raises(ValidationError):
        create_correction_request(
            actor=teacher_user,
            tenant=school,
            grade_record_id=record.id,
            payload={
                "reason": "<script>alert(1)</script>",
                "proposed_raw_score": "70.00",
            },
        )


def test_correction_event_payload_guard_blocks_marks_and_learner_names():
    with pytest.raises(ValidationError):
        assert_pii_safe_event_payload(
            {
                "tenant_id": "tenant-ref",
                "correction_request_id": "correction-ref",
                "raw_score": "77.00",
                "learner_name": "Sensitive Learner",
            }
        )
