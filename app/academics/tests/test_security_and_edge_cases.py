import uuid

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

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
from academics.policies import (
    can_assign_teacher,
    can_teacher_access_learning_area,
    can_view_cohort_roster,
)
from academics.selectors import (
    get_cohort_roster,
    get_tenant_scoped_learner_by_id,
)
from academics.services import (
    assign_teacher_to_learning_area,
    create_academic_year,
    create_term,
    enroll_learner,
)
from core.models import TenantUserRole
from core.policies import PolicyContext


pytestmark = [pytest.mark.django_db, pytest.mark.phase3]


def test_academics_migration_and_uuid_primary_keys_exist(
    academic_year,
    app_root,
    cohort,
    enrollment,
    grade_level,
    learning_area,
    student,
    teacher_assignment,
    term,
):
    assert (app_root / "academics" / "migrations" / "0001_initial.py").exists()

    for model_instance in [
        academic_year,
        term,
        grade_level,
        learning_area,
        cohort,
        student,
        enrollment,
        teacher_assignment,
    ]:
        assert isinstance(model_instance.pk, uuid.UUID)


def test_cbe_structure_links_grade_learning_area_cohort_and_year(
    academic_year,
    cohort,
    grade_level,
    learning_area,
    school,
):
    assert grade_level.stage == GradeLevel.Stage.PRIMARY
    assert learning_area.tenant == school
    assert learning_area.grade_level == grade_level
    assert cohort.tenant == school
    assert cohort.grade_level == grade_level
    assert cohort.academic_year == academic_year


def test_invalid_academic_year_and_term_dates_fail_closed(school):
    with pytest.raises(ValidationError):
        create_academic_year(
            tenant=school,
            label="Bad Year",
            start_date="2026-12-31",
            end_date="2026-01-01",
        )

    year = create_academic_year(
        tenant=school,
        label="Valid Year",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )

    with pytest.raises(ValidationError):
        create_term(
            tenant=school,
            academic_year=year,
            code=Term.TermCode.TERM_1,
            name="Outside",
            start_date="2025-12-01",
            end_date="2026-02-01",
        )


def test_tenant_scoped_uniqueness_constraints(
    academic_year,
    cohort,
    enrollment,
    grade_level,
    learning_area,
    school,
    student,
    teacher_assignment,
    teacher_user,
    term,
):
    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            AcademicYear.objects.create(
                tenant=school,
                label=academic_year.label,
                start_date=academic_year.start_date,
                end_date=academic_year.end_date,
            )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            LearningArea.objects.create(
                tenant=school,
                grade_level=grade_level,
                code=learning_area.code,
                name="Duplicate Learning Area",
            )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            Cohort.objects.create(
                tenant=school,
                academic_year=academic_year,
                grade_level=grade_level,
                name=cohort.name,
            )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            Student.objects.create(
                tenant=school,
                admission_number=student.admission_number,
                first_name="Other",
                last_name="Learner",
            )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            Enrollment.objects.create(
                tenant=school,
                student=student,
                cohort=cohort,
                academic_year=academic_year,
                term=term,
            )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            TeacherAssignment.objects.create(
                tenant=school,
                teacher=teacher_user,
                cohort=cohort,
                learning_area=learning_area,
                academic_year=academic_year,
                term=term,
            )


def test_cross_tenant_enrollment_and_assignment_are_rejected(
    academic_year,
    cohort,
    learning_area,
    other_school,
    school,
    student_factory,
    teacher_user,
    term,
):
    other_student = student_factory(tenant=other_school)

    with pytest.raises(ValidationError):
        enroll_learner(
            tenant=school,
            learner=other_student,
            cohort=cohort,
            academic_year=academic_year,
            term=term,
        )

    with pytest.raises(ValidationError):
        assign_teacher_to_learning_area(
            tenant=other_school,
            teacher=teacher_user,
            cohort=cohort,
            learning_area=learning_area,
            academic_year=academic_year,
            term=term,
        )


def test_teacher_cannot_view_unassigned_or_cross_tenant_roster(
    cohort,
    enrollment_factory,
    learning_area,
    school,
    teacher_user,
):
    enrollment_factory.create_batch(3, tenant=school, cohort=cohort)

    with pytest.raises(PermissionDenied):
        get_cohort_roster(
            tenant=school,
            actor=teacher_user,
            cohort=cohort,
            learning_area=learning_area,
        )


def test_roster_excludes_inactive_learners(
    cohort,
    enrollment_factory,
    learning_area,
    school,
    student_factory,
    teacher_assignment_factory,
    teacher_user,
):
    teacher_assignment_factory(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
    )

    active_student = student_factory(tenant=school, is_active=True)
    enrollment_factory(tenant=school, student=active_student, cohort=cohort)

    inactive_student = student_factory(tenant=school, is_active=False)
    enrollment_factory(tenant=school, student=inactive_student, cohort=cohort)

    roster = get_cohort_roster(
        tenant=school,
        actor=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
    )

    assert len(roster) == 1
    assert roster[0]["id"] == str(active_student.id)


def test_academic_abac_fails_closed_for_missing_context(
    cohort,
    learning_area,
    principal_role,
    principal_user,
    school,
):
    assert not can_view_cohort_roster(
        PolicyContext(
            tenant=None,
            actor=principal_user,
            action="academics.view_roster",
            role=principal_role,
        ),
        cohort=cohort,
        learning_area=learning_area,
    )
    assert not can_assign_teacher(
        PolicyContext(
            tenant=school,
            actor=None,
            action="academics.assign_teacher",
            role=principal_role,
        ),
        cohort=cohort,
    )


def test_academic_abac_allows_admin_only_inside_tenant(
    cohort,
    learning_area,
    other_cohort,
    principal_role,
    principal_user,
    school,
):
    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="academics.assign_teacher",
        role=principal_role,
    )

    assert can_assign_teacher(context, cohort=cohort)
    assert not can_assign_teacher(context, cohort=other_cohort)
    assert can_view_cohort_roster(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )


def test_teacher_assignment_abac_requires_active_assignment(
    cohort,
    learning_area,
    school,
    subject_teacher_role,
    teacher_assignment_factory,
    teacher_user,
):
    context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="academics.view_roster",
        role=subject_teacher_role,
    )

    assert not can_teacher_access_learning_area(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )

    assignment = teacher_assignment_factory(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
    )

    assert can_teacher_access_learning_area(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )

    assignment.is_active = False
    assignment.save()

    assert not can_teacher_access_learning_area(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )


def test_inactive_role_binding_denies_academic_access(
    cohort,
    learning_area,
    school,
    subject_teacher_role,
    teacher_user,
):
    TenantUserRole.objects.filter(
        tenant=school,
        user=teacher_user,
        role=subject_teacher_role,
    ).update(is_active=False)

    assert not can_teacher_access_learning_area(
        PolicyContext(
            tenant=school,
            actor=teacher_user,
            action="academics.view_roster",
            role=subject_teacher_role,
        ),
        cohort=cohort,
        learning_area=learning_area,
    )


def test_invalid_learner_lookup_fails_without_existence_leak(student, school):
    assert get_tenant_scoped_learner_by_id(
        tenant=school,
        learner_id="not-a-uuid",
    ) is None
    assert get_tenant_scoped_learner_by_id(
        tenant=school,
        learner_id=student.id,
    ) == student
