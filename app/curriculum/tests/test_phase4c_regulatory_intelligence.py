import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Role, TenantUserRole
from core.policies import PolicyContext
from curriculum.algorithms.curriculum_diff_engine import diff_graph_snapshots
from curriculum.algorithms.curriculum_graph_fingerprint import (
    fingerprint_outcome,
    fingerprint_rubric_foundation,
)
from curriculum.algorithms.regulatory_notice_classifier import (
    classify_regulatory_notice as classify_notice_algorithm,
)
from curriculum.algorithms.senior_school_dependency_mapper import (
    map_junior_to_senior_signals,
)
from curriculum.algorithms.teacher_readiness_mapper import (
    map_teacher_readiness_requirement as map_teacher_requirement_algorithm,
)
from curriculum.models import (
    CurriculumDiff,
    CurriculumDiffItem,
    CurriculumImpact,
    PrincipalNotificationEvidenceCard,
    RegulatoryImpact,
    RegulatoryNotice,
    SchoolUpdateAcknowledgement,
    TeacherReadinessRequirement,
)
from curriculum.policies import (
    can_acknowledge_principal_notification,
    can_issue_principal_notification,
    can_register_regulatory_notice,
)
from curriculum.selectors import (
    get_acknowledgements_for_school,
    get_diff_items_for_review,
    get_impacts_for_junior_to_senior_transition,
    get_impacts_for_senior_school,
    get_issued_principal_notifications_for_school,
    get_pending_principal_notifications,
    get_regulatory_notices_for_review,
    get_teacher_readiness_requirements,
    get_verified_regulatory_notices,
)
from curriculum.services import (
    acknowledge_school_update,
    analyze_curriculum_impact,
    build_principal_notification_evidence_card,
    classify_regulatory_notice,
    create_curriculum_diff,
    create_curriculum_diff_items,
    create_curriculum_version,
    create_regulatory_impact,
    issue_principal_notification_evidence_card,
    map_teacher_readiness_requirement,
    register_curriculum_authority,
    register_regulatory_notice,
    register_source_document,
)
from tenant.models import School


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def _authority(code="moe"):
    if code == "kicd":
        return register_curriculum_authority(
            code="kicd",
            name="Kenya Institute of Curriculum Development",
            official_website="https://kicd.ac.ke",
            allowed_domains=["kicd.ac.ke"],
        )
    if code == "knec":
        return register_curriculum_authority(
            code="knec",
            name="Kenya National Examinations Council",
            official_website="https://knec.ac.ke",
            allowed_domains=["knec.ac.ke"],
        )
    if code == "tsc":
        return register_curriculum_authority(
            code="tsc",
            name="Teachers Service Commission",
            official_website="https://tsc.go.ke",
            allowed_domains=["tsc.go.ke"],
        )
    return register_curriculum_authority(
        code="moe",
        name="Ministry of Education",
        official_website="https://education.go.ke",
        allowed_domains=["education.go.ke"],
    )


def _source_document(authority):
    return register_source_document(
        authority=authority,
        title="Official Senior School Regulatory Reference",
        document_code=f"{authority.code.upper()}-SENIOR-2026",
        document_version_label="2026",
        source_url=f"{authority.official_website}/official-reference.pdf",
        checksum="sha256:" + "f" * 64,
    )


def test_phase4c_migration_exists_and_models_use_uuid_primary_keys(app_root):
    assert (
        app_root / "curriculum" / "migrations" / "0003_phase4c_regulatory.py"
    ).exists()

    for model in [
        CurriculumDiff,
        CurriculumDiffItem,
        CurriculumImpact,
        RegulatoryNotice,
        RegulatoryImpact,
        TeacherReadinessRequirement,
        PrincipalNotificationEvidenceCard,
        SchoolUpdateAcknowledgement,
    ]:
        assert model._meta.pk.__class__.__name__ == "UUIDField"


def test_4b_curriculum_graph_is_version_aware_and_hidden_by_default(
    curriculum_version,
    curriculum_learning_area,
    strand,
    sub_strand,
    learning_outcome,
):
    learning_outcome.is_active = False
    learning_outcome.save()

    assert curriculum_learning_area.curriculum_version == curriculum_version
    assert strand.curriculum_learning_area == curriculum_learning_area
    assert sub_strand.strand == strand
    assert learning_outcome.sub_strand == sub_strand

    from curriculum.selectors import get_outcomes_for_sub_strand

    assert list(get_outcomes_for_sub_strand(sub_strand)) == []
    assert "grading" in settings.INSTALLED_APPS


