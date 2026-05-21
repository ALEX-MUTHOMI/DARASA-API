"""Fail-closed grading ABAC policies.

Grades are academic records.  A tenant role proves broad capability, while an
active teacher assignment proves contextual authority for a cohort and learning
area.
"""

from __future__ import annotations

from typing import Any

from academics.models import TeacherAssignment
from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant
from grading.models import (
    Assessment,
    AcademicAggregate,
    GradeCorrectionRequest,
    GradeRecord,
    LearnerReportSnapshot,
    ReportSnapshotRun,
    ReportSubjectLineSnapshot,
    SchoolGradingSchema,
)


GRADING_ADMIN_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.HOD.value,
    }
)
GRADING_EXECUTIVE_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.DEPUTY_PRINCIPAL.value,
    }
)
GRADING_ACADEMIC_HEAD_ROLES = frozenset(
    {
        Role.RoleCode.DEPUTY_PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }
)
GRADING_TEACHER_ROLES = frozenset(
    {
        Role.RoleCode.SUBJECT_TEACHER.value,
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.HOD.value,
    }
)


def _context_is_valid(context: PolicyContext) -> bool:
    if context.tenant is None:
        return False
    if context.actor is None or not context.actor.is_active:
        return False
    if context.role is None or not context.role.is_active:
        return False
    if not context.action:
        return False
    return user_has_role_in_tenant(
        user=context.actor,
        tenant=context.tenant,
        role_code=context.role.code,
    )


def _in_tenant(context: PolicyContext, resource: Any) -> bool:
    return (
        context.tenant is not None
        and getattr(resource, "tenant_id", None) == context.tenant.id
    )


def _is_admin(context: PolicyContext) -> bool:
    return _context_is_valid(context) and context.role.code in GRADING_ADMIN_ROLES


