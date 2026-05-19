from __future__ import annotations

import json
import uuid
from decimal import Decimal
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import CustomUser, Role, TenantUserRole
from curriculum.models import (
    CurriculumAppImpactPlan,
    CurriculumEvidenceSubmission,
    CurriculumVerificationReport,
    SchoolCurriculumAdoption,
)
from grading.models import (
    CompilationRun,
    CompiledCohortSummary,
    CompiledLearnerSnapshot,
    GradeRecord,
)
from grading.services import (
    compile_assessment,
    compute_assessment_readiness,
    compute_school_report_readiness,
    get_future_parent_report_readiness_projection,
    get_principal_readiness_projection,
    get_teacher_readiness_projection,
    save_grade_draft,
    submit_grade_batch,
)


pytestmark = [
    pytest.mark.django_db,
    pytest.mark.phase6,
    pytest.mark.grading,
    pytest.mark.redteam,
    pytest.mark.security,
]


def _confirmation(actor, tenant) -> dict[str, object]:
    return {
        "confirmed": True,
        "actor_id": str(actor.id),
        "tenant_id": str(tenant.id),
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase6d-redteam",
    }


def _row(student, score: str = "80.00") -> dict[str, str]:
    return {"student_id": str(student.id), "raw_score": score}


def _submit_and_compile(school, assessment, teacher_user, principal_user, student):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(student)]},
        idempotency_key=f"phase6d-redteam-submit-{uuid.uuid4().hex}",
        confirmation=_confirmation(teacher_user, school),
    )
    return compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )


def _blocker_codes(readiness):
    return {item["code"] for item in readiness["blockers"]}


def _role_user(school, role_code: str, *, is_active: bool = True) -> CustomUser:
    role, _ = Role.objects.get_or_create(
        code=role_code,
        defaults={"name": role_code.replace("_", " ").title()},
    )
    user = CustomUser.objects.create_user(
        email=f"phase6d-redteam-{role_code}-{uuid.uuid4().hex[:8]}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(
        tenant=school,
        user=user,
        role=role,
        is_active=is_active,
    )
    return user


def _checksum() -> str:
    return "sha256:" + uuid.uuid4().hex + uuid.uuid4().hex


def _create_app_impact_plan(
    *,
    school,
    actor,
    app_domain: str,
    affected_scope: dict[str, str],
) -> CurriculumAppImpactPlan:
    token = uuid.uuid4().hex
    submission = CurriculumEvidenceSubmission.objects.create(
        tenant=school,
        submitted_by=actor,
        submitter_role=Role.RoleCode.PRINCIPAL.value,
        storage_reference=f"private://phase6d-redteam/{token}.pdf",
        file_name=f"phase6d-redteam-{token}.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        file_checksum=_checksum(),
        evidence_fingerprint=_checksum(),
        claimed_authority="moe",
        claimed_scope=affected_scope,
    )
    report = CurriculumVerificationReport.objects.create(
        tenant=school,
        evidence_submission=submission,
        candidate_id=uuid.uuid4(),
        fingerprint=submission.evidence_fingerprint,
        scope_guess=affected_scope,
        sla_due_at=timezone.now() + timedelta(hours=24),
    )
    return CurriculumAppImpactPlan.objects.create(
        tenant=school,
        verification_report=report,
        app_domain=app_domain,
        impact_type="review_required",
        affected_scope=affected_scope,
        required_action="review_before_activation",
        safe_behavior="Readiness must review applicable CCT scope.",
        historical_protection_rule="Existing academic history remains unchanged.",
    )


def test_draft_only_work_cannot_fake_report_readiness(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    principal_user,
):
    save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "72.00")]},
        idempotency_key="phase6d-redteam-draft-only",
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert not readiness["report_ready"]
    assert readiness["readiness_status"] == "in_progress"
    assert {
        "no_compilation",
        "teacher_submission_missing",
        "draft_unsubmitted",
    } <= _blocker_codes(readiness)


def test_older_null_timestamp_run_does_not_hide_latest_completed_compilation(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    principal_user,
):
    CompilationRun.objects.create(
        tenant=school,
        assessment=assessment,
        requested_by=principal_user,
        status=CompilationRun.Status.STALE,
        compiled_at=None,
    )
    run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert readiness["compilation_run_id"] == str(run.id)
    assert readiness["report_ready"]
    assert "stale_compilation" not in _blocker_codes(readiness)


