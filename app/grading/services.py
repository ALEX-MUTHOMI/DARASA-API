"""Write services for the grading workflow.

Phase 6B adds draft and final submission orchestration while keeping CBE/CCT
binding, tenant context, teacher identity, and event payloads server-derived.
"""

from __future__ import annotations

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
from grading.algorithms.draft_merge import (
    normalize_draft_rows,
    validate_draft_version,
)
from grading.algorithms.grade_grid_builder import build_grid_contract
from grading.algorithms.learner_snapshot_builder import build_learner_snapshots
from grading.algorithms.missing_marks import detect_missing_marks
from grading.algorithms.role_projection_builder import build_role_projection
from grading.algorithms.roster_resolver import stable_roster_rows
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
    CompilationRun,
    CompiledAssessmentSnapshot,
    CompiledCohortSummary,
    CompiledLearnerSnapshot,
    GradeDraftBatch,
    GradeDraftRow,
    GradeRecord,
    GradeSubmissionBatch,
)
from grading.policies import (
    can_compile_assessment,
    can_view_deputy_academics_compilation,
    can_view_future_parent_projection,
    can_view_hod_compilation,
    can_view_principal_compilation,
    can_view_teacher_compilation,
)
from grading.selectors import (
    get_assessment_for_teacher,
    get_assessment_components_for_compilation,
    get_compiled_learner_snapshots,
    get_expected_roster_for_compilation,
    get_existing_draft_for_teacher,
    get_existing_submission_for_assessment,
    get_hod_compilation_scope,
    get_principal_compilation_scope,
    get_roster_for_assessment,
    get_submitted_records_for_assessment,
    get_teacher_compilation_scope,
    get_teacher_grading_contexts,
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
