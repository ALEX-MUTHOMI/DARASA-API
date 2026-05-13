from __future__ import annotations

import pathlib
import uuid

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
from tenant.models import School


@pytest.fixture
def app_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _token() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def school() -> School:
    token = _token()
    return School.objects.create(
        name=f"Phase 3 School {token}",
        schema_name=f"p3_{token}",
        subdomain=f"p3-{token}",
        school_code=f"P3S{token[:7]}".upper(),
    )


@pytest.fixture
def other_school() -> School:
    token = _token()
    return School.objects.create(
        name=f"Other Phase 3 School {token}",
        schema_name=f"op3_{token}",
        subdomain=f"op3-{token}",
        school_code=f"OP3{token[:7]}".upper(),
    )


@pytest.fixture
def principal_role() -> Role:
    return Role.objects.create(
        code=Role.RoleCode.PRINCIPAL,
        name=Role.RoleCode.PRINCIPAL.label,
    )


@pytest.fixture
def subject_teacher_role() -> Role:
    return Role.objects.create(
        code=Role.RoleCode.SUBJECT_TEACHER,
        name=Role.RoleCode.SUBJECT_TEACHER.label,
    )


@pytest.fixture
def principal_user(school, principal_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"principal-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=principal_role)
    return user


@pytest.fixture
def teacher_user(school, subject_teacher_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"teacher-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(
        tenant=school,
        user=user,
        role=subject_teacher_role,
    )
    return user


@pytest.fixture
def academic_year(school) -> AcademicYear:
    return AcademicYear.objects.create(
        tenant=school,
        label=f"AY-{_token()}",
        start_date="2026-01-01",
        end_date="2026-12-31",
        is_active=True,
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
        is_active=True,
    )


@pytest.fixture
def grade_level() -> GradeLevel:
    return GradeLevel.objects.create(
        code=f"grade-{_token()}",
        name="Grade 4",
        stage=GradeLevel.Stage.PRIMARY,
    )


@pytest.fixture
def learning_area(school, grade_level) -> LearningArea:
    return LearningArea.objects.create(
        tenant=school,
        grade_level=grade_level,
        code=f"la-{_token()}",
        name="Integrated Science",
    )


@pytest.fixture
def subject(learning_area) -> LearningArea:
    return learning_area


@pytest.fixture
def cohort(school, academic_year, grade_level) -> Cohort:
    return Cohort.objects.create(
        tenant=school,
        academic_year=academic_year,
        grade_level=grade_level,
        name=f"North-{_token()}",
        stream_label="North",
    )


@pytest.fixture
def other_cohort(other_school, grade_level) -> Cohort:
    token = _token()
    other_year = AcademicYear.objects.create(
        tenant=other_school,
        label=f"AY-{token}",
        start_date="2026-01-01",
        end_date="2026-12-31",
        is_active=True,
    )
    return Cohort.objects.create(
        tenant=other_school,
        academic_year=other_year,
        grade_level=grade_level,
        name=f"Other-{token}",
    )


@pytest.fixture
def student_factory(school):
    class StudentFactory:
        def __call__(self, **overrides):
            token = _token()
            defaults = {
                "tenant": school,
                "admission_number": f"ADM{token}".upper(),
                "first_name": "Test",
                "last_name": "Learner",
                "is_active": True,
            }
            defaults.update(overrides)
            return Student.objects.create(**defaults)

    return StudentFactory()


@pytest.fixture
def student(student_factory) -> Student:
    return student_factory()


@pytest.fixture
def enrollment_factory(school, academic_year, cohort, term):
    class EnrollmentFactory:
        def __call__(self, **overrides):
            defaults = {
                "tenant": school,
                "student": None,
                "cohort": cohort,
                "academic_year": academic_year,
                "term": term,
            }
            defaults.update(overrides)
            if defaults["student"] is None:
                defaults["student"] = Student.objects.create(
                    tenant=defaults["tenant"],
                    admission_number=f"ADM{_token()}".upper(),
                    first_name="Test",
                    last_name="Learner",
                )
            return Enrollment.objects.create(**defaults)

        def create_batch(self, count: int, **overrides):
            return [self(**overrides) for _ in range(count)]

    return EnrollmentFactory()


@pytest.fixture
def enrollment(enrollment_factory, student) -> Enrollment:
    return enrollment_factory(student=student)


@pytest.fixture
def teacher_assignment_factory(
    school,
    academic_year,
    cohort,
    learning_area,
    teacher_user,
    term,
):
    class TeacherAssignmentFactory:
        def __call__(self, **overrides):
            defaults = {
                "tenant": school,
                "teacher": teacher_user,
                "cohort": cohort,
                "learning_area": learning_area,
                "academic_year": academic_year,
                "term": term,
            }
            defaults.update(overrides)
            return TeacherAssignment.objects.create(**defaults)

    return TeacherAssignmentFactory()


@pytest.fixture
def teacher_assignment(teacher_assignment_factory) -> TeacherAssignment:
    return teacher_assignment_factory()
