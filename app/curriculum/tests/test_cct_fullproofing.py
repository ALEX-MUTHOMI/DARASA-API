from __future__ import annotations

from datetime import date, timedelta
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import CustomUser, Role, TenantUserRole
from core.policies import PolicyContext
from curriculum.models import (
    CurriculumAppImpactPlan,
    CurriculumEvidenceSubmission,
    CurriculumGovernanceDecision,
    CurriculumPublication,
    CurriculumRollbackCandidate,
    CurriculumVerificationReport,
    SchoolCurriculumAdoption,
)
from curriculum.policies import (
    can_record_curriculum_governance_decision,
    can_submit_curriculum_evidence,
)
from curriculum.selectors import (
    get_curriculum_app_impact_plans,
    get_curriculum_evidence_submissions,
    get_curriculum_governance_decisions,
    get_curriculum_rollback_candidates,
    get_curriculum_verification_reports,
)
from curriculum.services import (
    create_curriculum_publication,
    create_curriculum_rollback_candidate,
    create_curriculum_verification_report,
    plan_curriculum_app_impacts,
    record_governance_decision,
    register_curriculum_authority,
    submit_curriculum_evidence,
)
from events.models import EventOutbox, EventTypeRegistry
from events.services import write_outbox_event
from tenant.models import School


pytestmark = [pytest.mark.django_db, pytest.mark.curriculum, pytest.mark.security]


def _payload(
    *,
    storage_reference: str = "private://school/evidence.pdf",
    checksum: str | None = None,
    claimed_scope: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "storage_reference": storage_reference,
        "filename": "curriculum-circular.pdf",
        "content_type": "application/pdf",
        "size_bytes": 4096,
        "file_checksum": checksum or ("sha256:" + "a" * 64),
        "claimed_authority": "moe",
        "claimed_source_reference": "MOE circular reference",
        "claimed_reference_number": "MOE/CUR/2026/001",
        "claimed_publication_number": "PUB/2026/001",
        "claimed_publication_date": date(2026, 5, 1),
        "claimed_effective_date": date(2026, 6, 1),
        "claimed_scope": claimed_scope,
    }


def _role_user(school: School, role_code: str) -> CustomUser:
    role, _ = Role.objects.get_or_create(
        code=role_code,
        defaults={"name": role_code.replace("_", " ").title()},
    )
    user = CustomUser.objects.create_user(
        email=f"{role_code}-{uuid.uuid4().hex[:8]}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def _other_school() -> School:
    token = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"Fullproof Other {token}",
        schema_name=f"fullproof_{token}",
        subdomain=f"fullproof-{token}",
        school_code=f"FP{token[:6]}".upper(),
    )


def _authority():
    return register_curriculum_authority(
        code="moe",
        name="Ministry of Education",
        official_website="https://education.go.ke",
        allowed_domains=["education.go.ke"],
    )


def test_principal_and_deputy_submit_quarantined_evidence_but_teacher_denied(
    principal_role,
    principal_user,
    school,
    teacher_user,
):
    deputy = _role_user(school, Role.RoleCode.DEPUTY_PRINCIPAL.value)

    principal_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.submit_evidence",
        role=principal_role,
    )
    assert can_submit_curriculum_evidence(principal_context)

    principal_submission = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload={**_payload(), "status": "governance_ready"},
    )
    deputy_submission = submit_curriculum_evidence(
        actor=deputy,
        tenant=school,
        payload=_payload(
            storage_reference="private://school/deputy-evidence.pdf",
            checksum="sha256:" + "b" * 64,
        ),
    )

    assert (
        principal_submission.status
        == CurriculumEvidenceSubmission.Status.QUARANTINED
    )
    assert deputy_submission.status == CurriculumEvidenceSubmission.Status.QUARANTINED
    assert principal_submission.evidence_fingerprint.startswith("sha256:")
    assert CurriculumPublication.objects.count() == 0

    with pytest.raises(ValidationError):
        submit_curriculum_evidence(
            actor=teacher_user,
            tenant=school,
            payload=_payload(storage_reference="private://school/teacher.pdf"),
        )


def test_duplicate_evidence_clusters_by_document_identity_not_storage(
    principal_user,
    school,
):
    first = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(storage_reference="private://school/first.pdf"),
    )
    duplicate = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(storage_reference="private://school/second.pdf"),
    )

    assert duplicate.status == CurriculumEvidenceSubmission.Status.DUPLICATE_ATTACHED
    assert duplicate.duplicate_of == first
    assert duplicate.duplicate_cluster_id == first.duplicate_cluster_id
    assert list(get_curriculum_evidence_submissions(tenant=school)) == [
        duplicate,
        first,
    ]


