"""Tenant-aware read paths for grading records."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import models
from django.db.models import QuerySet

from curriculum.models import (
    CurriculumAppImpactPlan,
    CurriculumRollbackPlan,
    CurriculumVersionWithdrawal,
    SchoolCurriculumAdoption,
)
from grading.models import (
    AcademicAggregate,
    Assessment,
    AssessmentComponent,
    CompilationRun,
    CompiledCohortSummary,
    CompiledLearnerSnapshot,
    GradeDraftBatch,
    GradeCorrectionRequest,
    GradeCorrectionAuditRecord,
    GradeRecord,
    GradeSubmissionBatch,
    LearnerReportSnapshot,
    ReportSnapshotRun,
    ReportSubjectLineSnapshot,
    SchoolGradingBand,
    SchoolGradingSchema,
)
from grading.algorithms.correction_status import BLOCKING_CORRECTION_STATUSES


def _safe_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


READINESS_CCT_APP_DOMAINS = frozenset(
    {
        "academics",
        "assessments",
        "examinations",
        "grading",
        "compilation",
        "reports_future",
    }
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _scope_matches_any(value: Any, candidates: list[Any]) -> bool:
    expected = _normalized_text(value)
    if not expected:
        return True
    return expected in {_normalized_text(candidate) for candidate in candidates}


def _metadata_scope_matches(*, tenant: Any, scope: dict[str, Any]) -> bool:
    metadata = getattr(tenant, "metadata", {}) or {}
    for key in [
        "region",
        "county",
        "sub_county",
        "school_category",
        "senior_school_pathway",
    ]:
        if scope.get(key) and not _scope_matches_any(scope[key], [metadata.get(key)]):
            return False
    return True


def _impact_scope_applies_to_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
    scope: dict[str, Any] | None,
) -> bool:
    if not scope:
        return True
    if _normalized_text(scope.get("scope_type")) == "scope_unknown":
        return True
    if not _metadata_scope_matches(tenant=tenant, scope=scope):
        return False
    if scope.get("grade_level") and not _scope_matches_any(
        scope["grade_level"],
        [
            assessment.grade_level_id,
            getattr(assessment.grade_level, "code", ""),
            getattr(assessment.grade_level, "name", ""),
        ],
    ):
        return False
    if scope.get("learning_area") and not _scope_matches_any(
        scope["learning_area"],
        [
            assessment.learning_area_id,
            getattr(assessment.learning_area, "code", ""),
            getattr(assessment.learning_area, "name", ""),
        ],
    ):
        return False
    if scope.get("rubric") and not _scope_matches_any(
        scope["rubric"],
        [
            assessment.rubric_foundation_id,
            getattr(assessment.rubric_foundation, "level_code", ""),
            getattr(assessment.rubric_foundation, "level_label", ""),
        ],
    ):
        return False
    return True


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
        status__in=[
            GradeCorrectionRequest.Status.REQUESTED,
            GradeCorrectionRequest.Status.SUBMITTED,
            GradeCorrectionRequest.Status.UNDER_HOD_REVIEW,
        ],
    ).select_related("grade_record", "grade_record__assessment", "requested_by")


def get_submitted_records_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[GradeRecord]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return GradeRecord.objects.none()
    return (
        GradeRecord.objects.filter(
            tenant=tenant,
            assessment=assessment,
            submission_batch__status=GradeSubmissionBatch.Status.SUBMITTED,
        )
        .select_related("student", "assessment", "submission_batch")
        .order_by("student__admission_number", "student_id")
    )


def get_expected_roster_for_compilation(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[Any]:
    return get_roster_for_assessment(tenant=tenant, assessment=assessment)


def get_assessment_components_for_compilation(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[AssessmentComponent]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return AssessmentComponent.objects.none()
    return AssessmentComponent.objects.filter(
        tenant=tenant,
        assessment=assessment,
    ).order_by("order", "name")


def get_latest_compilation_run(
    *,
    tenant: Any,
    assessment: Assessment,
) -> CompilationRun | None:
    if tenant is None or assessment is None:
        return None
    return (
        CompilationRun.objects.filter(tenant=tenant, assessment=assessment)
        .order_by(
            "-created_at",
            models.F("compiled_at").desc(nulls_last=True),
            "-id",
        )
        .first()
    )


def get_latest_compilation_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> CompilationRun | None:
    return get_latest_compilation_run(tenant=tenant, assessment=assessment)


def get_assessment_readiness_scope(
    *,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[Assessment]:
    if tenant is None:
        return Assessment.objects.none()
    queryset = Assessment.objects.filter(tenant=tenant).select_related(
        "cohort",
        "learning_area",
        "academic_year",
        "term",
        "curriculum_version",
        "rubric_foundation",
    )
    filters = filters or {}
    for field in ["academic_year_id", "term_id", "cohort_id", "learning_area_id"]:
        if filters.get(field):
            queryset = queryset.filter(**{field: filters[field]})
    return queryset.order_by("cohort__name", "learning_area__name", "title")


def get_teacher_readiness_scope(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any | None = None,
) -> QuerySet[Assessment]:
    if actor is None or tenant is None:
        return Assessment.objects.none()
    queryset = get_assessment_readiness_scope(tenant=tenant).filter(
        cohort__teacher_assignments__teacher=actor,
        cohort__teacher_assignments__learning_area=models.F("learning_area"),
        cohort__teacher_assignments__academic_year=models.F("academic_year"),
        cohort__teacher_assignments__term=models.F("term"),
        cohort__teacher_assignments__is_active=True,
    )
    if assessment_id is not None:
        assessment_uuid = _safe_uuid(assessment_id)
        if assessment_uuid is None:
            return Assessment.objects.none()
        queryset = queryset.filter(id=assessment_uuid)
    return queryset.distinct()


def get_hod_readiness_scope(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[Assessment]:
    if actor is None or tenant is None:
        return Assessment.objects.none()
    queryset = get_teacher_readiness_scope(actor=actor, tenant=tenant)
    learning_area_id = (filters or {}).get("learning_area_id")
    if learning_area_id:
        queryset = queryset.filter(learning_area_id=learning_area_id)
    return queryset


def get_academic_head_readiness_scope(
    *,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[Assessment]:
    return get_assessment_readiness_scope(tenant=tenant, filters=filters)


def get_principal_readiness_scope(
    *,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[Assessment]:
    return get_assessment_readiness_scope(tenant=tenant, filters=filters)


def get_readiness_batches_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[GradeSubmissionBatch]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return GradeSubmissionBatch.objects.none()
    return GradeSubmissionBatch.objects.filter(
        tenant=tenant,
        assessment=assessment,
    ).order_by("-submitted_at", "-created_at")


def get_readiness_drafts_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[GradeDraftBatch]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return GradeDraftBatch.objects.none()
    return GradeDraftBatch.objects.filter(
        tenant=tenant,
        assessment=assessment,
        status=GradeDraftBatch.Status.DRAFT,
    ).order_by("-updated_at")


def get_pending_corrections_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[GradeCorrectionRequest]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return GradeCorrectionRequest.objects.none()
    return GradeCorrectionRequest.objects.filter(
        tenant=tenant,
        grade_record__assessment=assessment,
        status__in=BLOCKING_CORRECTION_STATUSES,
    ).order_by("-requested_at")


def get_teacher_correction_requests(
    *,
    actor: Any,
    tenant: Any,
) -> QuerySet[GradeCorrectionRequest]:
    if actor is None or tenant is None:
        return GradeCorrectionRequest.objects.none()
    return (
        GradeCorrectionRequest.objects.filter(tenant=tenant, requested_by=actor)
        .select_related("grade_record", "grade_record__assessment", "reviewed_by")
        .order_by("-requested_at")
    )


def get_hod_correction_queue(
    *,
    actor: Any,
    tenant: Any,
) -> QuerySet[GradeCorrectionRequest]:
    if actor is None or tenant is None:
        return GradeCorrectionRequest.objects.none()
    return (
        get_pending_corrections_for_reviewer(actor=actor, tenant=tenant)
        .filter(
            grade_record__assessment__cohort__teacher_assignments__teacher=actor,
            **{
                (
                    "grade_record__assessment__cohort__teacher_assignments__"
                    "learning_area"
                ): models.F("grade_record__assessment__learning_area"),
                (
                    "grade_record__assessment__cohort__teacher_assignments__"
                    "academic_year"
                ): models.F("grade_record__assessment__academic_year"),
            },
            grade_record__assessment__cohort__teacher_assignments__term=models.F(
                "grade_record__assessment__term"
            ),
            grade_record__assessment__cohort__teacher_assignments__is_active=True,
        )
        .distinct()
    )


def get_academic_head_correction_queue(
    *,
    tenant: Any,
) -> QuerySet[GradeCorrectionRequest]:
    if tenant is None:
        return GradeCorrectionRequest.objects.none()
    return (
        GradeCorrectionRequest.objects.filter(
            tenant=tenant,
            status__in=[
                GradeCorrectionRequest.Status.ESCALATION_REQUESTED,
                GradeCorrectionRequest.Status.UNDER_ACADEMIC_HEAD_REVIEW,
            ],
        )
        .select_related("grade_record", "grade_record__assessment", "requested_by")
        .order_by("-escalated_at", "-requested_at")
    )


def get_correction_audit_trail(
    *,
    tenant: Any,
    correction_request: GradeCorrectionRequest,
) -> QuerySet[GradeCorrectionAuditRecord]:
    if (
        tenant is None
        or correction_request is None
        or correction_request.tenant_id != tenant.id
    ):
        return GradeCorrectionAuditRecord.objects.none()
    return GradeCorrectionAuditRecord.objects.filter(
        tenant=tenant,
        correction_request=correction_request,
    ).order_by("created_at", "id")


def get_principal_correction_summary(*, tenant: Any) -> dict[str, int]:
    if tenant is None:
        return {"pending": 0, "escalated": 0, "approved_unapplied": 0}
    queryset = GradeCorrectionRequest.objects.filter(tenant=tenant)
    return {
        "pending": queryset.filter(status__in=BLOCKING_CORRECTION_STATUSES).count(),
        "escalated": queryset.filter(
            status__in=[
                GradeCorrectionRequest.Status.ESCALATION_REQUESTED,
                GradeCorrectionRequest.Status.UNDER_ACADEMIC_HEAD_REVIEW,
            ]
        ).count(),
        "approved_unapplied": queryset.filter(
            status__in=[
                GradeCorrectionRequest.Status.APPROVED,
                GradeCorrectionRequest.Status.APPROVED_BY_HOD,
                GradeCorrectionRequest.Status.APPROVED_BY_ACADEMIC_HEAD,
            ]
        ).count(),
    }


def get_active_school_grading_schema(
    *,
    tenant: Any,
    assessment_type: str,
) -> SchoolGradingSchema | None:
    if tenant is None:
        return None
    return (
        SchoolGradingSchema.objects.filter(
            tenant=tenant,
            assessment_type=assessment_type,
            status__in=[
                SchoolGradingSchema.Status.ACTIVE,
                SchoolGradingSchema.Status.LOCKED,
            ],
        )
        .order_by("-activated_at", "-created_at", "-id")
        .first()
    )


def get_assessment_schema_binding(
    *,
    tenant: Any,
    assessment: Assessment,
) -> SchoolGradingSchema | None:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return None
    return assessment.school_grading_schema


def get_schema_history_for_tenant(
    *,
    tenant: Any,
) -> QuerySet[SchoolGradingSchema]:
    if tenant is None:
        return SchoolGradingSchema.objects.none()
    return SchoolGradingSchema.objects.filter(tenant=tenant).order_by(
        "assessment_type",
        "-created_at",
    )


def get_schema_bands_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> QuerySet[SchoolGradingBand]:
    schema = get_assessment_schema_binding(tenant=tenant, assessment=assessment)
    if schema is None:
        return SchoolGradingBand.objects.none()
    return SchoolGradingBand.objects.filter(
        tenant=tenant,
        schema=schema,
    ).order_by("order", "min_percentage", "label")


def get_cct_blockers_for_assessment(
    *,
    tenant: Any,
    assessment: Assessment,
) -> dict[str, Any]:
    if tenant is None or assessment is None or assessment.tenant_id != tenant.id:
        return {
            "has_school_adoption": False,
            "curriculum_version_withdrawn": False,
            "rollback_plan_count": 0,
            "app_impact_plan_count": 0,
        }
    curriculum_version = assessment.curriculum_version
    if curriculum_version is None:
        return {
            "has_school_adoption": False,
            "curriculum_version_withdrawn": False,
            "rollback_plan_count": 0,
            "app_impact_plan_count": 0,
        }
    has_adoption = SchoolCurriculumAdoption.objects.filter(
        tenant=tenant,
        curriculum_version=curriculum_version,
        status__in=[
            SchoolCurriculumAdoption.Status.SCHEDULED,
            SchoolCurriculumAdoption.Status.ACTIVE,
        ],
    ).exists()
    withdrawn = CurriculumVersionWithdrawal.objects.filter(
        curriculum_version=curriculum_version,
        status=CurriculumVersionWithdrawal.Status.WITHDRAWN,
    ).exists()
    rollback_count = CurriculumRollbackPlan.objects.filter(
        tenant=tenant,
        withdrawn_version=curriculum_version,
    ).count()
    impact_plans = CurriculumAppImpactPlan.objects.filter(
        tenant=tenant,
        app_domain__in=READINESS_CCT_APP_DOMAINS,
        status__in=[
            CurriculumAppImpactPlan.Status.PLANNED,
            CurriculumAppImpactPlan.Status.REVIEW_REQUIRED,
        ],
    ).only("id", "affected_scope")
    impact_count = sum(
        1
        for plan in impact_plans
        if _impact_scope_applies_to_assessment(
            tenant=tenant,
            assessment=assessment,
            scope=plan.affected_scope,
        )
    )
    return {
        "has_school_adoption": has_adoption,
        "curriculum_version_withdrawn": withdrawn,
        "rollback_plan_count": rollback_count,
        "app_impact_plan_count": impact_count,
    }


def get_compiled_learner_snapshots(
    *,
    tenant: Any,
    assessment: Assessment | None = None,
    learner_id: Any | None = None,
) -> QuerySet[CompiledLearnerSnapshot]:
    if tenant is None:
        return CompiledLearnerSnapshot.objects.none()
    queryset = CompiledLearnerSnapshot.objects.filter(tenant=tenant).select_related(
        "assessment",
        "student",
        "cohort",
        "learning_area",
        "compilation_run",
    )
    if assessment is not None:
        queryset = queryset.filter(assessment=assessment)
    if learner_id is not None:
        queryset = queryset.filter(student_id=learner_id)
    return queryset.order_by("student__admission_number", "assessment_id")


def get_compiled_cohort_summary(
    *,
    tenant: Any,
    assessment: Assessment | None = None,
) -> QuerySet[CompiledCohortSummary]:
    if tenant is None:
        return CompiledCohortSummary.objects.none()
    queryset = CompiledCohortSummary.objects.filter(tenant=tenant).select_related(
        "assessment",
        "cohort",
        "learning_area",
        "compilation_run",
    )
    if assessment is not None:
        queryset = queryset.filter(assessment=assessment)
    return queryset.order_by("-compiled_at", "assessment_id")


def get_eligible_compilations_for_report_period(
    *,
    tenant: Any,
    academic_year: Any,
    term: Any,
    cohort_id: Any | None = None,
    learning_area_id: Any | None = None,
) -> QuerySet[CompilationRun]:
    if tenant is None or academic_year is None or term is None:
        return CompilationRun.objects.none()
    queryset = (
        CompilationRun.objects.filter(
            tenant=tenant,
            assessment__academic_year=academic_year,
            assessment__term=term,
            status=CompilationRun.Status.COMPLETE,
        )
        .select_related(
            "assessment",
            "assessment__academic_year",
            "assessment__term",
            "assessment__cohort",
            "assessment__learning_area",
            "assessment__curriculum_version",
            "assessment__rubric_foundation",
            "assessment__school_grading_schema",
        )
        .prefetch_related("learner_snapshots")
    )
    if cohort_id is not None:
        queryset = queryset.filter(assessment__cohort_id=cohort_id)
    if learning_area_id is not None:
        queryset = queryset.filter(assessment__learning_area_id=learning_area_id)
    return queryset.order_by(
        "assessment__cohort__name",
        "assessment__learning_area__name",
        "-compiled_at",
        "-created_at",
    )


def get_learner_report_snapshots(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun | None = None,
    cohort_id: Any | None = None,
    learner_id: Any | None = None,
) -> QuerySet[LearnerReportSnapshot]:
    if tenant is None:
        return LearnerReportSnapshot.objects.none()
    queryset = LearnerReportSnapshot.objects.filter(tenant=tenant).select_related(
        "snapshot_run",
        "student",
        "academic_year",
        "term",
        "cohort",
    )
    if snapshot_run is not None:
        queryset = queryset.filter(snapshot_run=snapshot_run)
    if cohort_id is not None:
        queryset = queryset.filter(cohort_id=cohort_id)
    if learner_id is not None:
        queryset = queryset.filter(student_id=learner_id)
    return queryset.order_by("-average_percentage", "student_id")


def get_report_subject_line_snapshots(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun | None = None,
    cohort_id: Any | None = None,
    learning_area_id: Any | None = None,
    actor: Any | None = None,
) -> QuerySet[ReportSubjectLineSnapshot]:
    if tenant is None:
        return ReportSubjectLineSnapshot.objects.none()
    queryset = ReportSubjectLineSnapshot.objects.filter(tenant=tenant).select_related(
        "snapshot_run",
        "assessment",
        "student",
        "cohort",
        "learning_area",
        "curriculum_version",
        "rubric_foundation",
    )
    if snapshot_run is not None:
        queryset = queryset.filter(snapshot_run=snapshot_run)
    if cohort_id is not None:
        queryset = queryset.filter(cohort_id=cohort_id)
    if learning_area_id is not None:
        queryset = queryset.filter(learning_area_id=learning_area_id)
    if actor is not None:
        queryset = queryset.filter(
            assessment__cohort__teacher_assignments__teacher=actor,
            assessment__cohort__teacher_assignments__learning_area=models.F(
                "learning_area"
            ),
            assessment__cohort__teacher_assignments__academic_year=models.F(
                "academic_year"
            ),
            assessment__cohort__teacher_assignments__term=models.F("term"),
            assessment__cohort__teacher_assignments__is_active=True,
        )
    return queryset.distinct().order_by(
        "cohort__name",
        "learning_area__name",
        "student_id",
    )


def get_academic_aggregates(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun | None = None,
    scope_type: str | None = None,
    cohort_id: Any | None = None,
    learning_area_id: Any | None = None,
) -> QuerySet[AcademicAggregate]:
    if tenant is None:
        return AcademicAggregate.objects.none()
    queryset = AcademicAggregate.objects.filter(tenant=tenant).select_related(
        "snapshot_run",
        "academic_year",
        "term",
        "cohort",
        "learning_area",
        "grade_level",
    )
    if snapshot_run is not None:
        queryset = queryset.filter(snapshot_run=snapshot_run)
    if scope_type is not None:
        queryset = queryset.filter(scope_type=scope_type)
    if cohort_id is not None:
        queryset = queryset.filter(cohort_id=cohort_id)
    if learning_area_id is not None:
        queryset = queryset.filter(learning_area_id=learning_area_id)
    return queryset.order_by("scope_type", "cohort__name", "learning_area__name")


def get_teacher_compilation_scope(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any | None = None,
) -> QuerySet[CompiledCohortSummary]:
    if actor is None or tenant is None:
        return CompiledCohortSummary.objects.none()
    queryset = get_compiled_cohort_summary(tenant=tenant).filter(
        assessment__cohort__teacher_assignments__teacher=actor,
        assessment__cohort__teacher_assignments__learning_area=models.F(
            "assessment__learning_area"
        ),
        assessment__cohort__teacher_assignments__academic_year=models.F(
            "assessment__academic_year"
        ),
        assessment__cohort__teacher_assignments__term=models.F("assessment__term"),
        assessment__cohort__teacher_assignments__is_active=True,
    )
    if assessment_id is not None:
        assessment_uuid = _safe_uuid(assessment_id)
        if assessment_uuid is None:
            return CompiledCohortSummary.objects.none()
        queryset = queryset.filter(assessment_id=assessment_uuid)
    return queryset.distinct()


def get_hod_compilation_scope(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[CompiledCohortSummary]:
    if actor is None or tenant is None:
        return CompiledCohortSummary.objects.none()
    queryset = get_compiled_cohort_summary(tenant=tenant).filter(
        assessment__cohort__teacher_assignments__teacher=actor,
        assessment__cohort__teacher_assignments__learning_area=models.F(
            "assessment__learning_area"
        ),
        assessment__cohort__teacher_assignments__academic_year=models.F(
            "assessment__academic_year"
        ),
        assessment__cohort__teacher_assignments__term=models.F("assessment__term"),
        assessment__cohort__teacher_assignments__is_active=True,
    )
    learning_area_id = (filters or {}).get("learning_area_id")
    if learning_area_id is not None:
        queryset = queryset.filter(learning_area_id=learning_area_id)
    return queryset.distinct()


def get_principal_compilation_scope(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> QuerySet[CompiledCohortSummary]:
    if actor is None or tenant is None:
        return CompiledCohortSummary.objects.none()
    queryset = get_compiled_cohort_summary(tenant=tenant)
    status = (filters or {}).get("status")
    if status:
        queryset = queryset.filter(status=status)
    return queryset
