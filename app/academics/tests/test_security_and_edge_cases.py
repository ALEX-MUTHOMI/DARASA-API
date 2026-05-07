import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError

from academics.models import Cohort
from academics.selectors import get_fast_grid_roster

pytestmark = pytest.mark.django_db


def test_fast_grid_idor_prevention(
    cohort,
    enrollment_factory,
    subject,
    teacher_user,
):
    """
    SECURITY GATE (IDOR):
    A teacher attempts to fetch a roster for a cohort they are NOT assigned to.
    The selector MUST raise PermissionDenied before touching student data.
    """
    enrollment_factory.create_batch(5, cohort=cohort)

    with pytest.raises(PermissionDenied):
        get_fast_grid_roster(teacher_user, cohort.id, subject.id)


def test_roster_excludes_inactive_students(
    cohort,
    enrollment_factory,
    student_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    BUSINESS LOGIC GATE:
    Transferred/expelled students stay in the DB for DPA requirements but must
    not appear on the daily attendance/grading roster.
    """
    teacher_assignment_factory(
        teacher=teacher_user,
        cohort=cohort,
        subject=subject,
    )

    active_student = student_factory(is_active=True)
    enrollment_factory(student=active_student, cohort=cohort)

    inactive_student = student_factory(is_active=False)
    enrollment_factory(student=inactive_student, cohort=cohort)

    roster = get_fast_grid_roster(teacher_user, cohort.id, subject.id)

    assert len(roster) == 1
    assert roster[0]["id"] == str(active_student.id)


def test_unique_enrollment_constraint(student, cohort, enrollment_factory):
    """
    DATA INTEGRITY GATE:
    A student cannot be enrolled in the exact same cohort twice.
    """
    enrollment_factory(student=student, cohort=cohort)

    with pytest.raises(IntegrityError):
        enrollment_factory(student=student, cohort=cohort)


def test_unique_teacher_assignment_constraint(
    cohort,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    DATA INTEGRITY GATE:
    A teacher cannot be assigned to the same subject in the same cohort twice.
    """
    teacher_assignment_factory(
        teacher=teacher_user,
        cohort=cohort,
        subject=subject,
    )

    with pytest.raises(IntegrityError):
        teacher_assignment_factory(
            teacher=teacher_user,
            cohort=cohort,
            subject=subject,
        )


def test_cohort_academic_year_constraint():
    """
    DATA INTEGRITY GATE:
    Cohort year must be sane (2000-2100).
    """
    # SQLite might not enforce CheckConstraints depending on version.
    with pytest.raises(IntegrityError):
        Cohort.objects.create(name="Form 1", academic_year=1999)

    with pytest.raises(IntegrityError):
        Cohort.objects.create(name="Form 1", academic_year=2101)
