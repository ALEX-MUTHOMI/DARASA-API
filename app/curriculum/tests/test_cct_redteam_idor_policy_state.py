from __future__ import annotations

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from core.models import CustomUser, Role, TenantUserRole
from core.policies import PolicyContext
from curriculum.models import (
    CurriculumNoticeBatchRun,
    PrincipalNotificationEvidenceCard,
    SchoolCurriculumAdoption,
)
from curriculum.policies import (
    can_acknowledge_principal_notification,
    can_plan_curriculum_rollback,
    can_schedule_school_adoption,
)
from curriculum.selectors import (
    get_curriculum_notice_batch_runs,
    get_curriculum_rollback_plans,
    get_school_adoption_status,
)
from curriculum.services import (
    approve_change_set,
    build_principal_notification_evidence_card,
    create_curriculum_change_set,
    create_curriculum_publication,
    create_notice_batch_run,
    mark_curriculum_version_withdrawn,
    plan_curriculum_rollback,
    publish_curriculum_version,
    register_regulatory_notice,
    schedule_school_curriculum_adoption,
)
from tenant.models import School


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def _other_school() -> School:
    return School.objects.create(
        name="Red Team Other School",
        schema_name="redteam_other",
        subdomain="redteam-other",
        school_code="RTO001",
    )


def _publish(curriculum_version, principal_user):
    return create_curriculum_publication(
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        publication_notes="Reviewed publication for red-team tests.",
        approved_by=principal_user,
        workflow_approved=True,
    )


def _principal_for(school: School, principal_role: Role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"principal-{school.schema_name}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=principal_role)
    return user


def test_tenant_scoped_cct_selectors_do_not_leak_guessed_ids(
    curriculum_version,
    principal_role,
    principal_user,
    school,
):
    other = _other_school()
    other_principal = _principal_for(other, principal_role)
    _publish(curriculum_version, principal_user)
    other_adoption = schedule_school_curriculum_adoption(
        tenant=other,
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        scheduled_by=other_principal,
    )
    rollback = plan_curriculum_rollback(
        tenant=other,
        withdrawn_version=curriculum_version,
        planned_by=other_principal,
        reason="Tenant-specific rollback plan.",
    )
    batch = create_notice_batch_run(
        tenant=other,
        notice_type=CurriculumNoticeBatchRun.NoticeType.PRINCIPAL_EVIDENCE,
        total_count=1,
        batch_size=1,
        created_by=other_principal,
        notes="Tenant-scoped notice batch.",
    )

    assert other_adoption not in list(get_school_adoption_status(tenant=school))
    assert rollback not in list(get_curriculum_rollback_plans(tenant=school))
    assert batch not in list(get_curriculum_notice_batch_runs(tenant=school))


def test_cross_tenant_principal_notice_acknowledgement_is_denied(
    principal_role,
    principal_user,
    school,
    source_document,
):
    other = _other_school()
    other_principal = _principal_for(other, principal_role)
    notice = register_regulatory_notice(
        authority=_authority("kicd"),
        source_document=source_document,
        title="Senior School Implementation Update",
        summary="Senior School implementation update.",
        review_status="verified",
        reviewed_by=principal_user,
    )
    card = build_principal_notification_evidence_card(
        tenant=other,
        regulatory_notice=notice,
        notification_type=(
            PrincipalNotificationEvidenceCard.NotificationType.REGULATORY_NOTICE
        ),
        impact_summary="Senior School update requires principal review.",
        required_action="Review evidence before school activation.",
    )
    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.notification.acknowledge",
        role=principal_role,
    )

    assert not can_acknowledge_principal_notification(context, evidence_card=card)
    assert other_principal != principal_user


def test_low_privilege_or_inactive_users_cannot_schedule_adoption_or_rollback(
    curriculum_version,
    principal_role,
    principal_user,
    school,
    teacher_role,
    teacher_user,
):
    _publish(curriculum_version, principal_user)
    teacher_context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="curriculum.cct.schedule_adoption",
        role=teacher_role,
    )
    assert not can_schedule_school_adoption(teacher_context)
    with pytest.raises(ValidationError):
        schedule_school_curriculum_adoption(
            tenant=school,
            curriculum_version=curriculum_version,
            effective_from=date(2026, 1, 1),
            scheduled_by=teacher_user,
        )

    rollback_context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="curriculum.cct.plan_rollback",
        role=teacher_role,
    )
    assert not can_plan_curriculum_rollback(rollback_context)
    with pytest.raises(ValidationError):
        plan_curriculum_rollback(
            tenant=school,
            withdrawn_version=curriculum_version,
            planned_by=teacher_user,
            reason="Teacher tries rollback.",
        )

    TenantUserRole.objects.filter(
        tenant=school,
        user=principal_user,
        role=principal_role,
    ).update(is_active=False)
    principal_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.schedule_adoption",
        role=principal_role,
    )
    assert not can_schedule_school_adoption(principal_context)
    with pytest.raises(ValidationError):
        schedule_school_curriculum_adoption(
            tenant=school,
            curriculum_version=curriculum_version,
            effective_from=date(2026, 1, 1),
            scheduled_by=principal_user,
        )


def test_mass_assignment_and_state_machine_bypass_attempts_fail(
    curriculum_version,
    principal_user,
    school,
    source_document,
):
    _publish(curriculum_version, principal_user)
    adoption = schedule_school_curriculum_adoption(
        tenant=school,
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        scheduled_by=principal_user,
    )
    assert adoption.status == SchoolCurriculumAdoption.Status.SCHEDULED

    change_set = create_curriculum_change_set(
        source_document=source_document,
        proposed_curriculum_version=curriculum_version,
        change_type="new_version",
        summary="Detected source change.",
        status="published",
    )
    assert change_set.status == "detected"

    with pytest.raises(ValidationError):
        publish_curriculum_version(
            change_set=change_set,
            curriculum_version=curriculum_version,
            approved_by=principal_user,
            effective_from=date(2026, 1, 1),
        )


def test_low_privilege_and_staff_without_curriculum_authority_cannot_publish(
    curriculum_version,
    source_document,
    teacher_user,
):
    staff_user = CustomUser.objects.create_user(
        email="staff-without-cct-authority@example.test",
        password="test-only-secret",
    )
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])
    authority = _authority("kicd")

    for actor in [teacher_user, staff_user]:
        change_set = create_curriculum_change_set(
            source_document=source_document,
            proposed_curriculum_version=curriculum_version,
            change_type="new_version",
            summary="Detected source change for authority checks.",
        )
        with pytest.raises(ValidationError):
            approve_change_set(change_set=change_set, reviewed_by=actor)
        with pytest.raises(ValidationError):
            create_curriculum_publication(
                curriculum_version=curriculum_version,
                effective_from=date(2026, 1, 1),
                publication_notes="Unauthorized publication attempt.",
                approved_by=actor,
                workflow_approved=True,
            )
        with pytest.raises(ValidationError):
            mark_curriculum_version_withdrawn(
                curriculum_version=curriculum_version,
                withdrawn_by=actor,
                reason="Unauthorized withdrawal attempt.",
            )
        with pytest.raises(ValidationError):
            register_regulatory_notice(
                authority=authority,
                source_document=source_document,
                title="Unauthorized verified notice",
                summary="Unauthorized actor attempts verified notice.",
                review_status="verified",
                reviewed_by=actor,
            )


def _authority(code):
    from curriculum.services import register_curriculum_authority

    return register_curriculum_authority(
        code=code,
        name="Kenya Institute of Curriculum Development",
        official_website="https://kicd.ac.ke",
        allowed_domains=["kicd.ac.ke"],
    )
