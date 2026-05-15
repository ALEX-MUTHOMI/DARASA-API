"""Tenant-aware read paths for grading records."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import models
from django.db.models import QuerySet

from grading.models import (
    Assessment,
    GradeDraftBatch,
    GradeCorrectionRequest,
    GradeRecord,
    GradeSubmissionBatch,
)


def _safe_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def get_teacher_grading_contexts(
    *,
    actor: Any,
    tenant: Any,
    academic_year: Any | None = None,
    term: Any | None = None,
) -> QuerySet[Assessment]:
    if actor is None or tenant is None:
        return Assessment.objects.none()
    queryset = Assessment.objects.filter(
        tenant=tenant,
        status=Assessment.Status.OPEN,
        curriculum_version__isnull=False,
        rubric_foundation__isnull=False,
        curriculum_binding_locked_at__isnull=False,
        cohort__is_active=True,
        learning_area__is_active=True,
        cohort__teacher_assignments__teacher=actor,
        cohort__teacher_assignments__learning_area=models.F("learning_area"),
        cohort__teacher_assignments__academic_year=models.F("academic_year"),
        cohort__teacher_assignments__term=models.F("term"),
        cohort__teacher_assignments__is_active=True,
    ).select_related(
        "cohort",
        "learning_area",
        "academic_year",
        "term",
        "curriculum_version",
        "rubric_foundation",
    )
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)
    if term is not None:
        queryset = queryset.filter(term=term)
    return queryset.distinct()


def get_assessment_for_teacher(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
) -> Assessment | None:
    assessment_uuid = _safe_uuid(assessment_id)
    if actor is None or tenant is None or assessment_uuid is None:
        return None
    return (
        Assessment.objects.filter(
            id=assessment_uuid,
            tenant=tenant,
            status=Assessment.Status.OPEN,
            curriculum_version__isnull=False,
            rubric_foundation__isnull=False,
            curriculum_binding_locked_at__isnull=False,
            cohort__teacher_assignments__teacher=actor,
            cohort__teacher_assignments__learning_area=models.F("learning_area"),
            cohort__teacher_assignments__academic_year=models.F("academic_year"),
            cohort__teacher_assignments__term=models.F("term"),
            cohort__teacher_assignments__is_active=True,
        )
        .select_related(
            "cohort",
            "learning_area",
            "academic_year",
            "term",
            "curriculum_version",
            "rubric_foundation",
        )
        .first()
    )


def get_grade_records_for_assessment(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
) -> QuerySet[GradeRecord]:
    assessment = get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )
    if assessment is None:
        return GradeRecord.objects.none()
    return GradeRecord.objects.filter(
        tenant=tenant,
        assessment=assessment,
    ).select_related("student", "assessment", "submission_batch")


def get_submission_batches_for_assessment(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
) -> QuerySet[GradeSubmissionBatch]:
    assessment = get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )
    if assessment is None:
        return GradeSubmissionBatch.objects.none()
    return GradeSubmissionBatch.objects.filter(
        tenant=tenant,
        assessment=assessment,
    ).select_related("teacher", "teacher_assignment", "cohort", "learning_area")


def get_grade_grid_context(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
) -> Assessment | None:
    return get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )


def get_roster_for_assessment(*, tenant: Any, assessment: Assessment) -> QuerySet[Any]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        from academics.models import Student

        return Student.objects.none()
    from academics.models import Student

    return (
        Student.objects.filter(
            tenant=tenant,
            enrollments__tenant=tenant,
            enrollments__cohort=assessment.cohort,
            enrollments__academic_year=assessment.academic_year,
            enrollments__term=assessment.term,
            enrollments__is_active=True,
            is_active=True,
        )
        .order_by("admission_number", "last_name", "first_name", "id")
        .distinct()
    )


def get_existing_draft_for_teacher(
    *,
    actor: Any,
    tenant: Any,
    assessment: Assessment,
) -> GradeDraftBatch | None:
    if actor is None or tenant is None or assessment is None:
        return None
    return (
        GradeDraftBatch.objects.filter(
            tenant=tenant,
            assessment=assessment,
            teacher=actor,
            status=GradeDraftBatch.Status.DRAFT,
        )
        .select_related("assessment", "teacher_assignment", "cohort", "learning_area")
        .prefetch_related("rows")
        .first()
    )


def get_existing_submission_for_assessment(
    *,
    actor: Any,
    tenant: Any,
    assessment: Assessment,
) -> GradeSubmissionBatch | None:
    if actor is None or tenant is None or assessment is None:
        return None
    return (
        GradeSubmissionBatch.objects.filter(
            tenant=tenant,
            assessment=assessment,
            teacher=actor,
            status__in=[
                GradeSubmissionBatch.Status.SUBMITTED,
                GradeSubmissionBatch.Status.VALIDATED,
                GradeSubmissionBatch.Status.COMPILED,
            ],
        )
        .select_related("assessment", "teacher_assignment", "cohort", "learning_area")
        .first()
    )


def get_pending_corrections_for_reviewer(
    *,
    actor: Any,
    tenant: Any,
) -> QuerySet[GradeCorrectionRequest]:
    if actor is None or tenant is None:
        return GradeCorrectionRequest.objects.none()
    return GradeCorrectionRequest.objects.filter(
        tenant=tenant,
        status=GradeCorrectionRequest.Status.REQUESTED,
    ).select_related("grade_record", "requested_by")