def test_cross_tenant_duplicate_does_not_expose_original_submission(
    principal_role,
    principal_user,
    school,
):
    other = _other_school()
    other_principal = _role_user(other, principal_role.code)
    original = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(storage_reference="private://school/original.pdf"),
    )
    duplicate = submit_curriculum_evidence(
        actor=other_principal,
        tenant=other,
        payload=_payload(storage_reference="private://other/duplicate.pdf"),
    )

    assert duplicate.status == CurriculumEvidenceSubmission.Status.DUPLICATE_ATTACHED
    assert duplicate.duplicate_of is None
    assert duplicate.duplicate_cluster_id == original.duplicate_cluster_id
    assert duplicate not in list(get_curriculum_evidence_submissions(tenant=school))

    with pytest.raises(ValidationError):
        submit_curriculum_evidence(
            actor=principal_user,
            tenant=other,
            payload=_payload(storage_reference="private://other/forged.pdf"),
        )


def test_upload_metadata_rejects_unsafe_files_urls_and_html(
    principal_user,
    school,
):
    unsafe_payloads = [
        {**_payload(), "filename": "../evil.pdf"},
        {**_payload(), "filename": "<script>alert(1)</script>.pdf"},
        {**_payload(), "content_type": "text/html"},
        {**_payload(), "size_bytes": 0},
        {
            **_payload(),
            "claimed_authority": '<img src=x onerror=alert(1)>',
        },
        {
            **_payload(),
            "claimed_source_url": "http://education.go.ke/circular.pdf",
        },
        {
            **_payload(),
            "claimed_source_url": "https://education.go.ke.evil.test/circular.pdf",
        },
    ]

    _authority()
    for payload in unsafe_payloads:
        with pytest.raises(ValidationError):
            submit_curriculum_evidence(
                actor=principal_user,
                tenant=school,
                payload=payload,
            )


def test_verification_report_records_signals_sla_and_does_not_publish(
    school,
    school_admin_user,
    principal_user,
):
    _authority()
    submission = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(claimed_scope={"county": "Nairobi", "grade_level": "10"}),
    )
    before = timezone.now()
    report = create_curriculum_verification_report(
        actor=school_admin_user,
        tenant=school,
        evidence_submission=submission,
        official_source_match_status=(
            CurriculumVerificationReport.OfficialSourceMatch.MATCHED
        ),
        stamp_signal=True,
        signature_signal=True,
        template_signal=True,
    )

    assert report.reference_number_detected
    assert report.publication_number_detected
    assert report.stamp_signal
    assert report.signature_signal
    assert report.confidence_score == 100
    assert report.confidence_level == "needs_governance_review"
    assert report.review_status == CurriculumVerificationReport.Status.COMPLETE
    assert report.sla_due_at >= before + timedelta(hours=23, minutes=59)
    assert report.scope_guess["county"] == "Nairobi"
    assert list(get_curriculum_verification_reports(tenant=school)) == [report]
    assert CurriculumPublication.objects.count() == 0
    assert SchoolCurriculumAdoption.objects.count() == 0


def test_governance_decision_requires_admin_and_does_not_globally_adopt(
    curriculum_version,
    principal_user,
    school,
    school_admin_role,
    school_admin_user,
):
    _authority()
    submission = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(),
    )
    report = create_curriculum_verification_report(
        actor=school_admin_user,
        tenant=school,
        evidence_submission=submission,
        official_source_match_status=(
            CurriculumVerificationReport.OfficialSourceMatch.MATCHED
        ),
        stamp_signal=True,
        signature_signal=True,
        template_signal=True,
    )

    assert can_record_curriculum_governance_decision(
        PolicyContext(
            tenant=school,
            actor=school_admin_user,
            action="curriculum.cct.record_governance_decision",
            role=school_admin_role,
        )
    )

    with pytest.raises(ValidationError):
        record_governance_decision(
            actor=principal_user,
            tenant=school,
            verification_report=report,
            decision=CurriculumGovernanceDecision.Decision.APPROVED_FOR_PUBLICATION,
            reason="Principal tries to approve curriculum truth.",
        )
    with pytest.raises(ValidationError):
        create_curriculum_publication(
            curriculum_version=curriculum_version,
            approved_by=principal_user,
            effective_from=date(2026, 1, 1),
            publication_notes="Principal attempts direct curriculum publication.",
            workflow_approved=True,
        )

    decision = record_governance_decision(
        actor=school_admin_user,
        tenant=school,
        verification_report=report,
        decision=CurriculumGovernanceDecision.Decision.APPROVED_FOR_PUBLICATION,
        reason="Governance approval recorded; publication remains separate.",
    )

    assert decision.reviewed_by == school_admin_user
    assert decision.reviewed_at is not None
    assert list(get_curriculum_governance_decisions(tenant=school)) == [decision]
    assert CurriculumPublication.objects.count() == 0
    assert SchoolCurriculumAdoption.objects.count() == 0