def test_diff_algorithms_are_deterministic_and_detect_assessment_changes():
    old_snapshot = [
        {
            "entity_type": "outcome",
            "identifier": "grade-10-physics-outcome-1",
            "title": "Explain motion",
            "grade": "Grade 10",
            "fingerprint": fingerprint_outcome({"title": "Explain motion"}),
        },
        {
            "entity_type": "rubric_foundation",
            "identifier": "rubric-1",
            "descriptor": "Meets expectation",
            "fingerprint": fingerprint_rubric_foundation(
                {"descriptor": "Meets expectation"}
            ),
        },
    ]
    new_snapshot = [
        {
            "entity_type": "outcome",
            "identifier": "grade-10-physics-outcome-1",
            "title": "Explain motion and force",
            "grade": "Grade 10",
            "fingerprint": fingerprint_outcome(
                {"title": "Explain motion and force"}
            ),
        },
        {
            "entity_type": "rubric_foundation",
            "identifier": "rubric-1",
            "descriptor": "Exceeds expectation",
            "fingerprint": fingerprint_rubric_foundation(
                {"descriptor": "Exceeds expectation"}
            ),
        },
        {
            "entity_type": "learning_area",
            "identifier": "grade-10-aviation",
            "name": "Aviation Technology",
        },
    ]

    first = diff_graph_snapshots(old_snapshot, new_snapshot)
    second = diff_graph_snapshots(old_snapshot, new_snapshot)

    assert first == second
    assert [item["entity_identifier"] for item in first] == [
        "grade-10-aviation",
        "grade-10-physics-outcome-1",
        "rubric-1",
    ]
    assert {item["change_type"] for item in first} >= {
        "added",
        "renamed",
        "assessment_criteria_changed",
    }


def test_curriculum_diff_models_and_impact_analysis(
    source_document,
    curriculum_version,
    grade_level,
):
    new_version = create_curriculum_version(
        source_document=source_document,
        version_label="phase4c-new-version",
        effective_from="2027-01-01",
        is_active=False,
    )
    curriculum_diff = create_curriculum_diff(
        old_curriculum_version=curriculum_version,
        new_curriculum_version=new_version,
        summary="Grade 10 Senior School curriculum comparison.",
    )
    diff_items = create_curriculum_diff_items(
        curriculum_diff=curriculum_diff,
        items=[
            {
                "change_type": CurriculumDiffItem.ChangeType.UPDATED,
                "entity_type": CurriculumDiffItem.EntityType.OUTCOME,
                "entity_identifier": "grade-10-outcome-1",
                "summary": "Grade 10 outcome updated for Senior School.",
            }
        ],
    )
    impacts = analyze_curriculum_impact(
        diff_item=diff_items[0],
        affected_stage="Senior School",
        affected_grade_level=grade_level,
    )

    assert impacts
    assert list(get_diff_items_for_review()) == diff_items
    assert any(
        impact.impact_category == CurriculumImpact.Category.SENIOR_SCHOOL_CURRICULUM
        for impact in impacts
    )

    with pytest.raises(ValidationError):
        create_curriculum_diff(
            old_curriculum_version=curriculum_version,
            new_curriculum_version=curriculum_version,
            summary="Invalid same-version comparison.",
        )

    with pytest.raises(ValidationError):
        create_curriculum_diff_items(
            curriculum_diff=curriculum_diff,
            items=[
                {
                    "change_type": CurriculumDiffItem.ChangeType.UPDATED,
                    "entity_type": CurriculumDiffItem.EntityType.OUTCOME,
                    "entity_identifier": "unsafe",
                    "summary": "Learner John Doe appears in governance notes.",
                }
            ],
        )


def test_regulatory_notice_classification_and_verification_workflow(principal_user):
    authority = _authority("kicd")
    source_document = _source_document(authority)

    assert (
        classify_notice_algorithm(
            authority_code="kicd",
            title="Senior School curriculum design update",
            summary="Grade 10 curriculum design implementation update.",
        )
        == RegulatoryNotice.NoticeType.KICD_CURRICULUM_UPDATE
    )
    assert map_junior_to_senior_signals(
        title="Grade 9 to Grade 10 Transition",
        summary="KJSEA pathway placement guidance for Senior School readiness.",
    )

    notice = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="Senior School Curriculum Design Update",
        summary="Grade 10 curriculum design implementation update.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=principal_user,
    )

    assert notice.review_status == RegulatoryNotice.ReviewStatus.VERIFIED
    assert notice.notice_type == RegulatoryNotice.NoticeType.KICD_CURRICULUM_UPDATE
    assert list(get_verified_regulatory_notices()) == [notice]

    pending = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="Implementation circular",
        summary="Senior School implementation guidance for principals.",
    )
    classified = classify_regulatory_notice(regulatory_notice=pending)

    assert classified.notice_type == RegulatoryNotice.NoticeType.KICD_CURRICULUM_UPDATE
    assert list(get_regulatory_notices_for_review()) == [classified]


