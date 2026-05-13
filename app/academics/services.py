from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

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
from core.models import CustomUser
from tenant.models import School


def _save_clean(instance: Any) -> Any:
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_academic_year(
    *,
    tenant: School,
    label: str,
    start_date: str,
    end_date: str,
    is_active: bool = True,
) -> AcademicYear:
    return _save_clean(
        AcademicYear(
            tenant=tenant,
            label=label,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_term(
    *,
    tenant: School,
    academic_year: AcademicYear,
    code: str,
    name: str,
    start_date: str,
    end_date: str,
    is_active: bool = True,
) -> Term:
    return _save_clean(
        Term(
            tenant=tenant,
            academic_year=academic_year,
            code=code,
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_grade_level(
    *,
    code: str,
    name: str,
    stage: str,
    is_active: bool = True,
) -> GradeLevel:
    return _save_clean(
        GradeLevel(code=code, name=name, stage=stage, is_active=is_active)
    )


@transaction.atomic
def create_learning_area(
    *,
    tenant: School,
    grade_level: GradeLevel,
    code: str,
    name: str,
    is_active: bool = True,
) -> LearningArea:
    return _save_clean(
        LearningArea(
            tenant=tenant,
            grade_level=grade_level,
            code=code,
            name=name,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_cohort(
    *,
    tenant: School,
    academic_year: AcademicYear,
    grade_level: GradeLevel,
    name: str,
    stream_label: str = "",
    is_active: bool = True,
) -> Cohort:
    return _save_clean(
        Cohort(
            tenant=tenant,
            academic_year=academic_year,
            grade_level=grade_level,
            name=name,
            stream_label=stream_label,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_learner(
    *,
    tenant: School,
    admission_number: str,
    first_name: str,
    last_name: str,
    is_active: bool = True,
) -> Student:
    return _save_clean(
        Student(
            tenant=tenant,
            admission_number=admission_number,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
        )
    )


@transaction.atomic
def enroll_learner(
    *,
    tenant: School,
    learner: Student,
    cohort: Cohort,
    academic_year: AcademicYear,
    term: Term,
    is_active: bool = True,
) -> Enrollment:
    if learner.tenant_id != tenant.id:
        raise ValidationError("Enrollment is invalid.")
    return _save_clean(
        Enrollment(
            tenant=tenant,
            student=learner,
            cohort=cohort,
            academic_year=academic_year,
            term=term,
            is_active=is_active,
        )
    )


@transaction.atomic
def assign_teacher_to_learning_area(
    *,
    tenant: School,
    teacher: CustomUser,
    cohort: Cohort,
    learning_area: LearningArea,
    academic_year: AcademicYear,
    term: Term,
    is_active: bool = True,
) -> TeacherAssignment:
    return _save_clean(
        TeacherAssignment(
            tenant=tenant,
            teacher=teacher,
            cohort=cohort,
            learning_area=learning_area,
            academic_year=academic_year,
            term=term,
            is_active=is_active,
        )
    )
