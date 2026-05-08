from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from academics.models import (
    AcademicYear,
    Cohort,
    Enrollment,
    LearningArea,
    Student,
    TeacherAssignment,
    Term,
)
from core.models import CustomUser
from tenant.models import School


def get_active_academic_year_for_tenant(*, tenant: School) -> AcademicYear | None:
    return AcademicYear.objects.filter(tenant=tenant, is_active=True).first()


def get_active_terms_for_tenant(*, tenant: School) -> QuerySet[Term]:
    return Term.objects.filter(
        tenant=tenant,
        is_active=True,
        academic_year__is_active=True,
    ).select_related("academic_year")


def verify_teacher_assignment(
    *,
    tenant: School,
    teacher: CustomUser,
    cohort: Cohort,
    learning_area: LearningArea,
) -> bool:
    return TeacherAssignment.objects.filter(
        tenant=tenant,
        teacher=teacher,
        cohort=cohort,
        learning_area=learning_area,
        is_active=True,
        cohort__is_active=True,
        learning_area__is_active=True,
    ).exists()


def get_teacher_assignments(
    *,
    tenant: School,
    teacher: CustomUser,
) -> QuerySet[TeacherAssignment]:
    return TeacherAssignment.objects.filter(
        tenant=tenant,
        teacher=teacher,
        is_active=True,
        cohort__is_active=True,
        learning_area__is_active=True,
    ).select_related("cohort", "learning_area", "academic_year", "term")


def get_learning_areas_assigned_to_teacher(
    *,
    tenant: School,
    teacher: CustomUser,
) -> QuerySet[LearningArea]:
    area_ids = get_teacher_assignments(
        tenant=tenant,
        teacher=teacher,
    ).values("learning_area_id")
    return LearningArea.objects.filter(
        tenant=tenant,
        id__in=area_ids,
        is_active=True,
    )


def get_cohort_roster(
    *,
    tenant: School,
    actor: CustomUser,
    cohort: Cohort,
    learning_area: LearningArea,
) -> list[dict[str, Any]]:
    if not verify_teacher_assignment(
        tenant=tenant,
        teacher=actor,
        cohort=cohort,
        learning_area=learning_area,
    ):
        raise PermissionDenied("Access denied.")

    roster = (
        Enrollment.objects.filter(
            tenant=tenant,
            cohort=cohort,
            is_active=True,
            student__is_active=True,
            student__tenant=tenant,
        )
        .order_by("student__last_name", "student__first_name")
        .values(
            "student__id",
            "student__first_name",
            "student__last_name",
            "student__admission_number",
        )
    )

    return [
        {
            "id": str(row["student__id"]),
            "first_name": row["student__first_name"],
            "last_name": row["student__last_name"],
            "admission_number": row["student__admission_number"],
        }
        for row in roster
    ]


def get_fast_grid_roster(
    teacher_user: CustomUser,
    cohort_uuid: str | UUID,
    subject_uuid: str | UUID,
) -> list[dict[str, Any]]:
    assignment = (
        TeacherAssignment.objects.filter(
            teacher=teacher_user,
            cohort_id=cohort_uuid,
            learning_area_id=subject_uuid,
            is_active=True,
            tenant__is_active=True,
        )
        .select_related("tenant", "cohort", "learning_area")
        .first()
    )
    if assignment is None:
        raise PermissionDenied("Access denied.")
    return get_cohort_roster(
        tenant=assignment.tenant,
        actor=teacher_user,
        cohort=assignment.cohort,
        learning_area=assignment.learning_area,
    )


def get_tenant_scoped_learner_by_id(
    *,
    tenant: School,
    learner_id: str | UUID,
) -> Student | None:
    try:
        learner_uuid = UUID(str(learner_id))
    except (TypeError, ValueError):
        return None
    return Student.objects.filter(
        tenant=tenant,
        id=learner_uuid,
        is_active=True,
    ).first()


def get_tenant_scoped_learner_by_admission_number(
    *,
    tenant: School,
    admission_number: str,
) -> Student | None:
    normalized = (admission_number or "").strip().upper()
    if not normalized:
        return None
    return Student.objects.filter(
        tenant=tenant,
        admission_number=normalized,
        is_active=True,
    ).first()
