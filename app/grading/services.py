"""Write services for the grading workflow.

Phase 6B adds draft and final submission orchestration while keeping CBE/CCT
binding, tenant context, teacher identity, and event payloads server-derived.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import TeacherAssignment
from core.models import Role, TenantUserRole
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant
from events.services import write_outbox_event
from grading.algorithms.batch_validation import validate_grade_rows
from grading.algorithms.cohort_summary_builder import build_cohort_summary
from grading.algorithms.compilation_inputs import build_compilation_input
from grading.algorithms.compilation_status import determine_compilation_status
from grading.algorithms.component_summary import detect_invalid_component_scores
from grading.algorithms.component_readiness import component_readiness_blockers
from grading.algorithms.cct_readiness_guard import cct_readiness_blockers
from grading.algorithms.cbe_school_schema_boundary import can_bind_school_schema
from grading.algorithms.correction_audit_diff import (
    correction_changed_fields,
    correction_state_hash,
)
from grading.algorithms.correction_readiness_impact import (
    correction_readiness_blockers,
    schema_readiness_blockers,
)
from grading.algorithms.correction_status import APPROVED_UNAPPLIED_STATUSES
from grading.algorithms.correction_transition_rules import can_transition_correction
from grading.algorithms.draft_merge import (
    normalize_draft_rows,
    validate_draft_version,
)
from grading.algorithms.grade_grid_builder import build_grid_contract
from grading.algorithms.hod_escalation_rules import can_escalate_hod_unavailable
from grading.algorithms.learner_snapshot_builder import build_learner_snapshots
from grading.algorithms.missing_marks import detect_missing_marks
from grading.algorithms.pii_safe_correction_payload import sanitize_untrusted_text
from grading.algorithms.academic_aggregate_builder import build_scope_aggregate
from grading.algorithms.readiness_blockers import blocker
from grading.algorithms.report_eligibility_rules import (
    evaluate_report_eligibility,
    summarize_eligibility,
)
from grading.algorithms.report_readiness_rules import build_report_readiness_summary
from grading.algorithms.report_snapshot_builder import (
    build_learner_snapshot_payload,
    build_subject_line_payload,
)
from grading.algorithms.role_projection_builder import build_role_projection
from grading.algorithms.role_analytics_projection import (
    build_future_parent_snapshot_projection,
    build_role_analytics_projection,
)
from grading.algorithms.role_readiness_projection import (
    build_future_parent_readiness_projection,
    build_readiness_projection,
)
from grading.algorithms.roster_resolver import stable_roster_rows
from grading.algorithms.stale_compilation_detector import detect_stale_compilation
from grading.algorithms.school_grading_band_mapper import (
    map_score_to_band as map_score_to_band_value,
)
from grading.algorithms.school_grading_schema_validator import validate_schema_bands
from grading.algorithms.submission_confirmation import validate_confirmation
from grading.algorithms.submission_idempotency import (
    canonical_payload_hash,
    ensure_same_payload,
    require_idempotency_key,
)
from grading.algorithms.workload_resolver import build_work_item
from grading.models import (
    Assessment,
    AssessmentComponent,
    AcademicAggregate,
    CompilationRun,
    CompiledAssessmentSnapshot,
    CompiledCohortSummary,
    CompiledLearnerSnapshot,
    GradeDraftBatch,
    GradeDraftRow,
    GradeCorrectionAuditRecord,
    GradeCorrectionRequest,
    GradeRecord,
    GradeSubmissionBatch,
    LearnerReportSnapshot,
    ReportEligibilityRecord,
    ReportSnapshotRun,
    ReportSubjectLineSnapshot,
    SchoolGradingBand,
    SchoolGradingSchema,
)
from grading.policies import (
    can_apply_correction,
    can_compile_assessment,
    can_compute_report_snapshot,
    can_compute_readiness,
    can_escalate_correction,
    can_manage_school_grading_schema,
    can_review_academic_head_correction,
    can_review_hod_correction,
    can_submit_correction_request,
    can_view_correction_audit,
    can_view_academic_head_readiness,
    can_view_deputy_academics_compilation,
    can_view_future_parent_readiness,
    can_view_future_parent_projection,
    can_view_class_teacher_analytics,
    can_view_deputy_analytics,
    can_view_future_parent_snapshot,
    can_view_hod_compilation,
    can_view_hod_analytics,
    can_view_hod_readiness,
    can_view_principal_correction_summary,
    can_view_principal_compilation,
    can_view_principal_analytics,
    can_view_principal_readiness,
    can_view_subject_teacher_analytics,
    can_view_teacher_compilation,
    can_view_teacher_readiness,
)
from grading.selectors import (
    get_academic_aggregates,
    get_academic_head_readiness_scope,
    get_assessment_for_teacher,
    get_assessment_components_for_compilation,
    get_assessment_schema_binding,
    get_correction_audit_trail as select_correction_audit_trail,
    get_cct_blockers_for_assessment,
    get_compiled_learner_snapshots,
    get_hod_readiness_scope,
    get_learner_report_snapshots,
    get_latest_compilation_for_assessment,
    get_pending_corrections_for_assessment,
    get_principal_readiness_scope,
    get_report_subject_line_snapshots,
    get_readiness_batches_for_assessment,
    get_readiness_drafts_for_assessment,
    get_expected_roster_for_compilation,
    get_existing_draft_for_teacher,
    get_existing_submission_for_assessment,
    get_principal_correction_summary,
    get_schema_bands_for_assessment,
    get_hod_compilation_scope,
    get_principal_compilation_scope,
    get_roster_for_assessment,
    get_submitted_records_for_assessment,
    get_teacher_compilation_scope,
    get_teacher_grading_contexts,
    get_teacher_readiness_scope,
)


GRADING_ROLE_CODES = frozenset(
    {
        Role.RoleCode.SUBJECT_TEACHER.value,
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.HOD.value,
    }
)
GRADING_TEACHER_ROLE_CODES = {
    Role.RoleCode.SUBJECT_TEACHER.value,
    Role.RoleCode.CLASS_TEACHER.value,
    Role.RoleCode.HOD.value,
}
GRADING_HOD_ROLE_CODES = {Role.RoleCode.HOD.value}
GRADING_ACADEMIC_HEAD_ROLE_CODES = {
    Role.RoleCode.DEPUTY_PRINCIPAL.value,
    Role.RoleCode.SCHOOL_ADMIN.value,
}
GRADING_SCHEMA_ADMIN_ROLE_CODES = {
    Role.RoleCode.PRINCIPAL.value,
    Role.RoleCode.DEPUTY_PRINCIPAL.value,
    Role.RoleCode.SCHOOL_ADMIN.value,
}

CLIENT_CONTROLLED_FIELDS = frozenset(
    {
        "tenant",
        "tenant_id",
        "teacher",
        "teacher_id",
        "submitted_by",
        "submitted_by_id",
        "teacher_assignment",
        "teacher_assignment_id",
        "status",
        "compiled_at",
        "validated_at",
        "reviewed_by",
        "reviewed_by_id",
        "approved_by",
        "approved_by_id",
        "applied_by",
        "applied_by_id",
        "old_state_hash",
        "curriculum_version",
        "curriculum_version_id",
        "rubric_foundation",
        "rubric_foundation_id",
        "curriculum_binding_locked_at",
    }
)


def _reject_client_controlled_fields(payload: dict[str, Any]) -> None:
    keys = set(payload)
    row_keys = set()
    for row in payload.get("rows", []) if isinstance(payload.get("rows"), list) else []:
        if isinstance(row, dict):
            row_keys.update(row)
    forbidden = (keys | row_keys) & CLIENT_CONTROLLED_FIELDS
    if forbidden:
        raise ValidationError({"payload": "Payload contains server-controlled fields."})


def _has_grading_role(*, actor: Any, tenant: Any) -> bool:
    if actor is None or tenant is None or not getattr(actor, "is_active", False):
        return False
    return any(
        user_has_role_in_tenant(user=actor, tenant=tenant, role_code=role_code)
        for role_code in GRADING_ROLE_CODES
    )


def _role_for(actor: Any, tenant: Any, role_codes: set[str]) -> Role | None:
    if actor is None or tenant is None:
        return None
    binding = (
        TenantUserRole.objects.filter(
            tenant=tenant,
            user=actor,
            role__code__in=role_codes,
            role__is_active=True,
            is_active=True,
        )
        .select_related("role")
        .first()
    )
    return binding.role if binding else None


def _policy_context(
    *,
    actor: Any,
    tenant: Any,
    action: str,
    role_codes: set[str],
) -> PolicyContext:
    return PolicyContext(
        tenant=tenant,
        actor=actor,
        action=action,
        role=_role_for(actor, tenant, role_codes),
    )


def _teacher_assignment_for(
    *,
    actor: Any,
    tenant: Any,
    assessment: Assessment,
) -> TeacherAssignment:
    assignment = TeacherAssignment.objects.filter(
        tenant=tenant,
        teacher=actor,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
        is_active=True,
        cohort__is_active=True,
        learning_area__is_active=True,
    ).first()
    if assignment is None:
        raise ValidationError(
            {"assessment": "Teacher is not assigned to grade this assessment."}
        )
    return assignment


def _grade_rows_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValidationError({"rows": "Rows must be provided."})
    return rows


def _assessment_components(assessment: Assessment) -> list[AssessmentComponent]:
    return list(assessment.components.order_by("order", "name"))


def _roster_ids(*, tenant: Any, assessment: Assessment) -> set[str]:
    return {
        str(student.id)
        for student in get_roster_for_assessment(tenant=tenant, assessment=assessment)
    }


def get_my_grading_work(
    *,
    actor: Any,
    tenant: Any,
    academic_year: Any | None = None,
    term: Any | None = None,
) -> list[dict[str, str]]:
    if not _has_grading_role(actor=actor, tenant=tenant):
        return []
    return [
        build_work_item(assessment)
        for assessment in get_teacher_grading_contexts(
            actor=actor,
            tenant=tenant,
            academic_year=academic_year,
            term=term,
        )
    ]


def build_grade_grid(*, actor: Any, tenant: Any, assessment_id: Any) -> dict[str, Any]:
    if not _has_grading_role(actor=actor, tenant=tenant):
        raise ValidationError({"assessment": "Assessment is not available."})
    assessment = get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )
    if assessment is None:
        raise ValidationError({"assessment": "Assessment is not available."})
    _teacher_assignment_for(actor=actor, tenant=tenant, assessment=assessment)
    roster = list(get_roster_for_assessment(tenant=tenant, assessment=assessment))
    roster_rows = stable_roster_rows(roster)
    draft = get_existing_draft_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment=assessment,
    )
    draft_rows = {}
    if draft is not None:
        draft_rows = {
            str(row.student_id): {
                "raw_score": str(row.raw_score) if row.raw_score is not None else None,
                "component_scores": row.component_scores,
                "remarks": row.remarks,
                "row_version": row.row_version,
            }
            for row in draft.rows.all()
        }
    submitted = get_existing_submission_for_assessment(
        actor=actor,
        tenant=tenant,
        assessment=assessment,
    )
    submitted_rows = {}
    if submitted is not None:
        submitted_rows = {
            str(record.student_id): {
                "raw_score": str(record.raw_score),
                "component_scores": record.component_scores,
                "remarks": record.remarks,
            }
            for record in submitted.grade_records.select_related("student").all()
        }
    grid = build_grid_contract(
        assessment=assessment,
        roster_rows=roster_rows,
        components=_assessment_components(assessment),
        draft_rows=draft_rows,
        submitted_rows=submitted_rows,
    )
    if draft is not None:
        grid["draft"] = {"draft_id": str(draft.id), "version": draft.version}
    return grid


@transaction.atomic
def save_grade_draft(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
    payload: dict[str, Any],
    idempotency_key: str,
) -> GradeDraftBatch:
    if not _has_grading_role(actor=actor, tenant=tenant):
        raise ValidationError({"assessment": "Assessment is not available."})
    _reject_client_controlled_fields(payload)
    key = require_idempotency_key(idempotency_key)
    assessment = get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )
    if assessment is None:
        raise ValidationError({"assessment": "Assessment is not available."})
    assignment = _teacher_assignment_for(
        actor=actor,
        tenant=tenant,
        assessment=assessment,
    )
    rows = _grade_rows_payload(payload)
    row_payload_hash = canonical_payload_hash(rows)
    existing_by_key = GradeDraftBatch.objects.filter(
        tenant=tenant,
        idempotency_key=key,
    ).first()
    if existing_by_key is not None:
        if (
            existing_by_key.assessment_id != assessment.id
            or existing_by_key.teacher_id != actor.id
        ):
            raise ValidationError(
                {"idempotency_key": "Idempotency key belongs to another context."}
            )
        ensure_same_payload(
            existing_hash=existing_by_key.payload_hash,
            new_hash=row_payload_hash,
        )
        return existing_by_key
    draft = (
        GradeDraftBatch.objects.select_for_update()
        .filter(
            tenant=tenant,
            assessment=assessment,
            teacher=actor,
            status=GradeDraftBatch.Status.DRAFT,
        )
        .first()
    )
    validate_draft_version(
        current_version=draft.version if draft else None,
        expected_version=payload.get("draft_version"),
    )
    normalized_rows = normalize_draft_rows(
        rows=rows,
        roster_student_ids=_roster_ids(tenant=tenant, assessment=assessment),
        max_score=assessment.max_score,
        components=_assessment_components(assessment),
    )
    if draft is None:
        draft = GradeDraftBatch.objects.create(
            tenant=tenant,
            assessment=assessment,
            teacher=actor,
            teacher_assignment=assignment,
            cohort=assessment.cohort,
            learning_area=assessment.learning_area,
            idempotency_key=key,
            payload_hash=row_payload_hash,
        )
    else:
        draft.version += 1
        draft.idempotency_key = key
        draft.payload_hash = row_payload_hash
        draft.save()
        draft.rows.all().delete()
    GradeDraftRow.objects.bulk_create(
        [
            GradeDraftRow(
                tenant=tenant,
                draft_batch=draft,
                student_id=row["student_id"],
                raw_score=row["raw_score"],
                component_scores=row["component_scores"],
                remarks=row["remarks"],
            )
            for row in normalized_rows
        ]
    )
    return draft


def build_submission_batch(
    *,
    tenant: Any,
    actor: Any,
    assessment: Assessment,
    teacher_assignment: TeacherAssignment,
    idempotency_key: str,
    record_count: int = 0,
    status: str = GradeSubmissionBatch.Status.SUBMITTED,
    payload_hash: str = "sha256:" + "0" * 64,
    confirmation_method: str = "session_step_up",
    confirmation_at: Any | None = None,
    confirmation_reference: str = "legacy-phase6a-helper",
) -> GradeSubmissionBatch:
    """Create a batch with server-derived tenant/teacher/assignment context."""

    if teacher_assignment.teacher_id != actor.id:
        raise ValidationError({"teacher_assignment": "Teacher assignment is invalid."})
    return GradeSubmissionBatch.objects.create(
        tenant=tenant,
        assessment=assessment,
        teacher=actor,
        teacher_assignment=teacher_assignment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        record_count=record_count,
        status=status,
        submitted_at=(
            timezone.now() if status != GradeSubmissionBatch.Status.DRAFT else None
        ),
        confirmation_method=confirmation_method,
        confirmation_at=confirmation_at or timezone.now(),
        confirmation_reference=confirmation_reference,
    )


def build_grade_record(
    *,
    tenant: Any,
    actor: Any,
    assessment: Assessment,
    submission_batch: GradeSubmissionBatch,
    student: Any,
    raw_score: Any,
    remarks: str = "",
    component_scores: dict[str, Any] | None = None,
) -> GradeRecord:
    """Create a grade record using authenticated actor, not client identity."""

    return GradeRecord.objects.create(
        tenant=tenant,
        assessment=assessment,
        submission_batch=submission_batch,
        student=student,
        raw_score=raw_score,
        component_scores=component_scores or {},
        remarks=remarks,
        submitted_by=actor,
    )


def _reject_correction_mass_assignment(payload: dict[str, Any]) -> None:
    forbidden = {
        "status",
        "tenant",
        "tenant_id",
        "reviewed_by",
        "reviewed_by_id",
        "approved_by",
        "approved_by_id",
        "applied_by",
        "applied_by_id",
        "old_state_hash",
        "requested_by",
        "requested_by_id",
        "schema_version",
        "school_grading_schema_version",
    } & set(payload)
    if forbidden:
        raise ValidationError({"payload": "Payload contains server-controlled fields."})


def _correction_context(
    *,
    actor: Any,
    tenant: Any,
    action: str,
    role_codes: set[str],
) -> PolicyContext:
    return _policy_context(
        actor=actor,
        tenant=tenant,
        action=action,
        role_codes=role_codes,
    )


def _audit_correction(
    *,
    tenant: Any,
    correction: GradeCorrectionRequest,
    actor: Any,
    action: str,
    status_from: str,
    status_to: str,
    changed_fields: list[str] | None = None,
    state_before_hash: str = "",
    state_after_hash: str = "",
    reason_summary: str = "",
) -> GradeCorrectionAuditRecord:
    return GradeCorrectionAuditRecord.objects.create(
        tenant=tenant,
        correction_request=correction,
        grade_record=correction.grade_record,
        actor=actor,
        action=action,
        status_from=status_from,
        status_to=status_to,
        reason_code=correction.reason_code,
        reason_summary=reason_summary,
        state_before_hash=state_before_hash,
        state_after_hash=state_after_hash,
        changed_fields=changed_fields or [],
    )


def _get_correction_for_update(
    *,
    tenant: Any,
    correction_request_id: Any,
) -> GradeCorrectionRequest:
    correction = (
        GradeCorrectionRequest.objects.select_for_update()
        .select_related("grade_record", "grade_record__assessment", "requested_by")
        .filter(tenant=tenant, id=correction_request_id)
        .first()
    )
    if correction is None:
        raise ValidationError({"correction": "Correction is not available."})
    return correction


@transaction.atomic
def create_correction_request(
    *,
    actor: Any,
    tenant: Any,
    grade_record_id: Any,
    payload: dict[str, Any],
) -> GradeCorrectionRequest:
    _reject_correction_mass_assignment(payload)
    grade_record = (
        GradeRecord.objects.select_related("assessment", "submission_batch")
        .filter(tenant=tenant, id=grade_record_id)
        .first()
    )
    if grade_record is None:
        raise ValidationError({"grade_record": "Grade record is not available."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.submit",
        role_codes=GRADING_TEACHER_ROLE_CODES,
    )
    if not can_submit_correction_request(context, grade_record=grade_record):
        raise ValidationError({"correction": "Correction is not authorized."})
    proposed_components = payload.get("proposed_component_scores") or {}
    if not isinstance(proposed_components, dict):
        raise ValidationError({"proposed_component_scores": "Invalid components."})
    reason = sanitize_untrusted_text(payload.get("reason"), max_length=500)
    reason_code = sanitize_untrusted_text(
        payload.get("reason_code", "teacher_request"),
        max_length=64,
    )
    old_hash = correction_state_hash(
        grade_record_id=grade_record.id,
        raw_score=grade_record.raw_score,
        component_scores=grade_record.component_scores,
        remarks=grade_record.remarks,
        version=grade_record.version,
    )
    correction = GradeCorrectionRequest.objects.create(
        tenant=tenant,
        grade_record=grade_record,
        requested_by=actor,
        reason=reason,
        reason_code=reason_code,
        old_state_hash=old_hash,
        proposed_raw_score=payload.get("proposed_raw_score"),
        proposed_component_scores=proposed_components,
        proposed_remarks=sanitize_untrusted_text(
            payload.get("proposed_remarks", ""),
            max_length=500,
        ),
        status=GradeCorrectionRequest.Status.UNDER_HOD_REVIEW,
    )
    _audit_correction(
        tenant=tenant,
        correction=correction,
        actor=actor,
        action=GradeCorrectionAuditRecord.Action.REQUESTED,
        status_from="",
        status_to=correction.status,
        state_before_hash=old_hash,
        reason_summary="teacher_requested_correction",
    )
    return correction


@transaction.atomic
def review_correction_as_hod(
    *,
    actor: Any,
    tenant: Any,
    correction_request_id: Any,
    decision: str,
    reason: str,
) -> GradeCorrectionRequest:
    correction = _get_correction_for_update(
        tenant=tenant,
        correction_request_id=correction_request_id,
    )
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.hod.review",
        role_codes=GRADING_HOD_ROLE_CODES,
    )
    if not can_review_hod_correction(context, correction=correction):
        raise ValidationError({"correction": "Correction review is not authorized."})
    target = {
        "approve": GradeCorrectionRequest.Status.APPROVED_BY_HOD,
        "reject": GradeCorrectionRequest.Status.REJECTED_BY_HOD,
    }.get(decision)
    if target is None:
        raise ValidationError({"decision": "Correction decision is invalid."})
    transition = can_transition_correction(
        current_status=correction.status,
        target_status=target,
    )
    if not transition.allowed:
        raise ValidationError({"status": "Correction transition is invalid."})
    status_from = correction.status
    correction.status = target
    correction.reviewed_by = actor
    correction.reviewed_at = timezone.now()
    correction.review_reason = sanitize_untrusted_text(reason, max_length=500)
    correction.save()
    _audit_correction(
        tenant=tenant,
        correction=correction,
        actor=actor,
        action=GradeCorrectionAuditRecord.Action.REVIEWED,
        status_from=status_from,
        status_to=correction.status,
        reason_summary=f"hod_{decision}",
    )
    return correction


@transaction.atomic
def escalate_correction_request(
    *,
    actor: Any,
    tenant: Any,
    correction_request_id: Any,
    reason: str,
) -> GradeCorrectionRequest:
    correction = _get_correction_for_update(
        tenant=tenant,
        correction_request_id=correction_request_id,
    )
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.escalate",
        role_codes=GRADING_ACADEMIC_HEAD_ROLE_CODES,
    )
    if not can_escalate_correction(context, correction=correction):
        raise ValidationError(
            {"correction": "Correction escalation is not authorized."}
        )
    clean_reason = sanitize_untrusted_text(reason, max_length=500)
    escalation = can_escalate_hod_unavailable(
        status=correction.status,
        explicit_reason=clean_reason,
        hod_available=False,
    )
    if not escalation.allowed:
        raise ValidationError({"status": "Correction escalation is invalid."})
    status_from = correction.status
    correction.status = GradeCorrectionRequest.Status.ESCALATION_REQUESTED
    correction.escalated_by = actor
    correction.escalated_at = timezone.now()
    correction.escalation_reason = clean_reason
    correction.save()
    _audit_correction(
        tenant=tenant,
        correction=correction,
        actor=actor,
        action=GradeCorrectionAuditRecord.Action.ESCALATED,
        status_from=status_from,
        status_to=correction.status,
        reason_summary="hod_unavailable_escalation",
    )
    return correction


@transaction.atomic
def review_correction_as_academic_head(
    *,
    actor: Any,
    tenant: Any,
    correction_request_id: Any,
    decision: str,
    reason: str,
) -> GradeCorrectionRequest:
    correction = _get_correction_for_update(
        tenant=tenant,
        correction_request_id=correction_request_id,
    )
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.academic_head.review",
        role_codes=GRADING_ACADEMIC_HEAD_ROLE_CODES,
    )
    if not can_review_academic_head_correction(context, correction=correction):
        raise ValidationError({"correction": "Correction review is not authorized."})
    target = {
        "approve": GradeCorrectionRequest.Status.APPROVED_BY_ACADEMIC_HEAD,
        "reject": GradeCorrectionRequest.Status.REJECTED_BY_ACADEMIC_HEAD,
    }.get(decision)
    if target is None:
        raise ValidationError({"decision": "Correction decision is invalid."})
    transition = can_transition_correction(
        current_status=correction.status,
        target_status=target,
    )
    if not transition.allowed:
        raise ValidationError({"status": "Correction transition is invalid."})
    status_from = correction.status
    correction.status = target
    correction.reviewed_by = actor
    correction.reviewed_at = timezone.now()
    correction.review_reason = sanitize_untrusted_text(reason, max_length=500)
    correction.save()
    _audit_correction(
        tenant=tenant,
        correction=correction,
        actor=actor,
        action=GradeCorrectionAuditRecord.Action.REVIEWED,
        status_from=status_from,
        status_to=correction.status,
        reason_summary=f"academic_head_{decision}",
    )
    return correction


@transaction.atomic
def apply_approved_correction(
    *,
    actor: Any,
    tenant: Any,
    correction_request_id: Any,
) -> GradeCorrectionRequest:
    correction = _get_correction_for_update(
        tenant=tenant,
        correction_request_id=correction_request_id,
    )
    if correction.status not in APPROVED_UNAPPLIED_STATUSES:
        raise ValidationError({"status": "Correction is not approved for application."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.apply",
        role_codes=GRADING_HOD_ROLE_CODES | GRADING_ACADEMIC_HEAD_ROLE_CODES,
    )
    if not can_apply_correction(context, correction=correction):
        raise ValidationError(
            {"correction": "Correction application is not authorized."}
        )
    record = correction.grade_record
    state_before = correction_state_hash(
        grade_record_id=record.id,
        raw_score=record.raw_score,
        component_scores=record.component_scores,
        remarks=record.remarks,
        version=record.version,
    )
    new_raw_score = (
        correction.proposed_raw_score
        if correction.proposed_raw_score is not None
        else record.raw_score
    )
    new_components = correction.proposed_component_scores or record.component_scores
    new_remarks = correction.proposed_remarks or record.remarks
    changed = correction_changed_fields(
        old_raw_score=record.raw_score,
        new_raw_score=correction.proposed_raw_score,
        old_component_scores=record.component_scores,
        new_component_scores=correction.proposed_component_scores,
        old_remarks=record.remarks,
        new_remarks=correction.proposed_remarks,
    )
    if not changed:
        raise ValidationError({"correction": "Correction does not change the record."})
    record.raw_score = new_raw_score
    record.component_scores = new_components
    record.remarks = new_remarks
    record.version += 1
    bands = list(
        get_schema_bands_for_assessment(tenant=tenant, assessment=record.assessment)
    )
    if bands:
        mapping = map_score_to_band_value(
            raw_score=record.raw_score,
            max_score=record.assessment.max_score,
            bands=[
                {
                    "label": band.label,
                    "descriptor": band.descriptor,
                    "min_percentage": band.min_percentage,
                    "max_percentage": band.max_percentage,
                    "points": band.points,
                }
                for band in bands
            ],
        )
        record.normalized_score = mapping.normalized_percentage
        record.internal_band_label = mapping.band_label
        record.internal_band_descriptor = mapping.band_descriptor
        record.school_grading_schema_version = (
            record.assessment.school_grading_schema_version
        )
    record.save()
    CompilationRun.objects.filter(tenant=tenant, assessment=record.assessment).update(
        status=CompilationRun.Status.STALE
    )
    state_after = correction_state_hash(
        grade_record_id=record.id,
        raw_score=record.raw_score,
        component_scores=record.component_scores,
        remarks=record.remarks,
        version=record.version,
    )
    status_from = correction.status
    correction.status = GradeCorrectionRequest.Status.APPLIED
    correction.applied_by = actor
    correction.applied_at = timezone.now()
    correction.save()
    _audit_correction(
        tenant=tenant,
        correction=correction,
        actor=actor,
        action=GradeCorrectionAuditRecord.Action.APPLIED,
        status_from=status_from,
        status_to=correction.status,
        changed_fields=changed,
        state_before_hash=state_before,
        state_after_hash=state_after,
        reason_summary="approved_correction_applied",
    )
    return correction


def get_correction_audit_trail(
    *,
    actor: Any,
    tenant: Any,
    correction_request_id: Any,
) -> list[GradeCorrectionAuditRecord]:
    correction = GradeCorrectionRequest.objects.filter(
        tenant=tenant,
        id=correction_request_id,
    ).first()
    if correction is None:
        raise ValidationError({"correction": "Correction is not available."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.audit.view",
        role_codes=(
            GRADING_TEACHER_ROLE_CODES
            | GRADING_ACADEMIC_HEAD_ROLE_CODES
            | {Role.RoleCode.PRINCIPAL.value}
        ),
    )
    if not can_view_correction_audit(context, correction=correction):
        raise ValidationError({"correction": "Correction is not available."})
    return list(
        select_correction_audit_trail(
            tenant=tenant,
            correction_request=correction,
        )
    )


def get_principal_correction_summary_projection(
    *,
    actor: Any,
    tenant: Any,
) -> dict[str, int]:
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.correction.principal.summary.view",
        role_codes={Role.RoleCode.PRINCIPAL.value, Role.RoleCode.SCHOOL_ADMIN.value},
    )
    if not can_view_principal_correction_summary(context):
        raise ValidationError({"correction": "Correction summary is not available."})
    return get_principal_correction_summary(tenant=tenant)


@transaction.atomic
def create_school_grading_schema(
    *,
    actor: Any,
    tenant: Any,
    payload: dict[str, Any],
) -> SchoolGradingSchema:
    _reject_correction_mass_assignment(payload)
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.schema.create",
        role_codes=GRADING_SCHEMA_ADMIN_ROLE_CODES,
    )
    if not can_manage_school_grading_schema(context, action="grading.schema.create"):
        raise ValidationError({"schema": "Schema management is not authorized."})
    bands_payload = payload.get("bands") or []
    validation = validate_schema_bands(
        bands=bands_payload,
        requires_full_coverage=bool(payload.get("requires_full_coverage", True)),
    )
    if not validation.is_valid:
        raise ValidationError({"bands": ", ".join(validation.errors)})
    schema = SchoolGradingSchema.objects.create(
        tenant=tenant,
        name=sanitize_untrusted_text(payload.get("name"), max_length=120),
        assessment_type=str(payload.get("assessment_type") or ""),
        version_label=sanitize_untrusted_text(
            payload.get("version_label"),
            max_length=48,
        ),
        requires_full_coverage=bool(payload.get("requires_full_coverage", True)),
        created_by=actor,
    )
    SchoolGradingBand.objects.bulk_create(
        [
            SchoolGradingBand(
                tenant=tenant,
                schema=schema,
                label=sanitize_untrusted_text(band["label"], max_length=32),
                descriptor=sanitize_untrusted_text(
                    band.get("descriptor", ""),
                    max_length=160,
                ),
                min_percentage=Decimal(str(band["min_percentage"])),
                max_percentage=Decimal(str(band["max_percentage"])),
                points=(
                    Decimal(str(band["points"]))
                    if band.get("points") is not None
                    else None
                ),
                order=index + 1,
            )
            for index, band in enumerate(bands_payload)
        ]
    )
    return schema


@transaction.atomic
def activate_school_grading_schema(
    *,
    actor: Any,
    tenant: Any,
    schema_id: Any,
) -> SchoolGradingSchema:
    schema = SchoolGradingSchema.objects.filter(tenant=tenant, id=schema_id).first()
    if schema is None:
        raise ValidationError({"schema": "Schema is not available."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.schema.activate",
        role_codes=GRADING_SCHEMA_ADMIN_ROLE_CODES,
    )
    if not can_manage_school_grading_schema(
        context,
        action="grading.schema.activate",
        schema=schema,
    ):
        raise ValidationError({"schema": "Schema management is not authorized."})
    bands = [
        {
            "label": band.label,
            "min_percentage": band.min_percentage,
            "max_percentage": band.max_percentage,
        }
        for band in schema.bands.all()
    ]
    validation = validate_schema_bands(
        bands=bands,
        requires_full_coverage=schema.requires_full_coverage,
    )
    if not validation.is_valid:
        raise ValidationError({"bands": ", ".join(validation.errors)})
    schema.status = SchoolGradingSchema.Status.ACTIVE
    schema.activated_by = actor
    schema.activated_at = timezone.now()
    schema.save()
    return schema


@transaction.atomic
def deprecate_school_grading_schema(
    *,
    actor: Any,
    tenant: Any,
    schema_id: Any,
) -> SchoolGradingSchema:
    schema = SchoolGradingSchema.objects.filter(tenant=tenant, id=schema_id).first()
    if schema is None:
        raise ValidationError({"schema": "Schema is not available."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.schema.deprecate",
        role_codes=GRADING_SCHEMA_ADMIN_ROLE_CODES,
    )
    if not can_manage_school_grading_schema(
        context,
        action="grading.schema.deprecate",
        schema=schema,
    ):
        raise ValidationError({"schema": "Schema management is not authorized."})
    schema.status = SchoolGradingSchema.Status.DEPRECATED
    schema.deprecated_by = actor
    schema.deprecated_at = timezone.now()
    schema.save()
    return schema


@transaction.atomic
def bind_schema_to_assessment(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
    schema_id: Any,
) -> Assessment:
    assessment = Assessment.objects.filter(tenant=tenant, id=assessment_id).first()
    schema = SchoolGradingSchema.objects.filter(tenant=tenant, id=schema_id).first()
    if assessment is None or schema is None:
        raise ValidationError({"schema": "Schema binding is not available."})
    context = _correction_context(
        actor=actor,
        tenant=tenant,
        action="grading.schema.bind",
        role_codes=GRADING_SCHEMA_ADMIN_ROLE_CODES,
    )
    if not can_manage_school_grading_schema(
        context,
        action="grading.schema.bind",
        schema=schema,
        assessment=assessment,
    ):
        raise ValidationError({"schema": "Schema binding is not authorized."})
    decision = can_bind_school_schema(
        assessment_type=assessment.assessment_type,
        schema_assessment_type=schema.assessment_type,
        has_cbe_context=bool(
            assessment.curriculum_version_id and assessment.rubric_foundation_id
        ),
    )
    if not decision.allowed:
        raise ValidationError({"schema": decision.reason})
    if schema.status not in {
        SchoolGradingSchema.Status.ACTIVE,
        SchoolGradingSchema.Status.LOCKED,
    }:
        raise ValidationError({"schema": "Schema is not active."})
    assessment.school_grading_schema = schema
    assessment.school_grading_schema_version = schema.version_label
    assessment.save()
    return assessment


def resolve_assessment_grading_schema(
    *,
    tenant: Any,
    assessment: Assessment,
) -> SchoolGradingSchema | None:
    return get_assessment_schema_binding(tenant=tenant, assessment=assessment)


def map_score_to_school_band(
    *,
    tenant: Any,
    assessment: Assessment,
    raw_score: Any,
) -> dict[str, str]:
    bands = list(get_schema_bands_for_assessment(tenant=tenant, assessment=assessment))
    if not bands:
        raise ValidationError({"schema": "Assessment has no school grading schema."})
    mapping = map_score_to_band_value(
        raw_score=raw_score,
        max_score=assessment.max_score,
        bands=[
            {
                "label": band.label,
                "descriptor": band.descriptor,
                "min_percentage": band.min_percentage,
                "max_percentage": band.max_percentage,
                "points": band.points,
            }
            for band in bands
        ],
    )
    return {
        "raw_score": str(mapping.raw_score),
        "max_score": str(mapping.max_score),
        "normalized_score": str(mapping.normalized_percentage),
        "band_label": mapping.band_label,
        "band_descriptor": mapping.band_descriptor,
        "schema_version": assessment.school_grading_schema_version,
    }


@transaction.atomic
def submit_grade_batch(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
    payload: dict[str, Any],
    idempotency_key: str,
    confirmation: dict[str, Any],
) -> GradeSubmissionBatch:
    if not _has_grading_role(actor=actor, tenant=tenant):
        raise ValidationError({"assessment": "Assessment is not available."})
    _reject_client_controlled_fields(payload)
    key = require_idempotency_key(idempotency_key)
    assessment = get_assessment_for_teacher(
        actor=actor,
        tenant=tenant,
        assessment_id=assessment_id,
    )
    if assessment is None:
        raise ValidationError({"assessment": "Assessment is not available."})
    assignment = _teacher_assignment_for(
        actor=actor,
        tenant=tenant,
        assessment=assessment,
    )
    rows = _grade_rows_payload(payload)
    row_payload_hash = canonical_payload_hash(rows)
    existing = GradeSubmissionBatch.objects.filter(
        tenant=tenant,
        idempotency_key=key,
        status__in=[
            GradeSubmissionBatch.Status.SUBMITTED,
            GradeSubmissionBatch.Status.VALIDATED,
            GradeSubmissionBatch.Status.COMPILED,
        ],
    ).first()
    if existing is not None:
        if existing.assessment_id != assessment.id or existing.teacher_id != actor.id:
            raise ValidationError(
                {"idempotency_key": "Idempotency key belongs to another context."}
            )
        ensure_same_payload(
            existing_hash=existing.payload_hash,
            new_hash=row_payload_hash,
        )
        return existing
    if GradeSubmissionBatch.objects.filter(
        tenant=tenant,
        assessment=assessment,
        teacher=actor,
        status__in=[
            GradeSubmissionBatch.Status.SUBMITTED,
            GradeSubmissionBatch.Status.VALIDATED,
            GradeSubmissionBatch.Status.COMPILED,
        ],
    ).exists():
        raise ValidationError({"assessment": "Assessment already has a submission."})
    confirmation_result = validate_confirmation(
        confirmation=confirmation,
        actor_id=actor.id,
        tenant_id=tenant.id,
    )
    normalized_rows = validate_grade_rows(
        rows=rows,
        roster_student_ids=_roster_ids(tenant=tenant, assessment=assessment),
        max_score=assessment.max_score,
        components=_assessment_components(assessment),
        require_complete=True,
    )
    submitted_at = timezone.now()
    batch = GradeSubmissionBatch.objects.create(
        tenant=tenant,
        assessment=assessment,
        teacher=actor,
        teacher_assignment=assignment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        idempotency_key=key,
        payload_hash=row_payload_hash,
        record_count=len(normalized_rows),
        status=GradeSubmissionBatch.Status.SUBMITTED,
        submitted_at=submitted_at,
        confirmation_method=confirmation_result["method"],
        confirmation_at=confirmation_result["confirmed_at"],
        confirmation_reference=confirmation_result["confirmation_reference"],
    )
    GradeRecord.objects.bulk_create(
        [
            GradeRecord(
                tenant=tenant,
                assessment=assessment,
                submission_batch=batch,
                student_id=row["student_id"],
                raw_score=row["raw_score"],
                component_scores=row["component_scores"],
                remarks=row["remarks"],
                submitted_by=actor,
            )
            for row in normalized_rows
        ]
    )
    GradeDraftBatch.objects.filter(
        tenant=tenant,
        assessment=assessment,
        teacher=actor,
        status=GradeDraftBatch.Status.DRAFT,
    ).update(status=GradeDraftBatch.Status.SUBMITTED)

    def emit_batch_submitted() -> None:
        write_outbox_event(
            event_type="grading.batch_submitted",
            event_version=1,
            source_module="grading",
            idempotency_key=f"grading.batch_submitted:{batch.id}",
            tenant=tenant,
            actor_id=actor.id,
            payload={
                "tenant_id": str(tenant.id),
                "assessment_id": str(assessment.id),
                "batch_id": str(batch.id),
                "cohort_id": str(assessment.cohort_id),
                "learning_area_id": str(assessment.learning_area_id),
                "curriculum_version_id": str(assessment.curriculum_version_id),
                "rubric_foundation_id": str(assessment.rubric_foundation_id),
                "record_count": batch.record_count,
                "submitted_at": submitted_at.isoformat(),
            },
        )

    transaction.on_commit(emit_batch_submitted)
    return batch


def _compilation_context_snapshot(assessment: Assessment) -> dict[str, str]:
    return {
        "assessment_id": str(assessment.id),
        "cohort_id": str(assessment.cohort_id),
        "learning_area_id": str(assessment.learning_area_id),
        "curriculum_version_id": str(assessment.curriculum_version_id),
        "rubric_foundation_id": str(assessment.rubric_foundation_id),
        "academic_year_id": str(assessment.academic_year_id),
        "term_id": str(assessment.term_id),
    }


def _component_completion_summary(
    *,
    components: list[AssessmentComponent],
    missing_marks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "component_count": len(components),
        "required_component_count": len(
            [component for component in components if component.is_required]
        ),
        "missing_required_component_count": len(
            [
                item
                for item in missing_marks
                if item["code"] == "missing_required_component"
            ]
        ),
    }


@transaction.atomic
def compile_assessment(
    *,
    tenant: Any,
    assessment_id: Any,
    requested_by: Any | None = None,
) -> CompilationRun:
    assessment = Assessment.objects.filter(id=assessment_id, tenant=tenant).first()
    if assessment is None:
        raise ValidationError({"assessment": "Assessment is not available."})
    if requested_by is None:
        raise ValidationError({"requested_by": "Compilation actor is required."})
    role_codes = {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.HOD.value,
    }
    context = _policy_context(
        actor=requested_by,
        tenant=tenant,
        action="grading.compilation.compile",
        role_codes=role_codes,
    )
    if not can_compile_assessment(
        context,
        assessment=assessment,
    ):
        raise ValidationError({"assessment": "Compilation is not authorized."})
    roster = list(
        get_expected_roster_for_compilation(tenant=tenant, assessment=assessment)
    )
    records = list(
        get_submitted_records_for_assessment(tenant=tenant, assessment=assessment)
    )
    components = list(
        get_assessment_components_for_compilation(
            tenant=tenant,
            assessment=assessment,
        )
    )
    compilation_input = build_compilation_input(
        tenant=tenant,
        assessment=assessment,
        roster=roster,
        grade_records=records,
        components=components,
    )
    missing = detect_missing_marks(
        roster_student_ids=compilation_input.roster_student_ids,
        grade_records=records,
        components=components,
    )
    invalid = detect_invalid_component_scores(
        grade_records=records,
        components=components,
        assessment_max_score=assessment.max_score,
    )
    status = determine_compilation_status(
        missing_marks=missing,
        invalid_records=invalid,
        has_submitted_records=bool(records),
    )
    compiled_at = timezone.now()
    component_summary = _component_completion_summary(
        components=components,
        missing_marks=missing,
    )
    summary_payload = build_cohort_summary(
        assessment=assessment,
        expected_count=len(compilation_input.roster_student_ids),
        submitted_count=len(
            {
                str(record.student_id)
                for record in records
                if str(record.student_id) in compilation_input.roster_student_ids
            }
        ),
        missing_count=len(
            [item for item in missing if item["code"] == "missing_learner_mark"]
        ),
        component_summary=component_summary,
        status=status,
    )
    run = CompilationRun.objects.create(
        tenant=tenant,
        assessment=assessment,
        requested_by=requested_by,
        status=status,
        expected_learner_count=summary_payload["expected_learner_count"],
        submitted_learner_count=summary_payload["submitted_learner_count"],
        missing_learner_count=summary_payload["missing_learner_count"],
        source_batch_ids=compilation_input.source_batch_ids,
        error_summary=";".join(sorted({item["code"] for item in invalid}))[:255],
        compiled_at=compiled_at,
    )
    CompilationRun.objects.filter(tenant=tenant, assessment=assessment).exclude(
        id=run.id
    ).update(status=CompilationRun.Status.STALE)
    CompiledAssessmentSnapshot.objects.create(
        tenant=tenant,
        compilation_run=run,
        assessment=assessment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        curriculum_version=assessment.curriculum_version,
        rubric_foundation=assessment.rubric_foundation,
        status=status,
        context_snapshot=_compilation_context_snapshot(assessment),
        summary=summary_payload,
        compiled_at=compiled_at,
    )
    CompiledCohortSummary.objects.create(
        tenant=tenant,
        compilation_run=run,
        assessment=assessment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        expected_learner_count=summary_payload["expected_learner_count"],
        submitted_learner_count=summary_payload["submitted_learner_count"],
        missing_learner_count=summary_payload["missing_learner_count"],
        completion_percentage=summary_payload["completion_percentage"],
        component_summary=component_summary,
        status=status,
        compiled_at=compiled_at,
    )
    snapshots = build_learner_snapshots(
        compilation_input=compilation_input,
        missing_marks=missing,
        status=status,
        compiled_at=compiled_at,
    )
    CompiledLearnerSnapshot.objects.bulk_create(
        [
            CompiledLearnerSnapshot(
                tenant=tenant,
                compilation_run=run,
                assessment=assessment,
                student_id=snapshot["learner_id"],
                cohort=assessment.cohort,
                learning_area=assessment.learning_area,
                curriculum_version=assessment.curriculum_version,
                rubric_foundation=assessment.rubric_foundation,
                status=snapshot["compilation_status"],
                score_summary=snapshot["score_summary"],
                component_summary=snapshot["component_summary"],
                missing_marks=snapshot["missing_marks"],
                cbe_band_status=snapshot["cbe_band_status"],
                source_batch_ids=snapshot["source_batch_ids"],
                compiled_at=compiled_at,
            )
            for snapshot in snapshots
        ]
    )

    def emit_compilation_completed() -> None:
        write_outbox_event(
            event_type="grading.compilation_completed",
            event_version=1,
            source_module="grading",
            idempotency_key=f"grading.compilation_completed:{run.id}",
            tenant=tenant,
            actor_id=getattr(requested_by, "id", None),
            payload={
                "tenant_id": str(tenant.id),
                "assessment_id": str(assessment.id),
                "compilation_run_id": str(run.id),
                "cohort_id": str(assessment.cohort_id),
                "learning_area_id": str(assessment.learning_area_id),
                "curriculum_version_id": str(assessment.curriculum_version_id),
                "status": status,
                "compiled_at": compiled_at.isoformat(),
            },
        )

    transaction.on_commit(emit_compilation_completed)
    return run


def compile_submission_batch(
    *,
    tenant: Any,
    batch_id: Any,
    requested_by: Any | None = None,
) -> CompilationRun:
    batch = (
        GradeSubmissionBatch.objects.filter(
            tenant=tenant,
            id=batch_id,
            status=GradeSubmissionBatch.Status.SUBMITTED,
        )
        .select_related("assessment")
        .first()
    )
    if batch is None:
        raise ValidationError({"batch": "Submitted batch is not available."})
    return compile_assessment(
        tenant=tenant,
        assessment_id=batch.assessment_id,
        requested_by=requested_by,
    )


def _build_assessment_readiness(
    *,
    tenant: Any,
    assessment: Assessment,
) -> dict[str, Any]:
    run = get_latest_compilation_for_assessment(tenant=tenant, assessment=assessment)
    cohort_summary = getattr(run, "cohort_summary", None) if run else None
    batches = list(
        get_readiness_batches_for_assessment(
            tenant=tenant,
            assessment=assessment,
        )
    )
    submitted_batches = [
        batch
        for batch in batches
        if batch.status
        in {
            GradeSubmissionBatch.Status.SUBMITTED,
            GradeSubmissionBatch.Status.VALIDATED,
            GradeSubmissionBatch.Status.COMPILED,
        }
    ]
    drafts = list(
        get_readiness_drafts_for_assessment(
            tenant=tenant,
            assessment=assessment,
        )
    )
    corrections = list(
        get_pending_corrections_for_assessment(tenant=tenant, assessment=assessment)
    )
    cct_state = get_cct_blockers_for_assessment(tenant=tenant, assessment=assessment)
    blockers = []
    if run is None:
        blockers.append(
            blocker(
                code="no_compilation",
                message="No compilation run exists for this assessment.",
            )
        )
    elif run.status == CompilationRun.Status.FAILED:
        blockers.append(
            blocker(
                code="failed_compilation",
                message="Latest compilation failed.",
                resource_id=run.id,
            )
        )
    elif run.status == CompilationRun.Status.BLOCKED:
        blockers.append(
            blocker(
                code="blocked_compilation",
                message="Latest compilation is blocked.",
                resource_id=run.id,
            )
        )
    if run is not None and run.missing_learner_count > 0:
        blockers.append(
            blocker(
                code="missing_marks",
                message="One or more active learners are missing official marks.",
                scope="learner",
            )
        )
    if not submitted_batches:
        blockers.append(
            blocker(
                code="teacher_submission_missing",
                message="No submitted teacher batch exists for this assessment.",
            )
        )
    if drafts and not submitted_batches:
        blockers.append(
            blocker(
                code="draft_unsubmitted",
                message="A draft exists but final submission is missing.",
            )
        )
    blockers.extend(correction_readiness_blockers(corrections=corrections))
    schema = resolve_assessment_grading_schema(tenant=tenant, assessment=assessment)
    schema_required_types = {
        Assessment.AssessmentType.CAT,
        Assessment.AssessmentType.INTERNAL_EXAM,
        Assessment.AssessmentType.MOCK_EXAM,
        Assessment.AssessmentType.TRIAL_EXAM,
        Assessment.AssessmentType.DEPARTMENTAL_TEST,
        Assessment.AssessmentType.PRACTICAL_COMPONENT,
    }
    blockers.extend(
        schema_readiness_blockers(
            assessment_type=assessment.assessment_type,
            requires_internal_schema=(
                assessment.assessment_type in schema_required_types
            ),
            schema_status=getattr(schema, "status", None),
        )
    )
    component_summary = (
        cohort_summary.component_summary if cohort_summary is not None else {}
    )
    blockers.extend(component_readiness_blockers(component_summary=component_summary))
    latest_batch_at = max(
        [batch.submitted_at for batch in submitted_batches if batch.submitted_at],
        default=None,
    )
    correction_timestamps = [
        correction.requested_at
        for correction in corrections
        if correction.requested_at
    ]
    latest_correction_at = max(correction_timestamps, default=None)
    freshness = detect_stale_compilation(
        compilation_status=getattr(run, "status", None),
        compiled_at=getattr(run, "compiled_at", None),
        assessment_updated_at=assessment.updated_at,
        latest_batch_submitted_at=latest_batch_at,
        latest_correction_requested_at=latest_correction_at,
    )
    if freshness.is_stale:
        blockers.append(
            blocker(
                code="stale_compilation",
                message="Compilation is stale and must be reviewed.",
                resource_id=getattr(run, "id", ""),
            )
        )
    blockers.extend(
        cct_readiness_blockers(
            assessment_is_bound=assessment.is_operationally_bound(),
            has_school_adoption=bool(cct_state["has_school_adoption"]),
            curriculum_version_withdrawn=bool(
                cct_state["curriculum_version_withdrawn"]
            ),
            rollback_plan_count=int(cct_state["rollback_plan_count"]),
            app_impact_plan_count=int(cct_state["app_impact_plan_count"]),
        )
    )
    expected_count = (
        cohort_summary.expected_learner_count if cohort_summary is not None else 0
    )
    submitted_count = (
        cohort_summary.submitted_learner_count if cohort_summary is not None else 0
    )
    missing_count = (
        cohort_summary.missing_learner_count if cohort_summary is not None else 0
    )
    return build_report_readiness_summary(
        assessment_id=assessment.id,
        cohort_id=assessment.cohort_id,
        learning_area_id=assessment.learning_area_id,
        curriculum_version_id=assessment.curriculum_version_id,
        compilation_run_id=getattr(run, "id", None),
        compilation_status=getattr(run, "status", None),
        expected_learner_count=expected_count,
        submitted_learner_count=submitted_count,
        missing_learner_count=missing_count,
        blocker_items=blockers,
        has_submitted_batch=bool(submitted_batches),
        has_draft=bool(drafts),
        pending_correction_count=len(corrections),
    )


def compute_assessment_readiness(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any,
) -> dict[str, Any]:
    assessment = Assessment.objects.filter(tenant=tenant, id=assessment_id).first()
    if assessment is None:
        raise ValidationError({"assessment": "Assessment is not available."})
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.compute",
        role_codes={
            Role.RoleCode.HOD.value,
            Role.RoleCode.DEPUTY_PRINCIPAL.value,
            Role.RoleCode.PRINCIPAL.value,
            Role.RoleCode.SCHOOL_ADMIN.value,
        },
    )
    if not can_compute_readiness(context, assessment=assessment):
        raise ValidationError(
            {
                "assessment": (
                    "Readiness computation is not authorized."
                )
            }
        )
    return _build_assessment_readiness(tenant=tenant, assessment=assessment)


def _authorized_readiness_items(
    *,
    tenant: Any,
    assessments: list[Assessment],
    context: PolicyContext,
    policy_check: Any,
) -> list[dict[str, Any]]:
    visible = [
        assessment
        for assessment in assessments
        if policy_check(context, assessment=assessment)
    ]
    return [
        _build_assessment_readiness(tenant=tenant, assessment=assessment)
        for assessment in visible
    ]


def compute_cohort_readiness(
    *,
    actor: Any,
    tenant: Any,
    cohort_id: Any,
) -> dict[str, Any]:
    return get_deputy_academics_readiness_projection(
        actor=actor,
        tenant=tenant,
        filters={"cohort_id": cohort_id},
    )


def compute_department_readiness(
    *,
    actor: Any,
    tenant: Any,
    learning_area_id: Any,
) -> dict[str, Any]:
    return get_hod_readiness_projection(
        actor=actor,
        tenant=tenant,
        filters={"learning_area_id": learning_area_id},
    )


def compute_school_report_readiness(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_principal_readiness_projection(
        actor=actor,
        tenant=tenant,
        filters=filters,
    )


def get_teacher_readiness_projection(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any | None = None,
) -> dict[str, Any]:
    assessments = list(
        get_teacher_readiness_scope(
            actor=actor,
            tenant=tenant,
            assessment_id=assessment_id,
        )
    )
    if not assessments:
        return build_readiness_projection(
            projection_type="teacher",
            assessment_readiness=[],
        )
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.teacher.view",
        role_codes=GRADING_TEACHER_ROLE_CODES,
    )
    return build_readiness_projection(
        projection_type="teacher",
        assessment_readiness=_authorized_readiness_items(
            tenant=tenant,
            assessments=assessments,
            context=context,
            policy_check=can_view_teacher_readiness,
        ),
    )


def get_hod_readiness_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.hod.view",
        role_codes={Role.RoleCode.HOD.value},
    )
    return build_readiness_projection(
        projection_type="hod",
        assessment_readiness=_authorized_readiness_items(
            tenant=tenant,
            assessments=list(
                get_hod_readiness_scope(actor=actor, tenant=tenant, filters=filters)
            ),
            context=context,
            policy_check=can_view_hod_readiness,
        ),
    )


def get_deputy_academics_readiness_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.academic_head.view",
        role_codes={
            Role.RoleCode.DEPUTY_PRINCIPAL.value,
            Role.RoleCode.PRINCIPAL.value,
            Role.RoleCode.SCHOOL_ADMIN.value,
        },
    )
    if not can_view_academic_head_readiness(context):
        return build_readiness_projection(
            projection_type="deputy_head_academics",
            assessment_readiness=[],
        )
    assessments = list(
        get_academic_head_readiness_scope(tenant=tenant, filters=filters)
    )
    return build_readiness_projection(
        projection_type="deputy_head_academics",
        assessment_readiness=[
            _build_assessment_readiness(tenant=tenant, assessment=assessment)
            for assessment in assessments
            if can_view_academic_head_readiness(context, assessment=assessment)
        ],
    )


def get_principal_readiness_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.principal.view",
        role_codes={Role.RoleCode.PRINCIPAL.value, Role.RoleCode.SCHOOL_ADMIN.value},
    )
    if not can_view_principal_readiness(context):
        return build_readiness_projection(
            projection_type="principal",
            assessment_readiness=[],
        )
    assessments = list(get_principal_readiness_scope(tenant=tenant, filters=filters))
    return build_readiness_projection(
        projection_type="principal",
        assessment_readiness=[
            _build_assessment_readiness(tenant=tenant, assessment=assessment)
            for assessment in assessments
            if can_view_principal_readiness(context, assessment=assessment)
        ],
    )


def get_future_parent_report_readiness_projection(
    *,
    actor: Any,
    tenant: Any,
    learner_id: Any,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.readiness.future_parent.view",
        role_codes={Role.RoleCode.GUARDIAN.value},
    )
    if not can_view_future_parent_readiness(context, tenant=tenant):
        return build_future_parent_readiness_projection()
    return build_future_parent_readiness_projection()


def get_teacher_compilation_projection(
    *,
    actor: Any,
    tenant: Any,
    assessment_id: Any | None = None,
) -> dict[str, Any]:
    summaries = list(
        get_teacher_compilation_scope(
            actor=actor,
            tenant=tenant,
            assessment_id=assessment_id,
        )
    )
    if not summaries:
        return build_role_projection(projection_type="teacher", cohort_summaries=[])
    assessment = summaries[0].assessment
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.compilation.teacher.view",
        role_codes=GRADING_TEACHER_ROLE_CODES,
    )
    if not can_view_teacher_compilation(context, assessment=assessment):
        return build_role_projection(projection_type="teacher", cohort_summaries=[])
    return build_role_projection(projection_type="teacher", cohort_summaries=summaries)


def get_hod_compilation_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role_codes = {Role.RoleCode.HOD.value}
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.compilation.hod.view",
        role_codes=role_codes,
    )
    summaries = list(
        get_hod_compilation_scope(actor=actor, tenant=tenant, filters=filters)
    )
    visible = [
        summary
        for summary in summaries
        if can_view_hod_compilation(context, assessment=summary.assessment)
    ]
    return build_role_projection(projection_type="hod", cohort_summaries=visible)


def get_deputy_academics_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role_codes = {
        Role.RoleCode.DEPUTY_PRINCIPAL.value,
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.compilation.deputy.view",
        role_codes=role_codes,
    )
    if not can_view_deputy_academics_compilation(context):
        return build_role_projection(
            projection_type="deputy_head_academics",
            cohort_summaries=[],
        )
    summaries = list(
        get_principal_compilation_scope(actor=actor, tenant=tenant, filters=filters)
    )
    return build_role_projection(
        projection_type="deputy_head_academics",
        cohort_summaries=summaries,
    )


def get_principal_compilation_projection(
    *,
    actor: Any,
    tenant: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role_codes = {Role.RoleCode.PRINCIPAL.value, Role.RoleCode.SCHOOL_ADMIN.value}
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.compilation.principal.view",
        role_codes=role_codes,
    )
    if not can_view_principal_compilation(context):
        return build_role_projection(projection_type="principal", cohort_summaries=[])
    summaries = list(
        get_principal_compilation_scope(actor=actor, tenant=tenant, filters=filters)
    )
    return build_role_projection(
        projection_type="principal",
        cohort_summaries=summaries,
    )


def get_future_parent_learner_projection(
    *,
    actor: Any,
    tenant: Any,
    learner_id: Any,
) -> dict[str, Any]:
    role_codes = {Role.RoleCode.GUARDIAN.value}
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.compilation.future_parent.view",
        role_codes=role_codes,
    )
    if not can_view_future_parent_projection(context, tenant=tenant):
        return build_role_projection(
            projection_type="future_parent",
            cohort_summaries=[],
            learner_snapshots=[],
        )
    snapshots = list(
        get_compiled_learner_snapshots(tenant=tenant, learner_id=learner_id)
    )
    return build_role_projection(
        projection_type="future_parent",
        cohort_summaries=[],
        learner_snapshots=snapshots,
    )


def compute_report_eligibility(
    *,
    actor: Any,
    tenant: Any,
    academic_year: Any,
    term: Any,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.report_snapshot.compute",
        role_codes=GRADING_ACADEMIC_HEAD_ROLE_CODES
        | {Role.RoleCode.PRINCIPAL.value},
    )
    if not can_compute_report_snapshot(context, tenant=tenant):
        raise ValidationError({"report_snapshot": "Report snapshot is not authorized."})
    assessments = list(
        get_academic_head_readiness_scope(
            tenant=tenant,
            filters={
                "academic_year_id": getattr(academic_year, "id", academic_year),
                "term_id": getattr(term, "id", term),
                **(filters or {}),
            },
        )
    )
    results = []
    for assessment in assessments:
        readiness = _build_assessment_readiness(tenant=tenant, assessment=assessment)
        results.append(evaluate_report_eligibility(readiness))
    return summarize_eligibility(results) | {"results": results}


def _create_eligibility_records(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun,
    assessments: list[Assessment],
) -> list[dict[str, Any]]:
    results = []
    for assessment in assessments:
        readiness = _build_assessment_readiness(tenant=tenant, assessment=assessment)
        result = evaluate_report_eligibility(readiness)
        run_id = result["compilation_run_id"]
        compilation_run = (
            CompilationRun.objects.filter(tenant=tenant, id=run_id).first()
            if run_id
            else None
        )
        ReportEligibilityRecord.objects.create(
            tenant=tenant,
            snapshot_run=snapshot_run,
            assessment=assessment,
            compilation_run=compilation_run,
            academic_year=assessment.academic_year,
            term=assessment.term,
            cohort=assessment.cohort,
            learning_area=assessment.learning_area,
            status=result["status"],
            readiness_status=result["readiness_status"],
            blocker_codes=result["blocker_codes"],
            source_readiness=readiness,
        )
        results.append(result)
    return results


def _eligible_compilation_ids(results: list[dict[str, Any]]) -> set[str]:
    return {
        result["compilation_run_id"]
        for result in results
        if result.get("eligible") and result.get("compilation_run_id")
    }


def _snapshot_source_rows(
    *,
    tenant: Any,
    compilation_run_ids: set[str],
) -> list[CompiledLearnerSnapshot]:
    if not compilation_run_ids:
        return []
    return list(
        CompiledLearnerSnapshot.objects.filter(
            tenant=tenant,
            compilation_run_id__in=compilation_run_ids,
            status=CompilationRun.Status.COMPLETE,
        )
        .select_related(
            "assessment",
            "student",
            "cohort",
            "learning_area",
            "curriculum_version",
            "rubric_foundation",
            "compilation_run",
        )
        .order_by("student_id", "learning_area__name", "assessment_id")
    )


def _build_report_snapshots(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun,
    source_rows: list[CompiledLearnerSnapshot],
) -> None:
    lines_by_student: dict[str, list[dict[str, Any]]] = {}
    rows_by_student: dict[str, list[CompiledLearnerSnapshot]] = {}
    for row in source_rows:
        line = build_subject_line_payload(compiled_snapshot=row)
        lines_by_student.setdefault(str(row.student_id), []).append(line)
        rows_by_student.setdefault(str(row.student_id), []).append(row)

    learner_by_student: dict[str, LearnerReportSnapshot] = {}
    for student_id, lines in sorted(lines_by_student.items()):
        row = rows_by_student[student_id][0]
        payload = build_learner_snapshot_payload(
            student_id=student_id,
            subject_lines=lines,
            readiness_status="ready_for_reports",
        )
        learner_by_student[student_id] = LearnerReportSnapshot.objects.create(
            tenant=tenant,
            snapshot_run=snapshot_run,
            student_id=student_id,
            academic_year=row.assessment.academic_year,
            term=row.assessment.term,
            cohort=row.cohort,
            subject_count=payload["subject_count"],
            total_score=Decimal(payload["total_score"]),
            average_percentage=Decimal(payload["average_percentage"]),
            source_compilation_run_ids=payload["source_compilation_run_ids"],
            readiness_status=payload["readiness_status"],
            correction_audit_state=payload["correction_audit_state"],
            context_snapshot=payload["context_snapshot"],
            schema_versions=payload["schema_versions"],
        )

    for row in source_rows:
        line = build_subject_line_payload(compiled_snapshot=row)
        ReportSubjectLineSnapshot.objects.create(
            tenant=tenant,
            snapshot_run=snapshot_run,
            learner_snapshot=learner_by_student[str(row.student_id)],
            compiled_learner_snapshot=row,
            compilation_run=row.compilation_run,
            assessment=row.assessment,
            student=row.student,
            academic_year=row.assessment.academic_year,
            term=row.assessment.term,
            cohort=row.cohort,
            learning_area=row.learning_area,
            curriculum_version=row.curriculum_version,
            rubric_foundation=row.rubric_foundation,
            school_grading_schema_version=line["school_grading_schema_version"],
            score_summary=line["score_summary"],
            component_summary=line["component_summary"],
            cbe_band_status=line["cbe_band_status"],
            internal_band_label=line["internal_band_label"],
            internal_band_descriptor=line["internal_band_descriptor"],
            status=line["status"],
        )


def _percentages(items: list[Any]) -> list[str]:
    return [str(getattr(item, "average_percentage", "0.00")) for item in items]


def _subject_percentages(items: list[Any]) -> list[str]:
    return [
        str((item.score_summary or {}).get("percentage", "0.00"))
        for item in items
    ]


def _create_aggregate(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun,
    scope_type: str,
    percentages: list[str],
    cohort: Any | None = None,
    learning_area: Any | None = None,
    stream_label: str = "",
    department_key: str = "",
) -> AcademicAggregate:
    metrics = build_scope_aggregate(scope_type=scope_type, percentages=percentages)
    return AcademicAggregate.objects.create(
        tenant=tenant,
        snapshot_run=snapshot_run,
        academic_year=snapshot_run.academic_year,
        term=snapshot_run.term,
        scope_type=scope_type,
        grade_level=(
            getattr(cohort, "grade_level", None) if cohort is not None else None
        ),
        cohort=cohort,
        learning_area=learning_area,
        stream_label=stream_label,
        department_key=department_key,
        metrics=metrics,
        min_group_size_met=bool(metrics["min_group_size_met"]),
    )


def compute_report_snapshot_aggregates(
    *,
    tenant: Any,
    snapshot_run: ReportSnapshotRun,
) -> list[AcademicAggregate]:
    learners = list(
        get_learner_report_snapshots(tenant=tenant, snapshot_run=snapshot_run)
    )
    lines = list(
        get_report_subject_line_snapshots(tenant=tenant, snapshot_run=snapshot_run)
    )
    aggregates = [
        _create_aggregate(
            tenant=tenant,
            snapshot_run=snapshot_run,
            scope_type=AcademicAggregate.ScopeType.SCHOOL,
            percentages=_percentages(learners),
        )
    ]

    cohorts = {learner.cohort_id: learner.cohort for learner in learners}
    for cohort_id, cohort in sorted(cohorts.items(), key=lambda item: str(item[0])):
        cohort_learners = [
            learner for learner in learners if learner.cohort_id == cohort_id
        ]
        aggregates.append(
            _create_aggregate(
                tenant=tenant,
                snapshot_run=snapshot_run,
                scope_type=AcademicAggregate.ScopeType.COHORT,
                percentages=_percentages(cohort_learners),
                cohort=cohort,
            )
        )
        stream_label = (
            getattr(cohort, "stream_label", "") or getattr(cohort, "name", "")
        )
        aggregates.append(
            _create_aggregate(
                tenant=tenant,
                snapshot_run=snapshot_run,
                scope_type=AcademicAggregate.ScopeType.STREAM,
                percentages=_percentages(cohort_learners),
                cohort=cohort,
                stream_label=stream_label,
            )
        )

    learning_areas = {line.learning_area_id: line.learning_area for line in lines}
    for learning_area_id, learning_area in sorted(
        learning_areas.items(), key=lambda item: str(item[0])
    ):
        subject_lines = [
            line for line in lines if line.learning_area_id == learning_area_id
        ]
        aggregates.append(
            _create_aggregate(
                tenant=tenant,
                snapshot_run=snapshot_run,
                scope_type=AcademicAggregate.ScopeType.SUBJECT,
                percentages=_subject_percentages(subject_lines),
                learning_area=learning_area,
            )
        )
        aggregates.append(
            _create_aggregate(
                tenant=tenant,
                snapshot_run=snapshot_run,
                scope_type=AcademicAggregate.ScopeType.DEPARTMENT,
                percentages=_subject_percentages(subject_lines),
                learning_area=learning_area,
                department_key=getattr(learning_area, "code", ""),
            )
        )
    return aggregates


@transaction.atomic
def create_report_snapshot_run(
    *,
    actor: Any,
    tenant: Any,
    academic_year: Any,
    term: Any,
    filters: dict[str, Any] | None = None,
) -> ReportSnapshotRun:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.report_snapshot.compute",
        role_codes=GRADING_ACADEMIC_HEAD_ROLE_CODES
        | {Role.RoleCode.PRINCIPAL.value},
    )
    if not can_compute_report_snapshot(context, tenant=tenant):
        raise ValidationError({"report_snapshot": "Report snapshot is not authorized."})
    assessments = list(
        get_academic_head_readiness_scope(
            tenant=tenant,
            filters={
                "academic_year_id": getattr(academic_year, "id", academic_year),
                "term_id": getattr(term, "id", term),
                **(filters or {}),
            },
        )
    )
    snapshot_run = ReportSnapshotRun.objects.create(
        tenant=tenant,
        academic_year=academic_year,
        term=term,
        requested_by=actor,
        status=ReportSnapshotRun.Status.RUNNING,
    )
    eligibility_results = _create_eligibility_records(
        tenant=tenant,
        snapshot_run=snapshot_run,
        assessments=assessments,
    )
    eligible_ids = _eligible_compilation_ids(eligibility_results)
    source_rows = _snapshot_source_rows(tenant=tenant, compilation_run_ids=eligible_ids)
    _build_report_snapshots(
        tenant=tenant,
        snapshot_run=snapshot_run,
        source_rows=source_rows,
    )
    compute_report_snapshot_aggregates(tenant=tenant, snapshot_run=snapshot_run)
    summary = summarize_eligibility(eligibility_results)
    status = (
        ReportSnapshotRun.Status.COMPLETE
        if summary["all_eligible"]
        else ReportSnapshotRun.Status.PARTIAL
        if summary["eligible_count"]
        else ReportSnapshotRun.Status.BLOCKED
    )
    snapshot_run.status = status
    snapshot_run.eligibility_summary = summary
    snapshot_run.source_compilation_run_ids = sorted(eligible_ids)
    snapshot_run.completed_at = timezone.now()
    snapshot_run.save(
        update_fields=[
            "status",
            "eligibility_summary",
            "source_compilation_run_ids",
            "completed_at",
            "updated_at",
        ]
    )
    return snapshot_run


def _latest_report_snapshot_run(*, tenant: Any) -> ReportSnapshotRun | None:
    if tenant is None:
        return None
    return (
        ReportSnapshotRun.objects.filter(
            tenant=tenant,
            status__in=[
                ReportSnapshotRun.Status.COMPLETE,
                ReportSnapshotRun.Status.PARTIAL,
            ],
        )
        .order_by("-completed_at", "-created_at")
        .first()
    )


def _learner_projection_items(
    snapshots: list[LearnerReportSnapshot],
) -> list[dict[str, Any]]:
    return [
        {
            "snapshot_id": str(snapshot.id),
            "student_id": str(snapshot.student_id),
            "cohort_id": str(snapshot.cohort_id),
            "average_percentage": str(snapshot.average_percentage),
            "subject_count": snapshot.subject_count,
        }
        for snapshot in snapshots
    ]


def _aggregate_projection_items(
    aggregates: list[AcademicAggregate],
) -> list[dict[str, Any]]:
    return [
        {
            "aggregate_id": str(aggregate.id),
            "scope_type": aggregate.scope_type,
            "cohort_id": str(aggregate.cohort_id or ""),
            "learning_area_id": str(aggregate.learning_area_id or ""),
            "stream_label": aggregate.stream_label,
            "department_key": aggregate.department_key,
            "metrics": aggregate.metrics,
            "min_group_size_met": aggregate.min_group_size_met,
        }
        for aggregate in aggregates
    ]


def _analytics_projection(
    *,
    projection_type: str,
    snapshot_run: ReportSnapshotRun | None,
    learners: list[LearnerReportSnapshot],
    aggregates: list[AcademicAggregate],
) -> dict[str, Any]:
    return build_role_analytics_projection(
        projection_type=projection_type,
        learner_snapshots=_learner_projection_items(learners),
        aggregates=_aggregate_projection_items(aggregates),
        readiness_summary=(
            snapshot_run.eligibility_summary if snapshot_run is not None else {}
        ),
    )


def get_principal_analytics_projection(*, actor: Any, tenant: Any) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.principal.view",
        role_codes={Role.RoleCode.PRINCIPAL.value, Role.RoleCode.SCHOOL_ADMIN.value},
    )
    if not can_view_principal_analytics(context):
        return _analytics_projection(
            projection_type="principal",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    snapshot_run = _latest_report_snapshot_run(tenant=tenant)
    if snapshot_run is None:
        return _analytics_projection(
            projection_type="principal",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    learners = list(
        get_learner_report_snapshots(tenant=tenant, snapshot_run=snapshot_run)
    )
    aggregates = list(
        get_academic_aggregates(tenant=tenant, snapshot_run=snapshot_run)
    )
    return _analytics_projection(
        projection_type="principal",
        snapshot_run=snapshot_run,
        learners=learners,
        aggregates=aggregates,
    )


def get_deputy_analytics_projection(*, actor: Any, tenant: Any) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.deputy.view",
        role_codes={
            Role.RoleCode.DEPUTY_PRINCIPAL.value,
            Role.RoleCode.PRINCIPAL.value,
            Role.RoleCode.SCHOOL_ADMIN.value,
        },
    )
    if not can_view_deputy_analytics(context):
        return _analytics_projection(
            projection_type="deputy_head_academics",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    snapshot_run = _latest_report_snapshot_run(tenant=tenant)
    if snapshot_run is None:
        return _analytics_projection(
            projection_type="deputy_head_academics",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    learners = list(
        get_learner_report_snapshots(tenant=tenant, snapshot_run=snapshot_run)
    )
    aggregates = list(
        get_academic_aggregates(tenant=tenant, snapshot_run=snapshot_run)
    )
    return _analytics_projection(
        projection_type="deputy_head_academics",
        snapshot_run=snapshot_run,
        learners=learners,
        aggregates=aggregates,
    )


def get_hod_analytics_projection(*, actor: Any, tenant: Any) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.hod.view",
        role_codes={Role.RoleCode.HOD.value},
    )
    snapshot_run = _latest_report_snapshot_run(tenant=tenant)
    if snapshot_run is None:
        return _analytics_projection(
            projection_type="hod",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    lines = list(
        get_report_subject_line_snapshots(
            tenant=tenant,
            snapshot_run=snapshot_run,
            actor=actor,
        )
    )
    if not lines:
        return _analytics_projection(
            projection_type="hod",
            snapshot_run=snapshot_run,
            learners=[],
            aggregates=[],
        )
    visible_learning_area_ids = {
        line.learning_area_id
        for line in lines
        if can_view_hod_analytics(context, assessment=line.assessment)
    }
    aggregates = [
        aggregate
        for aggregate in get_academic_aggregates(
            tenant=tenant,
            snapshot_run=snapshot_run,
        )
        if aggregate.learning_area_id in visible_learning_area_ids
        and can_view_hod_analytics(context, aggregate=aggregate)
    ]
    learner_ids = {
        line.student_id
        for line in lines
        if line.learning_area_id in visible_learning_area_ids
    }
    learners = list(
        get_learner_report_snapshots(tenant=tenant, snapshot_run=snapshot_run).filter(
            student_id__in=learner_ids
        )
    )
    return _analytics_projection(
        projection_type="hod",
        snapshot_run=snapshot_run,
        learners=learners,
        aggregates=aggregates,
    )


def get_class_teacher_analytics_projection(
    *,
    actor: Any,
    tenant: Any,
    cohort_id: Any,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.class_teacher.view",
        role_codes={Role.RoleCode.CLASS_TEACHER.value, Role.RoleCode.HOD.value},
    )
    if not can_view_class_teacher_analytics(context, cohort_id=cohort_id):
        return _analytics_projection(
            projection_type="class_teacher",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    snapshot_run = _latest_report_snapshot_run(tenant=tenant)
    if snapshot_run is None:
        return _analytics_projection(
            projection_type="class_teacher",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    learners = list(
        get_learner_report_snapshots(
            tenant=tenant,
            snapshot_run=snapshot_run,
            cohort_id=cohort_id,
        )
    )
    aggregates = list(
        get_academic_aggregates(
            tenant=tenant,
            snapshot_run=snapshot_run,
            cohort_id=cohort_id,
        )
    )
    return _analytics_projection(
        projection_type="class_teacher",
        snapshot_run=snapshot_run,
        learners=learners,
        aggregates=aggregates,
    )


def get_subject_teacher_analytics_projection(
    *,
    actor: Any,
    tenant: Any,
    learning_area_id: Any,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.subject_teacher.view",
        role_codes={Role.RoleCode.SUBJECT_TEACHER.value, Role.RoleCode.HOD.value},
    )
    snapshot_run = _latest_report_snapshot_run(tenant=tenant)
    if snapshot_run is None:
        return _analytics_projection(
            projection_type="subject_teacher",
            snapshot_run=None,
            learners=[],
            aggregates=[],
        )
    lines = list(
        get_report_subject_line_snapshots(
            tenant=tenant,
            snapshot_run=snapshot_run,
            learning_area_id=learning_area_id,
            actor=actor,
        )
    )
    visible = [
        line
        for line in lines
        if can_view_subject_teacher_analytics(context, subject_line=line)
    ]
    learner_ids = {line.student_id for line in visible}
    learners = list(
        get_learner_report_snapshots(tenant=tenant, snapshot_run=snapshot_run).filter(
            student_id__in=learner_ids
        )
    )
    aggregates = list(
        get_academic_aggregates(
            tenant=tenant,
            snapshot_run=snapshot_run,
            learning_area_id=learning_area_id,
        )
    )
    return _analytics_projection(
        projection_type="subject_teacher",
        snapshot_run=snapshot_run,
        learners=learners,
        aggregates=aggregates,
    )


def get_future_parent_snapshot_projection(
    *,
    actor: Any,
    tenant: Any,
    learner_id: Any,
) -> dict[str, Any]:
    context = _policy_context(
        actor=actor,
        tenant=tenant,
        action="grading.analytics.future_parent.view",
        role_codes={Role.RoleCode.GUARDIAN.value},
    )
    if not can_view_future_parent_snapshot(context, tenant=tenant):
        return build_future_parent_snapshot_projection()
    return build_future_parent_snapshot_projection()