def test_unofficial_or_pii_notice_cannot_be_verified(principal_user):
    authority = register_curriculum_authority(
        code="moe",
        name="Ministry of Education",
        official_website="https://education.go.ke",
        allowed_domains=["education.go.ke"],
        is_approved=False,
    )

    with pytest.raises(ValidationError):
        register_regulatory_notice(
            authority=authority,
            title="Fake Senior School Circular",
            summary="Senior School update.",
            review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
            reviewed_by=principal_user,
        )

    approved_authority = _authority("knec")
    with pytest.raises(ValidationError):
        register_regulatory_notice(
            authority=approved_authority,
            title="Unsafe governance note",
            summary="Learner John Doe appears in the notice.",
        )


def test_regulatory_impact_and_teacher_readiness_mapping(
    principal_user,
    learning_area,
    grade_level,
):
    authority = _authority("tsc")
    source_document = _source_document(authority)
    notice = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="TSC Grade 10 Teacher Training Notice",
        summary="Senior School assessment training required for Grade 10 teachers.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=principal_user,
    )
    impact = create_regulatory_impact(
        regulatory_notice=notice,
        affected_grade_level=grade_level,
        affected_learning_area=learning_area,
        impact_category=RegulatoryImpact.Category.TEACHER_TRAINING,
        impact_severity=RegulatoryImpact.Severity.HIGH,
        action_required="Review teacher training requirements.",
    )
    requirement = map_teacher_readiness_requirement(
        regulatory_notice=notice,
        affected_learning_area=learning_area,
        affected_grade_level=grade_level,
        summary="Assessment training required for Senior School teachers.",
    )

    assert impact.impact_category == RegulatoryImpact.Category.TEACHER_TRAINING
    assert (
        map_teacher_requirement_algorithm(
            title=notice.title,
            summary=notice.summary,
        )
        == TeacherReadinessRequirement.RequirementType.ASSESSMENT_TRAINING_REQUIRED
    )
    assert (
        requirement.requirement_type
        == TeacherReadinessRequirement.RequirementType.ASSESSMENT_TRAINING_REQUIRED
    )
    assert list(get_teacher_readiness_requirements()) == [requirement]


def test_principal_notification_evidence_acknowledgement_and_no_activation(
    principal_user,
    school,
):
    authority = _authority("moe")
    source_document = _source_document(authority)
    notice = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="Senior School Regulatory Update",
        summary="Grade 10 Senior School pathway readiness update.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=principal_user,
    )
    card = build_principal_notification_evidence_card(
        tenant=school,
        regulatory_notice=notice,
        impact_summary="Senior School Grade 10 pathway readiness update detected.",
        required_action="Principal review is required before school activation.",
    )
    issued = issue_principal_notification_evidence_card(evidence_card=card)
    acknowledgement = acknowledge_school_update(
        evidence_card=issued,
        tenant=school,
        acknowledged_by=principal_user,
        acknowledgement_status=SchoolUpdateAcknowledgement.Status.ACKNOWLEDGED,
        principal_notes="School leadership will review internally.",
    )

    issued.refresh_from_db()
    assert "Darasa has not automatically changed" in issued.summary
    assert issued.status == PrincipalNotificationEvidenceCard.Status.ACKNOWLEDGED
    assert acknowledgement.notification_evidence_card == issued
    assert list(get_issued_principal_notifications_for_school(tenant=school)) == [
        issued
    ]
    assert list(get_acknowledgements_for_school(tenant=school)) == [acknowledgement]

    with pytest.raises(ValidationError):
        acknowledge_school_update(
            evidence_card=issued,
            tenant=School.objects.create(
                name="Other School",
                schema_name="other_phase4c",
                subdomain="other-phase4c",
                school_code="OTH4C",
            ),
            acknowledged_by=principal_user,
            acknowledgement_status=SchoolUpdateAcknowledgement.Status.ACKNOWLEDGED,
        )