def test_scope_app_impact_and_rollback_candidate_are_non_mutating(
    principal_user,
    school,
    school_admin_user,
):
    submission = submit_curriculum_evidence(
        actor=principal_user,
        tenant=school,
        payload=_payload(
            storage_reference="private://school/scope.pdf",
            claimed_scope={
                "region": "Nairobi Metropolitan",
                "senior_school_pathway": "STEM",
                "learning_area": "Computer Studies",
            },
        ),
    )
    report = create_curriculum_verification_report(
        actor=school_admin_user,
        tenant=school,
        evidence_submission=submission,
    )

    plans = plan_curriculum_app_impacts(
        actor=principal_user,
        tenant=school,
        verification_report=report,
        app_domains=["grading", "compilation", "reports_future", "nlp_future"],
    )
    rollback = create_curriculum_rollback_candidate(
        actor=principal_user,
        tenant=school,
        evidence_submission=submission,
        verification_report=report,
        reason="Withdrawal evidence requires governance review.",
    )

    assert {plan.app_domain for plan in plans} == {
        "grading",
        "compilation",
        "reports_future",
        "nlp_future",
    }
    assert all(plan.status == CurriculumAppImpactPlan.Status.PLANNED for plan in plans)
    assert "preserve old context" in plans[0].historical_protection_rule
    assert rollback.status == CurriculumRollbackCandidate.Status.QUARANTINED
    assert {
        plan.id for plan in get_curriculum_app_impact_plans(tenant=school)
    } == {plan.id for plan in plans}
    assert list(get_curriculum_rollback_candidates(tenant=school)) == [rollback]
    assert CurriculumPublication.objects.count() == 0


def test_fullproof_events_are_versioned_reference_only_and_after_commit(
    django_capture_on_commit_callbacks,
    principal_user,
    school,
    school_admin_user,
):
    _authority()
    with django_capture_on_commit_callbacks(execute=True):
        submission = submit_curriculum_evidence(
            actor=principal_user,
            tenant=school,
            payload=_payload(storage_reference="private://school/event.pdf"),
        )
        report = create_curriculum_verification_report(
            actor=school_admin_user,
            tenant=school,
            evidence_submission=submission,
            official_source_match_status=(
                CurriculumVerificationReport.OfficialSourceMatch.MATCHED
            ),
            stamp_signal=True,
            signature_signal=True,
            template_signal=True,
        )
        decision = record_governance_decision(
            actor=school_admin_user,
            tenant=school,
            verification_report=report,
            decision=CurriculumGovernanceDecision.Decision.APPROVED_FOR_PUBLICATION,
            reason="Reference-only governance decision.",
        )
        rollback = create_curriculum_rollback_candidate(
            actor=principal_user,
            tenant=school,
            evidence_submission=submission,
            reason="Reference-only rollback candidate.",
        )

    expected_events = {
        "curriculum.evidence_submitted",
        "curriculum.verification_report_created",
        "curriculum.governance_decision_recorded",
        "curriculum.rollback_candidate_created",
    }
    forbidden = {
        "raw_circular_text",
        "raw_uploaded_file_content",
        "html_body",
        "student_data",
        "learner_names",
        "grade_marks",
        "component_scores",
        "report_text",
        "nlp_output",
        "guardian_contacts",
        "teacher_private_notes",
        "full_document_body",
    }

    for event_type in expected_events:
        contract = EventTypeRegistry.objects.get(event_type=event_type)
        event = EventOutbox.objects.get(event_type=event_type)
        assert contract.event_version == 1
        assert contract.allowed_producers == ["curriculum"]
        assert event.event_version == 1
        assert not (set(event.payload) & forbidden)

    assert EventOutbox.objects.get(
        event_type="curriculum.evidence_submitted"
    ).payload["evidence_submission_id"] == str(submission.id)
    assert EventOutbox.objects.get(
        event_type="curriculum.verification_report_created"
    ).payload["verification_report_id"] == str(report.id)
    assert EventOutbox.objects.get(
        event_type="curriculum.governance_decision_recorded"
    ).payload["governance_decision_id"] == str(decision.id)
    assert EventOutbox.objects.get(
        event_type="curriculum.rollback_candidate_created"
    ).payload["rollback_candidate_id"] == str(rollback.id)


def test_fullproof_event_payload_injection_is_rejected(school):
    forbidden_payloads = [
        {"raw_circular_text": "body"},
        {"raw_uploaded_file_content": "bytes"},
        {"html_body": "<script>alert(1)</script>"},
        {"student_data": ["learner"]},
        {"grade_marks": "99"},
        {"nlp_output": "generated"},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(ValidationError):
            write_outbox_event(
                event_type="curriculum.evidence_submitted",
                event_version=1,
                source_module="curriculum",
                tenant=school,
                idempotency_key=f"fullproof-injection-{list(payload)[0]}",
                payload={
                    "tenant_id": str(school.id),
                    "evidence_submission_id": str(uuid.uuid4()),
                    "status": "quarantined",
                    "created_at": timezone.now().isoformat(),
                    **payload,
                },
            )