def test_cct_app_impact_blocks_only_applicable_readiness_scope(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    principal_user,
):
    school.metadata = {
        "county": "Nairobi",
        "region": "Nairobi Metropolitan",
        "senior_school_pathway": "STEM",
    }
    school.save(update_fields=["metadata", "updated_at"])
    _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )

    _create_app_impact_plan(
        school=school,
        actor=principal_user,
        app_domain="grading",
        affected_scope={
            "county": "Mombasa",
            "learning_area": assessment.learning_area.name,
        },
    )
    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    assert readiness["report_ready"]
    assert "cct_app_impact_review_required" not in _blocker_codes(readiness)

    _create_app_impact_plan(
        school=school,
        actor=principal_user,
        app_domain="grading",
        affected_scope={
            "county": "Nairobi",
            "learning_area": assessment.learning_area.name,
        },
    )
    blocked = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    assert not blocked["report_ready"]
    assert "cct_app_impact_review_required" in _blocker_codes(blocked)


def test_is_staff_parent_and_principal_projection_boundaries_are_safe(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    principal_user,
):
    _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    staff = CustomUser.objects.create_user(
        email=f"phase6d-staff-{uuid.uuid4().hex[:8]}@example.test",
        password="test-only-secret",
        is_staff=True,
    )
    guardian = _role_user(school, Role.RoleCode.GUARDIAN.value)

    assert get_principal_readiness_projection(
        actor=staff,
        tenant=school,
    )["assessment_count"] == 0
    parent_projection = get_future_parent_report_readiness_projection(
        actor=guardian,
        tenant=school,
        learner_id=enrolled_student.id,
    )
    assert parent_projection["ready_for_release"] is False
    assert parent_projection["assessments"] == []

    principal_projection = get_principal_readiness_projection(
        actor=principal_user,
        tenant=school,
    )
    encoded = json.dumps(principal_projection, sort_keys=True)
    assert "raw_score" not in encoded
    assert "component_scores" not in encoded
    assert "grade_records" not in encoded
    assert "learner_names" not in encoded
    assert "guardian" not in encoded


def test_readiness_services_do_not_mutate_grading_or_cct_history(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    principal_user,
):
    run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    grade_record = GradeRecord.objects.get(
        tenant=school,
        assessment=assessment,
        student=enrolled_student,
    )
    batch = grade_record.submission_batch
    learner_snapshot = CompiledLearnerSnapshot.objects.get(compilation_run=run)
    cohort_summary = CompiledCohortSummary.objects.get(compilation_run=run)
    adoption = SchoolCurriculumAdoption.objects.get(
        tenant=school,
        curriculum_version=assessment.curriculum_version,
    )
    before = {
        "assessment_curriculum_version": assessment.curriculum_version_id,
        "assessment_rubric": assessment.rubric_foundation_id,
        "grade_score": Decimal(grade_record.raw_score),
        "batch_status": batch.status,
        "run_status": run.status,
        "learner_score_summary": learner_snapshot.score_summary,
        "learner_component_summary": learner_snapshot.component_summary,
        "cohort_status": cohort_summary.status,
        "adoption_status": adoption.status,
    }

    compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    compute_school_report_readiness(actor=principal_user, tenant=school)
    get_teacher_readiness_projection(actor=teacher_user, tenant=school)
    get_principal_readiness_projection(actor=principal_user, tenant=school)

    assessment.refresh_from_db()
    grade_record.refresh_from_db()
    batch.refresh_from_db()
    run.refresh_from_db()
    learner_snapshot.refresh_from_db()
    cohort_summary.refresh_from_db()
    adoption.refresh_from_db()
    after = {
        "assessment_curriculum_version": assessment.curriculum_version_id,
        "assessment_rubric": assessment.rubric_foundation_id,
        "grade_score": Decimal(grade_record.raw_score),
        "batch_status": batch.status,
        "run_status": run.status,
        "learner_score_summary": learner_snapshot.score_summary,
        "learner_component_summary": learner_snapshot.component_summary,
        "cohort_status": cohort_summary.status,
        "adoption_status": adoption.status,
    }

    assert after == before


def test_client_controlled_readiness_payloads_are_not_accepted(
    school,
    assessment,
    principal_user,
):
    with pytest.raises(TypeError):
        compute_assessment_readiness(
            actor=principal_user,
            tenant=school,
            assessment_id=assessment.id,
            status="ready_for_reports",
            blockers=[],
            ignore_missing_marks=True,
            override_cct_blocker=True,
        )

    with pytest.raises(ValidationError):
        compute_assessment_readiness(
            actor=None,
            tenant=school,
            assessment_id=assessment.id,
        )
