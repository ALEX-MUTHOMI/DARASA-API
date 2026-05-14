from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from academics.models import (
    AcademicYear,
    Cohort,
    Enrollment,
    GradeLevel,
    LearningArea,
    Student,
    TeacherAssignment,
    Term,
)
from core.models import CustomUser, Role, TenantUserRole
from grading.models import Assessment
from tenant.models import School


def _token() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def school() -> School:
    token = _token()
    return School.objects.create(
        name=f"Phase 6A School {token}",
        schema_name=f"p6a_{token}",
        subdomain=f"p6a-{token}",
        school_code=f"P6A{token[:7]}".upper(),
    )


@pytest.fixture
def other_school() -> School:
    token = _token()
    return School.objects.create(
        name=f"Other Phase 6A School {token}",
        schema_name=f"op6a_{token}",
        subdomain=f"op6a-{token}",
        school_code=f"Q6A{token[:7]}".upper(),
    )


@pytest.fixture
def subject_teacher_role() -> Role:
    return Role.objects.get_or_create(
        code=Role.RoleCode.SUBJECT_TEACHER,
        defaults={"name": Role.RoleCode.SUBJECT_TEACHER.label},
    )[0]


@pytest.fixture
def principal_role() -> Role:
    return Role.objects.get_or_create(
        code=Role.RoleCode.PRINCIPAL,
        defaults={"name": Role.RoleCode.PRINCIPAL.label},
    )[0]


@pytest.fixture
def teacher_user(school, subject_teacher_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"p6a-teacher-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=subject_teacher_role)
    return user


@pytest.fixture
def principal_user(school, principal_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"p6a-principal-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=principal_role)
    return user


@pytest.fixture
def academic_year(school) -> AcademicYear:
    return AcademicYear.objects.create(
        tenant=school,
        label=f"AY-{_token()}",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )


@pytest.fixture
def term(school, academic_year) -> Term:
    return Term.objects.create(
        tenant=school,
        academic_year=academic_year,
        code=Term.TermCode.TERM_1,
        name="Term 1",
        start_date="2026-01-01",
        end_date="2026-04-01",
    )


@pytest.fixture
def grade_level() -> GradeLevel:
    return GradeLevel.objects.create(
        code=f"grade-{_token()}",
        name="Grade 10",
        stage=GradeLevel.Stage.SENIOR_SCHOOL,
    )


@pytest.fixture
def cohort(school, academic_year, grade_level) -> Cohort:
    return Cohort.objects.create(
        tenant=school,
        academic_year=academic_year,
        grade_level=grade_level,
        name=f"West-{_token()}",
    )


@pytest.fixture
def other_cohort(other_school, grade_level) -> Cohort:
    token = _token()
    other_year = AcademicYear.objects.create(
        tenant=other_school,
        label=f"AY-{token}",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )
    return Cohort.objects.create(
        tenant=other_school,
        academic_year=other_year,
        grade_level=grade_level,
        name=f"East-{token}",
    )


@pytest.fixture
def learning_area(school, grade_level) -> LearningArea:
    return LearningArea.objects.create(
        tenant=school,
        grade_level=grade_level,
        code=f"computer-{_token()}",
        name="Computer Studies",
    )


@pytest.fixture
def other_learning_area(other_school, grade_level) -> LearningArea:
    return LearningArea.objects.create(
        tenant=other_school,
        grade_level=grade_level,
        code=f"computer-{_token()}",
        name="Computer Studies",
    )


@pytest.fixture
def assessment(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    learning_area,
    principal_user,
) -> Assessment:
    return Assessment.objects.create(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=learning_area,
        title=f"Assessment {_token()}",
        max_score=Decimal("100.00"),
        status=Assessment.Status.OPEN,
        created_by=principal_user,
    )


@pytest.fixture
def teacher_assignment(
    school,
    teacher_user,
    cohort,
    learning_area,
    academic_year,
    term,
) -> TeacherAssignment:
    return TeacherAssignment.objects.create(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
        academic_year=academic_year,
        term=term,
    )


@pytest.fixture
def student(school) -> Student:
    return Student.objects.create(
        tenant=school,
        admission_number=f"ADM{_token()}".upper(),
        first_name="Test",
        last_name="Learner",
    )


@pytest.fixture
def enrolled_student(student, school, cohort, academic_year, term) -> Student:
    Enrollment.objects.create(
        tenant=school,
        student=student,
        cohort=cohort,
        academic_year=academic_year,
        term=term,
    )
    return student