def test_notification_security_abuse_cases(principal_user, teacher_user, school):
    authority = _authority("knec")
    source_document = _source_document(authority)
    notice = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="KNEC Assessment Guidance",
        summary="Senior School assessment guidance update.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=principal_user,
        status=PrincipalNotificationEvidenceCard.Status.ISSUED,
    )

    with pytest.raises(ValidationError):
        build_principal_notification_evidence_card(
            tenant=school,
            regulatory_notice=notice,
            impact_summary="Learner John Doe should receive this alert.",
            required_action="Principal review is required.",
        )

    card = build_principal_notification_evidence_card(
        tenant=school,
        regulatory_notice=notice,
        impact_summary="Senior School assessment guidance update detected.",
        required_action="Principal review is required.",
    )
    assert card.status == PrincipalNotificationEvidenceCard.Status.READY_FOR_REVIEW

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            build_principal_notification_evidence_card(
                tenant=school,
                regulatory_notice=notice,
                impact_summary="Senior School assessment guidance update detected.",
                required_action="Principal review is required.",
            )

    teacher_role = Role.objects.get(code=Role.RoleCode.SUBJECT_TEACHER)
    teacher_context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="curriculum.notification.issue",
        role=teacher_role,
    )
    assert not can_issue_principal_notification(teacher_context)


def test_policies_fail_closed_and_inactive_role_binding_denies(
    principal_user,
    principal_role,
    school,
):
    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.regulatory.register",
        role=principal_role,
    )
    assert can_register_regulatory_notice(context)

    TenantUserRole.objects.filter(
        tenant=school,
        user=principal_user,
        role=principal_role,
    ).update(is_active=False)

    assert not can_register_regulatory_notice(context)
    assert not can_issue_principal_notification(
        PolicyContext(
            tenant=school,
            actor=principal_user,
            action="curriculum.notification.issue",
            role=principal_role,
        )
    )


def test_acknowledgement_policy_is_tenant_scoped(
    principal_user,
    principal_role,
    school,
):
    authority = _authority("moe")
    source_document = _source_document(authority)
    notice = register_regulatory_notice(
        authority=authority,
        source_document=source_document,
        title="Senior School Implementation Circular",
        summary="Senior School implementation guidance.",
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        reviewed_by=principal_user,
    )
    card = build_principal_notification_evidence_card(
        tenant=school,
        regulatory_notice=notice,
        impact_summary="Senior School implementation guidance detected.",
        required_action="Principal review is required.",
    )
    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.notification.acknowledge",
        role=principal_role,
    )

    assert can_acknowledge_principal_notification(context, evidence_card=card)

    other_school = School.objects.create(
        name="Policy Other School",
        schema_name="policy_other_phase4c",
        subdomain="policy-other-phase4c",
        school_code="POTH4C",
    )
    other_context = PolicyContext(
        tenant=other_school,
        actor=principal_user,
        action="curriculum.notification.acknowledge",
        role=principal_role,
    )
    assert not can_acknowledge_principal_notification(
        other_context,
        evidence_card=card,
    )


def test_selectors_are_bounded_for_phase4c(
    django_assert_max_num_queries,
    source_document,
    curriculum_version,
    school,
):
    new_version = create_curriculum_version(
        source_document=source_document,
        version_label="phase4c-selector-version",
        effective_from="2027-01-01",
        is_active=False,
    )
    curriculum_diff = create_curriculum_diff(
        old_curriculum_version=curriculum_version,
        new_curriculum_version=new_version,
        summary="Grade 10 Senior School selector comparison.",
    )
    diff_item = create_curriculum_diff_items(
        curriculum_diff=curriculum_diff,
        items=[
            {
                "change_type": CurriculumDiffItem.ChangeType.UPDATED,
                "entity_type": CurriculumDiffItem.EntityType.OUTCOME,
                "entity_identifier": "grade-10-selector-outcome",
                "summary": "Grade 10 Senior School selector update.",
            }
        ],
    )[0]
    analyze_curriculum_impact(
        diff_item=diff_item,
        affected_stage="Senior School",
    )

    with django_assert_max_num_queries(1):
        assert list(get_impacts_for_senior_school())
    with django_assert_max_num_queries(1):
        assert list(get_diff_items_for_review()) == [diff_item]
    with django_assert_max_num_queries(1):
        assert list(get_pending_principal_notifications(tenant=school)) == []
    with django_assert_max_num_queries(1):
        assert list(get_impacts_for_junior_to_senior_transition()) == []


def test_phase_boundary_no_live_web_ai_parser_or_future_apps(app_root, settings):
    forbidden_files = [
        app_root / "curriculum" / "crawler.py",
        app_root / "curriculum" / "ai_parser.py",
    ]

    assert all(not path.exists() for path in forbidden_files)
    assert "grading" in settings.INSTALLED_APPS
    assert "reports" not in settings.INSTALLED_APPS
    assert "schemes" not in settings.INSTALLED_APPS
