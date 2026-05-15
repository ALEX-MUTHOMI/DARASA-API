from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academics.models import Enrollment, Student
from events.models import EventOutbox
from grading.services import build_grade_grid, get_my_grading_work, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:perf",
    }


def _add_roster_students(school, cohort, academic_year, term, count=12):
    students = []
    for index in range(count):
        student = Student.objects.create(
            tenant=school,
            admission_number=f"P6BPERF{index:03d}",
            first_name=f"Perf{index}",
            last_name="Learner",
        )
        Enrollment.objects.create(
            tenant=school,
            student=student,
            cohort=cohort,
            academic_year=academic_year,
            term=term,
        )
        students.append(student)
    inactive = Student.objects.create(
        tenant=school,
        admission_number="P6BINACTIVE",
        first_name="Inactive",
        last_name="Learner",
        is_active=False,
    )
    Enrollment.objects.create(
        tenant=school,
        student=inactive,
        cohort=cohort,
        academic_year=academic_year,
        term=term,
    )
    return students


def test_workload_resolver_uses_bounded_teacher_assessment_path(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
):
    with CaptureQueriesContext(connection) as captured:
        work = get_my_grading_work(actor=teacher_user, tenant=school)

    assert [item["assessment_id"] for item in work] == [str(assessment.id)]
    assert len(captured) <= 8


def test_grade_grid_builder_is_bounded_to_one_roster(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    cohort,
    academic_year,
    term,
):
    students = _add_roster_students(school, cohort, academic_year, term, count=12)

    with CaptureQueriesContext(connection) as captured:
        grid = build_grade_grid(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )

    assert len(grid["rows"]) == len(students)
    student_ids = {str(student.id) for student in students}
    assert all(row["student_id"] in student_ids for row in grid["rows"])
    assert len(captured) <= 16


def test_final_submission_uses_bounded_batch_access_and_one_event(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    cohort,
    academic_year,
    term,
    django_capture_on_commit_callbacks,
):
    students = _add_roster_students(school, cohort, academic_year, term, count=8)
    payload = {
        "rows": [
            {"student_id": str(student.id), "raw_score": "60.00"}
            for student in students
        ]
    }

    with CaptureQueriesContext(connection) as captured:
        with django_capture_on_commit_callbacks(execute=True):
            batch = submit_grade_batch(
                actor=teacher_user,
                tenant=school,
                assessment_id=assessment.id,
                payload=payload,
                idempotency_key="performance-submit",
                confirmation=_confirmation(teacher_user, school),
            )

    assert batch.record_count == len(students)
    assert EventOutbox.objects.filter(event_type="grading.batch_submitted").count() == 1
    assert len(captured) <= 55
