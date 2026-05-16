from __future__ import annotations

from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import Enrollment, TeacherAssignment
from core.models import CustomUser, Role, TenantUserRole
from curriculum.models import CurriculumVersion
from events.models import EventOutbox
from events.services import write_outbox_event
from grading.models import (
    CompiledAssessmentSnapshot,
    CompiledLearnerSnapshot,
    GradeSubmissionBatch,
)
from grading.services import (
    compile_assessment,
    compile_submission_batch,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:closeout",
    }


def _submit(school, assessment, teacher_user, student, key="closeout-submit"):
    return submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(student.id), "raw_score": "78.00"}]},
        idempotency_key=key,
        confirmation=_confirmation(teacher_user, school),
    )


def _role_user(school, code):
    role = Role.objects.get_or_create(
        code=code,
        defaults={"name": code.replace("_", " ").title()},
    )[0]
    user = CustomUser.objects.create_user(
        email=f"phase6c-closeout-{code}-{school.id}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def test_later_curriculum_version_does_not_mutate_compiled_snapshot(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
    curriculum_source_document,
):
    original_version_id = assessment.curriculum_version_id
    _submit(school, assessment, teacher_user, enrolled_student)
    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )
    newer_version = CurriculumVersion.objects.create(
        source_document=curriculum_source_document,
        version_label="Later Phase 6C Fixture",
        effective_from="2027-01-01",
        is_active=False,
    )

    snapshot = CompiledAssessmentSnapshot.objects.get(compilation_run=run)

    assert newer_version.id != original_version_id
    assert snapshot.curriculum_version_id == original_version_id
    assert snapshot.context_snapshot["curriculum_version_id"] == str(
        original_version_id
    )
    assert snapshot.context_snapshot["academic_year_id"] == str(
        assessment.academic_year_id
    )
    assert snapshot.context_snapshot["term_id"] == str(assessment.term_id)


def test_inactive_or_out_of_roster_learner_is_flagged_not_silently_trusted(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _submit(school, assessment, teacher_user, enrolled_student)
    Enrollment.objects.filter(student=enrolled_student).update(is_active=False)

    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    snapshot = CompiledLearnerSnapshot.objects.get(compilation_run=run)
    assert snapshot.missing_marks[0]["code"] == "student_outside_roster"
    assert run.expected_learner_count == 0


def test_hod_cannot_compile_unassigned_assessment(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    _submit(school, assessment, teacher_user, enrolled_student)
    hod = _role_user(school, Role.RoleCode.HOD.value)

    with pytest.raises(ValidationError):
        compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=hod,
        )

    TeacherAssignment.objects.create(
        tenant=school,
        teacher=hod,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
    )
    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=hod,
    )
    assert run.assessment_id == assessment.id


def test_compile_submission_batch_requires_submitted_batch(
    school,
    assessment,
    principal_user,
    teacher_user,
    teacher_assignment,
):
    draft_batch = GradeSubmissionBatch.objects.create(
        tenant=school,
        assessment=assessment,
        teacher=teacher_user,
        teacher_assignment=teacher_assignment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        status=GradeSubmissionBatch.Status.DRAFT,
    )

    with pytest.raises(ValidationError):
        compile_submission_batch(
            tenant=school,
            batch_id=draft_batch.id,
            requested_by=principal_user,
        )


def test_failed_compilation_validation_emits_no_event(
    school,
    assessment,
    teacher_user,
):
    with pytest.raises(ValidationError):
        compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=teacher_user,
        )

    assert EventOutbox.objects.filter(
        event_type="grading.compilation_completed",
    ).count() == 0


def test_compilation_event_producer_allowlist_is_enforced(school, assessment):
    with pytest.raises(ValidationError):
        write_outbox_event(
            event_type="grading.compilation_completed",
            event_version=1,
            source_module="academics",
            idempotency_key="bad-compilation-producer",
            tenant=school,
            payload={
                "tenant_id": str(school.id),
                "assessment_id": str(assessment.id),
                "compilation_run_id": "run-id",
                "cohort_id": str(assessment.cohort_id),
                "learning_area_id": str(assessment.learning_area_id),
                "curriculum_version_id": str(assessment.curriculum_version_id),
                "status": "complete",
                "compiled_at": timezone.now().isoformat(),
            },
        )


def test_phase6c_algorithms_are_side_effect_safe():
    algorithm_dir = Path(__file__).resolve().parents[1] / "algorithms"
    forbidden = [
        ".objects.",
        ".save(",
        ".create(",
        ".update(",
        "bulk_create",
        "write_outbox_event",
        "requests.",
        "httpx",
        "source_url_validator",
        "ssrf_guard",
        "artifact_validator",
        "curriculum_diff_engine",
        "regulatory_notice_classifier",
    ]

    for path in algorithm_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        content = path.read_text()
        assert not any(term in content for term in forbidden), path.name