def _has_assignment_for_assessment(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if not _context_is_valid(context) or context.role.code not in GRADING_TEACHER_ROLES:
        return False
    if not _in_tenant(context, assessment):
        return False
    return TeacherAssignment.objects.filter(
        tenant=context.tenant,
        teacher=context.actor,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
        is_active=True,
        cohort__is_active=True,
        learning_area__is_active=True,
    ).exists()


def can_view_grading_context(context: PolicyContext, *, assessment: Assessment) -> bool:
    if not _in_tenant(context, assessment):
        return False
    return _is_admin(context) or _has_assignment_for_assessment(
        context,
        assessment=assessment,
    )


def can_view_assessment(context: PolicyContext, *, assessment: Assessment) -> bool:
    return context.action == "grading.assessment.view" and can_view_grading_context(
        context,
        assessment=assessment,
    )


def can_enter_grades(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.grades.enter":
        return False
    if assessment.status != Assessment.Status.OPEN:
        return False
    if not assessment.is_operationally_bound():
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_submit_grade_batch(context: PolicyContext, *, assessment: Assessment) -> bool:
    return context.action == "grading.batch.submit" and can_enter_grades(
        PolicyContext(
            tenant=context.tenant,
            actor=context.actor,
            action="grading.grades.enter",
            role=context.role,
        ),
        assessment=assessment,
    )


def can_view_grade_records(
    context: PolicyContext,
    *,
    grade_record: GradeRecord,
) -> bool:
    if context.action != "grading.records.view":
        return False
    if not _in_tenant(context, grade_record):
        return False
    return _is_admin(context) or _has_assignment_for_assessment(
        context,
        assessment=grade_record.assessment,
    )


def can_request_grade_correction(
    context: PolicyContext,
    *,
    grade_record: GradeRecord,
) -> bool:
    if context.action != "grading.correction.request":
        return False
    return can_view_grade_records(
        PolicyContext(
            tenant=context.tenant,
            actor=context.actor,
            action="grading.records.view",
            role=context.role,
        ),
        grade_record=grade_record,
    )


def can_review_grade_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.review":
        return False
    if not _in_tenant(context, correction):
        return False
    if correction.requested_by_id == getattr(context.actor, "id", None):
        return False
    return _is_admin(context)


def can_submit_correction_request(
    context: PolicyContext,
    *,
    grade_record: GradeRecord,
) -> bool:
    if context.action != "grading.correction.submit":
        return False
    return can_request_grade_correction(
        PolicyContext(
            tenant=context.tenant,
            actor=context.actor,
            action="grading.correction.request",
            role=context.role,
        ),
        grade_record=grade_record,
    )


def can_review_hod_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.hod.review":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code != Role.RoleCode.HOD.value:
        return False
    if not _in_tenant(context, correction):
        return False
    if correction.requested_by_id == getattr(context.actor, "id", None):
        return False
    return _has_assignment_for_assessment(
        context,
        assessment=correction.grade_record.assessment,
    )


def can_escalate_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.escalate":
        return False
    if not _context_is_valid(context) or not _in_tenant(context, correction):
        return False
    return context.role.code in GRADING_ACADEMIC_HEAD_ROLES


def can_review_academic_head_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.academic_head.review":
        return False
    if not _context_is_valid(context) or not _in_tenant(context, correction):
        return False
    if correction.requested_by_id == getattr(context.actor, "id", None):
        return False
    return context.role.code in GRADING_ACADEMIC_HEAD_ROLES


def can_apply_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.apply":
        return False
    if not _context_is_valid(context) or not _in_tenant(context, correction):
        return False
    if correction.requested_by_id == getattr(context.actor, "id", None):
        return False
    if context.role.code == Role.RoleCode.HOD.value:
        return _has_assignment_for_assessment(
            context,
            assessment=correction.grade_record.assessment,
        )
    return context.role.code in GRADING_ACADEMIC_HEAD_ROLES


def can_view_correction_audit(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.audit.view":
        return False
    if not _in_tenant(context, correction):
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code in GRADING_EXECUTIVE_ROLES:
        return True
    if context.role.code == Role.RoleCode.HOD.value:
        return _has_assignment_for_assessment(
            context,
            assessment=correction.grade_record.assessment,
        )
    return correction.requested_by_id == getattr(context.actor, "id", None)


def can_view_principal_correction_summary(context: PolicyContext) -> bool:
    if context.action != "grading.correction.principal.summary.view":
        return False
    if not _context_is_valid(context):
        return False
    return context.role.code in {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }


def can_manage_school_grading_schema(
    context: PolicyContext,
    *,
    action: str,
    schema: SchoolGradingSchema | None = None,
    assessment: Assessment | None = None,
) -> bool:
    if context.action != action:
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in GRADING_ACADEMIC_HEAD_ROLES | {
        Role.RoleCode.PRINCIPAL.value,
    }:
        return False
    if schema is not None and not _in_tenant(context, schema):
        return False
    if assessment is not None and not _in_tenant(context, assessment):
        return False
    return True


def can_view_grade_completion_summary(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if context.action != "grading.summary.view":
        return False
    if not _in_tenant(context, assessment):
        return False
    if not assessment.is_operationally_bound():
        return False
    return _is_admin(context)


def can_compile_assessment(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.compilation.compile":
        return False
    if not _in_tenant(context, assessment):
        return False
    if not assessment.is_operationally_bound():
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code in {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }:
        return True
    if context.role.code == Role.RoleCode.HOD.value:
        return _has_assignment_for_assessment(context, assessment=assessment)
    return False


def can_view_teacher_compilation(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if context.action != "grading.compilation.teacher.view":
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_view_hod_compilation(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.compilation.hod.view":
        return False
    if not _in_tenant(context, assessment):
        return False
    if not _context_is_valid(context) or context.role.code != Role.RoleCode.HOD.value:
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_view_deputy_academics_compilation(
    context: PolicyContext,
    *,
    assessment: Assessment | None = None,
) -> bool:
    if context.action != "grading.compilation.deputy.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in GRADING_EXECUTIVE_ROLES:
        return False
    return assessment is None or _in_tenant(context, assessment)


def can_view_principal_compilation(
    context: PolicyContext,
    *,
    assessment: Assessment | None = None,
) -> bool:
    if context.action != "grading.compilation.principal.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }:
        return False
    return assessment is None or _in_tenant(context, assessment)


def can_view_future_parent_projection(context: PolicyContext, *, tenant: Any) -> bool:
    """Fail closed until an explicit guardian-learner mapping exists."""

    if context.action != "grading.compilation.future_parent.view":
        return False
    if context.tenant != tenant:
        return False
    return False


def can_compute_readiness(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.readiness.compute":
        return False
    if not _in_tenant(context, assessment):
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code in GRADING_EXECUTIVE_ROLES:
        return True
    if context.role.code == Role.RoleCode.HOD.value:
        return _has_assignment_for_assessment(context, assessment=assessment)
    return False


def can_view_teacher_readiness(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if context.action != "grading.readiness.teacher.view":
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_view_hod_readiness(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.readiness.hod.view":
        return False
    if not _context_is_valid(context) or context.role.code != Role.RoleCode.HOD.value:
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_view_academic_head_readiness(
    context: PolicyContext,
    *,
    assessment: Assessment | None = None,
) -> bool:
    if context.action != "grading.readiness.academic_head.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in GRADING_EXECUTIVE_ROLES:
        return False
    return assessment is None or _in_tenant(context, assessment)


def can_view_principal_readiness(
    context: PolicyContext,
    *,
    assessment: Assessment | None = None,
) -> bool:
    if context.action != "grading.readiness.principal.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }:
        return False
    return assessment is None or _in_tenant(context, assessment)


def can_view_future_parent_readiness(context: PolicyContext, *, tenant: Any) -> bool:
    """Fail closed until approved report-release and guardian mapping exist."""

    if context.action != "grading.readiness.future_parent.view":
        return False
    if context.tenant != tenant:
        return False
    return False


def can_compute_report_snapshot(
    context: PolicyContext,
    *,
    tenant: Any,
) -> bool:
    if context.action != "grading.report_snapshot.compute":
        return False
    if context.tenant != tenant:
        return False
    if not _context_is_valid(context):
        return False
    return context.role.code in GRADING_EXECUTIVE_ROLES


def can_view_report_snapshot(
    context: PolicyContext,
    *,
    snapshot: LearnerReportSnapshot | ReportSubjectLineSnapshot | ReportSnapshotRun,
) -> bool:
    if context.action != "grading.report_snapshot.view":
        return False
    if not _context_is_valid(context) or not _in_tenant(context, snapshot):
        return False
    return context.role.code in GRADING_EXECUTIVE_ROLES | GRADING_TEACHER_ROLES


def can_view_principal_analytics(context: PolicyContext) -> bool:
    if context.action != "grading.analytics.principal.view":
        return False
    if not _context_is_valid(context):
        return False
    return context.role.code in {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }


def can_view_deputy_analytics(context: PolicyContext) -> bool:
    if context.action != "grading.analytics.deputy.view":
        return False
    if not _context_is_valid(context):
        return False
    return context.role.code in GRADING_EXECUTIVE_ROLES


def can_view_hod_analytics(
    context: PolicyContext,
    *,
    assessment: Assessment | None = None,
    aggregate: AcademicAggregate | None = None,
) -> bool:
    if context.action != "grading.analytics.hod.view":
        return False
    if not _context_is_valid(context) or context.role.code != Role.RoleCode.HOD.value:
        return False
    if assessment is not None:
        return _has_assignment_for_assessment(context, assessment=assessment)
    if aggregate is not None and aggregate.learning_area_id is not None:
        return TeacherAssignment.objects.filter(
            tenant=context.tenant,
            teacher=context.actor,
            learning_area_id=aggregate.learning_area_id,
            academic_year=aggregate.academic_year,
            term=aggregate.term,
            is_active=True,
        ).exists()
    return False


def can_view_teacher_analytics(
    context: PolicyContext,
    *,
    subject_line: ReportSubjectLineSnapshot | None = None,
) -> bool:
    if context.action != "grading.analytics.teacher.view":
        return False
    if not _context_is_valid(context):
        return False
    if subject_line is None:
        return context.role.code in GRADING_TEACHER_ROLES
    return _has_assignment_for_assessment(context, assessment=subject_line.assessment)


def can_view_subject_teacher_analytics(
    context: PolicyContext,
    *,
    subject_line: ReportSubjectLineSnapshot | None = None,
) -> bool:
    if context.action != "grading.analytics.subject_teacher.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in {
        Role.RoleCode.SUBJECT_TEACHER.value,
        Role.RoleCode.HOD.value,
    }:
        return False
    if subject_line is None:
        return True
    return _has_assignment_for_assessment(context, assessment=subject_line.assessment)


def can_view_class_teacher_analytics(
    context: PolicyContext,
    *,
    learner_snapshot: LearnerReportSnapshot | None = None,
    cohort_id: Any | None = None,
) -> bool:
    if context.action != "grading.analytics.class_teacher.view":
        return False
    if not _context_is_valid(context):
        return False
    if context.role.code not in {
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.HOD.value,
    }:
        return False
    target_cohort_id = (
        getattr(learner_snapshot, "cohort_id", None)
        if learner_snapshot is not None
        else cohort_id
    )
    if target_cohort_id is None:
        return False
    return TeacherAssignment.objects.filter(
        tenant=context.tenant,
        teacher=context.actor,
        cohort_id=target_cohort_id,
        is_active=True,
    ).exists()


def can_view_future_parent_snapshot(context: PolicyContext, *, tenant: Any) -> bool:
    """Fail closed until approved report release and guardian mapping exist."""

    if context.action != "grading.analytics.future_parent.view":
        return False
    if context.tenant != tenant:
        return False
    return False
