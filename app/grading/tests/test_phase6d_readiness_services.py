from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from academics.models import Enrollment, Student
from curriculum.models import CurriculumVersionWithdrawal, SchoolCurriculumAdoption
from grading.algorithms.correction_hash import hash_grade_state
from grading.models import (
    AssessmentComponent,
    CompilationRun,
    GradeCorrectionRequest,
    GradeRecord,
)
from grading.services import (
    compile_assessment,
    compute_assessment_readiness,
    get_principal_readiness_projection,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase6d",
    }


def _submit_and_compile(school, assessment, teacher_user, principal_user, student):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(student.id), "raw_score": "80.00"}]},
        idempotency_key=f"phase6d-submit-{student.id}",
        confirmation=_confirmation(teacher_user, school),
    )
    return compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )


def _blocker_codes(readiness):
    return {item["code"] for item in readiness["blockers"]}


def test_complete_compilation_becomes_report_ready(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert readiness["readiness_status"] == "ready_for_reports"
    assert readiness["report_ready"]
    assert readiness["compilation_run_id"] == str(run.id)
    assert readiness["blockers"] == []


def test_missing_marks_and_missing_required_component_block_readiness(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
    cohort,
    academic_year,
    term,
):
    missing_student = Student.objects.create(
        tenant=school,
        admission_number="P6D-MISSING",
        first_name="Missing",
        last_name="Learner",
    )
    Enrollment.objects.create(
        tenant=school,
        student=missing_student,
        cohort=cohort,
        academic_year=academic_year,
        term=term,
    )
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={
            "rows": [{"student_id": str(enrolled_student.id), "raw_score": "72.00"}]
        },
        idempotency_key="phase6d-partial-submit",
        confirmation=_confirmation(teacher_user, school),
    )
    AssessmentComponent.objects.create(
        tenant=school,
        assessment=assessment,
        name="Practical setup",
        max_score=Decimal("30.00"),
        is_required=True,
        rubric_foundation=assessment.rubric_foundation,
    )
    compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert not readiness["report_ready"]
    assert {"missing_marks", "missing_required_component"} <= _blocker_codes(
        readiness
    )


def test_failed_stale_and_pending_correction_block_report_readiness(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    CompilationRun.objects.filter(id=run.id).update(status=CompilationRun.Status.STALE)
    record = GradeRecord.objects.get(assessment=assessment, student=enrolled_student)
    GradeCorrectionRequest.objects.create(
        tenant=school,
        grade_record=record,
        requested_by=teacher_user,
        reason="Correction needed before reports.",
        old_state_hash=hash_grade_state({"score": "80.00"}),
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert not readiness["report_ready"]
    assert {"stale_compilation", "correction_pending"} <= _blocker_codes(readiness)


def test_cct_withdrawal_and_missing_adoption_create_review_blockers_without_mutation(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    original_curriculum_version_id = assessment.curriculum_version_id
    SchoolCurriculumAdoption.objects.filter(
        tenant=school,
        curriculum_version=assessment.curriculum_version,
    ).delete()
    CurriculumVersionWithdrawal.objects.create(
        curriculum_version=assessment.curriculum_version,
        status=CurriculumVersionWithdrawal.Status.WITHDRAWN,
        reason="Official withdrawal requires review.",
        withdrawn_by=principal_user,
        withdrawn_at=timezone.now(),
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    assessment.refresh_from_db()

    assert not readiness["report_ready"]
    assert {
        "cct_adoption_missing",
        "cct_withdrawal_review_required",
    } <= _blocker_codes(readiness)
    assert assessment.curriculum_version_id == original_curriculum_version_id
    assert GradeRecord.objects.filter(assessment=assessment).count() == 1


def test_school_projection_aggregates_assessment_readiness(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )

    projection = get_principal_readiness_projection(
        actor=principal_user,
        tenant=school,
    )

    assert projection["projection_type"] == "principal"
    assert projection["ready_for_reports"]
    assert projection["status_counts"] == {"ready_for_reports": 1}
