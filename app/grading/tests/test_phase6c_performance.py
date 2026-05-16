from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
import pytest

from academics.models import Enrollment, Student
from grading.models import CompiledLearnerSnapshot
from grading.services import compile_assessment, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:compile-perf",
    }


def _students(school, cohort, academic_year, term, count=8):
    created = []
    for index in range(count):
        student = Student.objects.create(
            tenant=school,
            admission_number=f"P6CPERF{index:03d}",
            first_name=f"Compile{index}",
            last_name="Learner",
        )
        Enrollment.objects.create(
            tenant=school,
            student=student,
            cohort=cohort,
            academic_year=academic_year,
            term=term,
        )
        created.append(student)
    return created


def test_compilation_is_bounded_to_one_assessment_roster(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    cohort,
    academic_year,
    term,
):
    students = _students(school, cohort, academic_year, term, count=8)
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={
            "rows": [
                {"student_id": str(student.id), "raw_score": "70.00"}
                for student in students
            ]
        },
        idempotency_key="compile-performance-submit",
        confirmation=_confirmation(teacher_user, school),
    )

    with CaptureQueriesContext(connection) as captured:
        run = compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=principal_user,
        )

    assert CompiledLearnerSnapshot.objects.filter(compilation_run=run).count() == 8
    assert len(captured) <= 75
