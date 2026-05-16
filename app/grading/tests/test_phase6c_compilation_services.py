from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone
import pytest

from academics.models import Enrollment, Student
from events.models import EventOutbox
from grading.models import (
    CompilationRun,
    CompiledAssessmentSnapshot,
    CompiledCohortSummary,
    CompiledLearnerSnapshot,
    GradeDraftBatch,
)
from grading.services import compile_assessment, save_grade_draft, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:compile",
    }


def _row(student, score="80.00"):
    return {"student_id": str(student.id), "raw_score": score}


def test_compile_assessment_creates_canonical_snapshots(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "84.00")]},
        idempotency_key="compile-source-submit",
        confirmation=_confirmation(teacher_user, school),
    )

    with django_capture_on_commit_callbacks(execute=True):
        run = compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=principal_user,
        )

    assert run.status == CompilationRun.Status.COMPLETE
    assert CompiledAssessmentSnapshot.objects.get(compilation_run=run).summary[
        "submitted_learner_count"
    ] == 1
    learner_snapshot = CompiledLearnerSnapshot.objects.get(compilation_run=run)
    assert learner_snapshot.curriculum_version_id == assessment.curriculum_version_id
    assert learner_snapshot.rubric_foundation_id == assessment.rubric_foundation_id
    assert learner_snapshot.score_summary["percentage"] == "84.00"
    assert CompiledCohortSummary.objects.get(compilation_run=run).status == "complete"

    event = EventOutbox.objects.get(event_type="grading.compilation_completed")
    assert event.event_version == 1
    assert event.payload["compilation_run_id"] == str(run.id)
    assert "raw_marks" not in event.payload
    assert "learner_names" not in event.payload
    assert "component_scores" not in event.payload


def test_drafts_are_not_compiled(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "70.00")]},
        idempotency_key="draft-not-compiled",
    )

    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    assert run.status == CompilationRun.Status.BLOCKED
    assert GradeDraftBatch.objects.count() == 1
    assert CompiledLearnerSnapshot.objects.filter(compilation_run=run).count() == 0


def test_missing_roster_mark_creates_partial_summary(
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
        admission_number="P6CMISS001",
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
        payload={"rows": [_row(enrolled_student, "74.00")]},
        idempotency_key="partial-submit",
        confirmation=_confirmation(teacher_user, school),
    )

    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    summary = CompiledCohortSummary.objects.get(compilation_run=run)
    assert run.status == CompilationRun.Status.PARTIAL
    assert summary.expected_learner_count == 2
    assert summary.submitted_learner_count == 1
    assert summary.missing_learner_count == 1


def test_unbound_or_unauthorized_assessment_cannot_compile(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
):
    with pytest.raises(ValidationError):
        compile_assessment(tenant=school, assessment_id=assessment.id)

    with pytest.raises(ValidationError):
        compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=teacher_user,
        )

    assessment.__class__.objects.filter(id=assessment.id).update(
        curriculum_version=None,
        curriculum_binding_locked_at=None,
    )
    with pytest.raises(ValidationError):
        compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=principal_user,
        )
