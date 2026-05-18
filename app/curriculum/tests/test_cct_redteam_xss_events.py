from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from curriculum.algorithms.pii_guard import validate_governance_text
from curriculum.models import (
    CurriculumNoticeBatchRun,
    CurriculumVersion,
    PrincipalNotificationEvidenceCard,
    RegulatoryNotice,
)
from curriculum.services import (
    build_principal_notification_evidence_card,
    create_notice_batch_run,
    mark_curriculum_version_withdrawn,
    register_regulatory_notice,
)
from events.models import EventOutbox
from events.services import write_outbox_event


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


XSS_PAYLOADS = [
    '<script>alert("cct")</script>',
    '<img src=x onerror=alert("cct")>',
    "<svg onload=alert('cct')>",
    '<a href="javascript:alert(1)">click</a>',
    '"><script>alert(1)</script>',
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_governance_text_rejects_executable_html_payloads(payload):
    with pytest.raises(ValidationError):
        validate_governance_text(payload)


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_source_and_version_metadata_rejects_executable_html(
    payload,
    source_document,
):
    source_document.title = payload
    with pytest.raises(ValidationError):
        source_document.full_clean()

    version = CurriculumVersion(
        source_document=source_document,
        version_label=payload,
        effective_from="2026-01-01",
    )
    with pytest.raises(ValidationError):
        version.full_clean()


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_notices_and_withdrawals_reject_executable_html(
    payload,
    curriculum_version,
    school_admin_user,
    school,
):
    with pytest.raises(ValidationError):
        mark_curriculum_version_withdrawn(
            curriculum_version=curriculum_version,
            withdrawn_by=school_admin_user,
            reason=payload,
        )

    with pytest.raises(ValidationError):
        create_notice_batch_run(
            notice_type=CurriculumNoticeBatchRun.NoticeType.PRINCIPAL_EVIDENCE,
            total_count=1,
            batch_size=1,
            created_by=school_admin_user,
            tenant=school,
            notes=payload,
        )


def test_principal_notice_rejects_html_and_does_not_emit_raw_text(
    school_admin_user,
    school,
    source_document,
):
    notice = register_regulatory_notice(
        authority=_authority("kicd"),
        source_document=source_document,
        title="Senior School Update",
        summary="Senior School curriculum implementation guidance.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=school_admin_user,
    )
    with pytest.raises(ValidationError):
        build_principal_notification_evidence_card(
            tenant=school,
            regulatory_notice=notice,
            notification_type=(
                PrincipalNotificationEvidenceCard.NotificationType.CURRICULUM_UPDATE
            ),
            impact_summary='<script>alert("cct")</script>',
            required_action="Principal review is required.",
        )

    assert EventOutbox.objects.count() == 0


def test_cct_event_payload_injection_fields_are_rejected():
    forbidden_payloads = [
        {"raw_circular_text": "full body"},
        {"raw_uploaded_file_content": "bytes"},
        {"student_data": ["learner one"]},
        {"learner_names": ["A Learner"]},
        {"grade_marks": "99"},
        {"component_scores": {"practical": 10}},
        {"report_text": "report"},
        {"nlp_output": "generated"},
        {"guardian_phone": "+254700000000"},
        {"teacher_private_notes": "internal"},
        {"html_body": "<script>alert(1)</script>"},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(ValidationError):
            write_outbox_event(
                event_type="curriculum.notice_batch_created",
                event_version=1,
                source_module="curriculum",
                tenant=None,
                idempotency_key=f"redteam-event-{list(payload)[0]}",
                payload={
                    "notice_batch_id": "batch-1",
                    "notice_type": "principal_evidence",
                    "total_count": 1,
                    **payload,
                },
            )


def _authority(code):
    from curriculum.services import register_curriculum_authority

    return register_curriculum_authority(
        code=code,
        name="Kenya Institute of Curriculum Development",
        official_website="https://kicd.ac.ke",
        allowed_domains=["kicd.ac.ke"],
    )
