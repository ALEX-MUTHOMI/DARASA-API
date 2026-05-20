from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from academics.models import TeacherAssignment
from core.models import CustomUser, Role, TenantUserRole
from grading.models import CompilationRun, GradeCorrectionAuditRecord
from grading.services import (
    apply_approved_correction,
    build_grade_record,
    build_submission_batch,
    create_correction_request,
    escalate_correction_request,
    review_correction_as_academic_head,
    review_correction_as_hod,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _role_user(school, role_code: str) -> CustomUser:
    role, _ = Role.objects.get_or_create(
        code=role_code,
        defaults={"name": role_code.replace("_", " ").title()},
    )
    user = CustomUser.objects.create_user(
        email=f"{role_code}-{school.id}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def _grade_record(school, assessment, teacher_user, teacher_assignment, student):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key=f"phase6e-batch-{student.id}",
    )
    return build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=student,
        raw_score=Decimal("71.00"),
    )


def _hod_for_assessment(school, assessment) -> CustomUser:
    hod = _role_user(school, Role.RoleCode.HOD.value)
    TeacherAssignment.objects.create(
        tenant=school,
        teacher=hod,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
    )
    return hod


def test_teacher_requests_hod_approves_and_application_marks_compilation_stale(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    record = _grade_record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )
    run = CompilationRun.objects.create(
        tenant=school,
        assessment=assessment,
        requested_by=principal_user,
        status=CompilationRun.Status.COMPLETE,
        expected_learner_count=1,
        submitted_learner_count=1,
        missing_learner_count=0,
    )
    hod = _hod_for_assessment(school, assessment)

    correction = create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=record.id,
        payload={
            "reason": "Transcription error from paper mark sheet.",
            "reason_code": "transcription_error",
            "proposed_raw_score": "74.00",
        },
    )
    correction = review_correction_as_hod(
        actor=hod,
        tenant=school,
        correction_request_id=correction.id,
        decision="approve",
        reason="Evidence checked against original script.",
    )
    correction = apply_approved_correction(
        actor=hod,
        tenant=school,
        correction_request_id=correction.id,
    )

    record.refresh_from_db()
    run.refresh_from_db()
    assert record.raw_score == Decimal("74.00")
    assert record.version == 2
    assert run.status == CompilationRun.Status.STALE
    assert correction.status == correction.Status.APPLIED
    audit_actions = list(
        GradeCorrectionAuditRecord.objects.filter(correction_request=correction)
        .order_by("created_at")
        .values_list("action", flat=True)
    )
    assert audit_actions == ["requested", "reviewed", "applied"]


def test_teacher_cannot_self_approve_and_hod_scope_is_enforced(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    record = _grade_record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )
    correction = create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=record.id,
        payload={"reason": "Correction required.", "proposed_raw_score": "72.00"},
    )

    with pytest.raises(ValidationError):
        review_correction_as_hod(
            actor=teacher_user,
            tenant=school,
            correction_request_id=correction.id,
            decision="approve",
            reason="Self approval attempt.",
        )

    unrelated_hod = _role_user(school, Role.RoleCode.HOD.value)
    with pytest.raises(ValidationError):
        review_correction_as_hod(
            actor=unrelated_hod,
            tenant=school,
            correction_request_id=correction.id,
            decision="approve",
            reason="Outside scope attempt.",
        )


def test_hod_unavailability_escalation_requires_reason_and_deputy_approval(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    record = _grade_record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )
    correction = create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=record.id,
        payload={
            "reason": "HOD away and report deadline pending.",
            "proposed_raw_score": "73.00",
        },
    )
    deputy = _role_user(school, Role.RoleCode.DEPUTY_PRINCIPAL.value)

    with pytest.raises(ValidationError):
        escalate_correction_request(
            actor=deputy,
            tenant=school,
            correction_request_id=correction.id,
            reason="",
        )

    correction = escalate_correction_request(
        actor=deputy,
        tenant=school,
        correction_request_id=correction.id,
        reason="HOD inactive during deadline window.",
    )
    correction = review_correction_as_academic_head(
        actor=deputy,
        tenant=school,
        correction_request_id=correction.id,
        decision="approve",
        reason="Escalation evidence reviewed.",
    )

    assert correction.status == correction.Status.APPROVED_BY_ACADEMIC_HEAD
    assert correction.escalated_by == deputy


def test_principal_cannot_casually_apply_correction(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    record = _grade_record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )
    hod = _hod_for_assessment(school, assessment)
    correction = create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=record.id,
        payload={
            "reason": "Score changed after moderation.",
            "proposed_raw_score": "79.00",
        },
    )
    review_correction_as_hod(
        actor=hod,
        tenant=school,
        correction_request_id=correction.id,
        decision="approve",
        reason="Approved by HOD.",
    )

    with pytest.raises(ValidationError):
        apply_approved_correction(
            actor=principal_user,
            tenant=school,
            correction_request_id=correction.id,
        )
