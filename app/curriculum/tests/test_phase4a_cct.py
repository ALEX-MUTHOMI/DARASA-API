import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import TenantUserRole
from core.policies import PolicyContext
from curriculum.algorithms.artifact_validator import validate_artifact_metadata
from curriculum.algorithms.authority_normalizer import normalize_authority_code
from curriculum.algorithms.change_detector import detect_source_change
from curriculum.algorithms.checksum import compute_sha256
from curriculum.algorithms.pii_guard import validate_governance_text
from curriculum.algorithms.publication_state_machine import validate_transition
from curriculum.algorithms.source_fingerprint import build_source_fingerprint
from curriculum.algorithms.source_url_validator import validate_source_url
from curriculum.algorithms.version_resolver import resolve_publication_for_date
from curriculum.models import (
    CurriculumAuthority,
    CurriculumChangeSet,
    CurriculumPublication,
    SourceArtifact,
)
from curriculum.policies import (
    can_approve_change_set,
    can_publish_curriculum_version,
    can_register_curriculum_source,
    can_view_source_registry,
)
from curriculum.selectors import (
    get_active_authorities,
    get_active_curriculum_publication,
    get_approved_change_sets,
    get_curriculum_publication_history,
    get_pending_change_sets,
    get_quarantined_artifacts,
    get_rejected_change_sets,
    get_source_document_history,
    resolve_curriculum_version_for_date,
)
from curriculum.services import (
    approve_change_set,
    create_curriculum_change_set,
    create_curriculum_publication,
    create_curriculum_version,
    publish_curriculum_version,
    register_curriculum_authority,
    register_source_artifact,
    register_source_document,
    reject_change_set,
    supersede_curriculum_publication,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def test_cct_migration_exists_and_models_use_uuid_primary_keys(app_root):
    assert (app_root / "curriculum" / "migrations" / "0002_cct.py").exists()

    for model in [
        CurriculumAuthority,
        SourceArtifact,
        CurriculumChangeSet,
        CurriculumPublication,
    ]:
        assert model._meta.pk.__class__.__name__ == "UUIDField"


def test_authority_normalization_and_uniqueness():
    authority = register_curriculum_authority(
        code=" KICD ",
        name="Kenya Institute of Curriculum Development",
        official_website="https://kicd.ac.ke",
        allowed_domains=["kicd.ac.ke"],
    )

    assert authority.code == "kicd"
    assert (
        normalize_authority_code(" Ministry Of Education ")
        == "ministry-of-education"
    )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            register_curriculum_authority(
                code="kicd",
                name="Duplicate KICD",
                official_website="https://kicd.ac.ke",
                allowed_domains=["kicd.ac.ke"],
            )


def test_source_url_validator_accepts_only_approved_official_hosts():
    allowed = ["kicd.ac.ke", "www.kicd.ac.ke"]

    assert (
        validate_source_url(
            "https://kicd.ac.ke/cbc-materials/curriculum-designs/",
            allowed_domains=allowed,
        )
        == "https://kicd.ac.ke/cbc-materials/curriculum-designs/"
    )

    rejected_urls = [
        "https://kicd.ac.ke.evil.com/fake.pdf",
        "https://kicd.ac.ke@evil.com/file.pdf",
        "http://kicd.ac.ke/insecure.pdf",
        "https://kicd.ac.ke:8443/alternate-port.pdf",
        "https://kicd.ac.ke:invalid/file.pdf",
        "http://127.0.0.1:8000/admin",
        "http://10.0.0.5/internal",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "ftp://kicd.ac.ke/file.pdf",
        "https://localhost/admin",
    ]

    for url in rejected_urls:
        with pytest.raises(ValidationError):
            validate_source_url(url, allowed_domains=allowed)


def test_authority_registry_rejects_unknown_or_poisoned_domains():
    with pytest.raises(ValidationError):
        register_curriculum_authority(
            code="evil-official",
            name="Fake Official Curriculum Authority",
            official_website="https://evil.example",
            allowed_domains=["evil.example"],
        )

    with pytest.raises(ValidationError):
        register_curriculum_authority(
            code="kicd",
            name="Poisoned KICD",
            official_website="https://kicd.ac.ke.evil.com",
            allowed_domains=["kicd.ac.ke.evil.com"],
        )


def test_checksum_fingerprint_and_change_detection_are_deterministic():
    old_checksum = compute_sha256(b"official-source-v1")
    new_checksum = compute_sha256(b"official-source-v2")

    assert old_checksum == compute_sha256(b"official-source-v1")
    assert old_checksum != new_checksum

    old_fingerprint = build_source_fingerprint(
        authority_code="kicd",
        source_reference="KICD-G4",
        version_label="2026",
        checksum=old_checksum,
    )
    new_fingerprint = build_source_fingerprint(
        authority_code="kicd",
        source_reference="KICD-G4",
        version_label="2026",
        checksum=new_checksum,
    )

    assert old_fingerprint != new_fingerprint
    assert detect_source_change(None, old_fingerprint) == "new_version_candidate"
    assert detect_source_change(old_fingerprint, old_fingerprint) == "no_change"
    assert detect_source_change(old_fingerprint, new_fingerprint) == "changed_source"


def test_artifact_validator_rejects_resource_exhaustion_and_unsupported_types():
    validate_artifact_metadata(
        file_size=1024,
        content_type="application/pdf",
        checksum="sha256:" + "a" * 64,
    )

    with pytest.raises(ValidationError):
        validate_artifact_metadata(
            file_size=50 * 1024 * 1024 + 1,
            content_type="application/pdf",
            checksum="sha256:" + "a" * 64,
        )
    with pytest.raises(ValidationError):
        validate_artifact_metadata(
            file_size=1024,
            content_type="application/x-msdownload",
            checksum="sha256:" + "a" * 64,
        )
    with pytest.raises(ValidationError):
        validate_artifact_metadata(
            file_size=1024,
            content_type="application/pdf",
            checksum="",
        )


def test_artifact_registration_rejects_path_traversal_and_size_mismatch(
    source_document,
):
    with pytest.raises(ValidationError):
        register_source_artifact(
            source_document=source_document,
            file_name="../poison.pdf",
            content_type="application/pdf",
            file_size=6,
            content=b"source",
            capture_method=SourceArtifact.CaptureMethod.MANUAL_UPLOAD,
        )

    with pytest.raises(ValidationError):
        register_source_artifact(
            source_document=source_document,
            file_name="source.pdf",
            content_type="application/pdf",
            file_size=999,
            content=b"source",
            capture_method=SourceArtifact.CaptureMethod.MANUAL_UPLOAD,
        )


def test_pii_guard_rejects_obvious_learner_specific_governance_text():
    validate_governance_text("Source changed for Grade 4 Integrated Science.")

    for text in [
        "Update for learner admission number ADM-2026-001.",
        "Pupil John Doe needs this curriculum change.",
        "Guardian phone details were included.",
    ]:
        with pytest.raises(ValidationError):
            validate_governance_text(text)


def test_publication_state_machine_blocks_bypass_transitions():
    validate_transition(
        CurriculumChangeSet.Status.DETECTED,
        CurriculumChangeSet.Status.QUARANTINED,
    )
    validate_transition(
        CurriculumChangeSet.Status.APPROVED,
        CurriculumChangeSet.Status.PUBLISHED,
    )

    for old_status, new_status in [
        (CurriculumChangeSet.Status.DETECTED, CurriculumChangeSet.Status.PUBLISHED),
        (CurriculumChangeSet.Status.REJECTED, CurriculumChangeSet.Status.PUBLISHED),
        (CurriculumChangeSet.Status.SUPERSEDED, CurriculumChangeSet.Status.APPROVED),
    ]:
        with pytest.raises(ValidationError):
            validate_transition(old_status, new_status)


def test_authority_source_artifact_and_change_set_workflow(
    curriculum_version,
    principal_user,
):
    authority = register_curriculum_authority(
        code="kicd",
        name="Kenya Institute of Curriculum Development",
        official_website="https://kicd.ac.ke",
        allowed_domains=["kicd.ac.ke"],
    )
    source_document = register_source_document(
        authority=authority,
        title="Official Grade 4 Curriculum Design Reference",
        document_code="KICD-G4-CCT",
        document_version_label="2026",
        source_url="https://kicd.ac.ke/cbc-materials/curriculum-designs/",
        checksum="sha256:" + "b" * 64,
    )
    artifact_content = b"official curriculum reference"
    artifact = register_source_artifact(
        source_document=source_document,
        file_name="grade-4.pdf",
        content_type="application/pdf",
        file_size=len(artifact_content),
        content=artifact_content,
        capture_method=SourceArtifact.CaptureMethod.MANUAL_UPLOAD,
    )
    change_set = create_curriculum_change_set(
        source_document=source_document,
        old_curriculum_version=None,
        proposed_curriculum_version=curriculum_version,
        change_type=CurriculumChangeSet.ChangeType.NEW_VERSION,
        summary="Official source update proposed for review.",
    )

    assert artifact.quarantine_status == SourceArtifact.QuarantineStatus.QUARANTINED
    assert artifact.scan_status == SourceArtifact.ScanStatus.PENDING
    assert change_set.status == CurriculumChangeSet.Status.DETECTED

    with pytest.raises(ValidationError):
        publish_curriculum_version(
            change_set=change_set,
            curriculum_version=curriculum_version,
            approved_by=principal_user,
            effective_from="2026-01-01",
        )

    approved = approve_change_set(change_set=change_set, reviewed_by=principal_user)
    assert list(get_approved_change_sets()) == [approved]
    publication = publish_curriculum_version(
        change_set=approved,
        curriculum_version=curriculum_version,
        approved_by=principal_user,
        effective_from="2026-01-01",
        publication_notes="Reviewed official source update.",
    )

    approved.refresh_from_db()
    assert approved.status == CurriculumChangeSet.Status.PUBLISHED
    assert publication.is_active


def test_publication_rejects_workflow_bypass_and_version_swap(
    curriculum_version,
    principal_user,
    source_document,
):
    alternate_version = create_curriculum_version(
        source_document=source_document,
        version_label="alternate-version",
        effective_from="2028-01-01",
        is_active=False,
    )
    change_set = create_curriculum_change_set(
        source_document=source_document,
        proposed_curriculum_version=curriculum_version,
        change_type=CurriculumChangeSet.ChangeType.NEW_VERSION,
        summary="Reviewed official source update.",
    )
    approved = approve_change_set(change_set=change_set, reviewed_by=principal_user)

    with pytest.raises(ValidationError):
        create_curriculum_publication(
            curriculum_version=curriculum_version,
            approved_by=principal_user,
            effective_from="2026-01-01",
            publication_notes="Direct active publication bypass.",
        )

    with pytest.raises(ValidationError):
        publish_curriculum_version(
            change_set=approved,
            curriculum_version=alternate_version,
            approved_by=principal_user,
            effective_from="2026-01-01",
        )


def test_review_actions_require_active_reviewer(source_document, principal_user):
    change_set = create_curriculum_change_set(
        source_document=source_document,
        change_type=CurriculumChangeSet.ChangeType.SOURCE_CHANGED,
        summary="Official source change proposed.",
    )
    principal_user.is_active = False
    principal_user.save(update_fields=["is_active"])

    with pytest.raises(ValidationError):
        approve_change_set(change_set=change_set, reviewed_by=principal_user)


def test_inactive_authority_cannot_register_source():
    authority = register_curriculum_authority(
        code="moe",
        name="Ministry of Education",
        official_website="https://education.go.ke",
        allowed_domains=["education.go.ke"],
        is_active=False,
    )

    with pytest.raises(ValidationError):
        register_source_document(
            authority=authority,
            title="Official Source",
            document_code="MOE-1",
            document_version_label="2026",
            source_url="https://education.go.ke/source.pdf",
            checksum="sha256:" + "c" * 64,
        )


def test_rejected_change_remains_auditable(source_document, principal_user):
    change_set = create_curriculum_change_set(
        source_document=source_document,
        change_type=CurriculumChangeSet.ChangeType.SOURCE_CHANGED,
        summary="Official source changed but was rejected after review.",
    )

    rejected = reject_change_set(change_set=change_set, reviewed_by=principal_user)
    assert rejected.status == CurriculumChangeSet.Status.REJECTED
    assert list(get_rejected_change_sets()) == [rejected]

    with pytest.raises(ValidationError):
        publish_curriculum_version(
            change_set=rejected,
            curriculum_version=rejected.proposed_curriculum_version,
            approved_by=principal_user,
            effective_from="2026-01-01",
        )


def test_publication_preserves_old_versions(
    curriculum_version,
    principal_user,
    source_document,
):
    change_set = create_curriculum_change_set(
        source_document=source_document,
        proposed_curriculum_version=curriculum_version,
        change_type=CurriculumChangeSet.ChangeType.NEW_VERSION,
        summary="Initial official publication reviewed.",
    )
    approved = approve_change_set(change_set=change_set, reviewed_by=principal_user)
    old_publication = publish_curriculum_version(
        change_set=approved,
        curriculum_version=curriculum_version,
        approved_by=principal_user,
        effective_from="2026-01-01",
        publication_notes="Initial reviewed publication.",
    )
    new_publication = create_curriculum_publication(
        curriculum_version=curriculum_version,
        approved_by=principal_user,
        effective_from="2027-01-01",
        publication_notes="Replacement reviewed publication.",
        is_active=False,
    )

    supersede_curriculum_publication(
        publication=old_publication,
        superseded_by=new_publication,
    )
    old_publication.refresh_from_db()

    assert not old_publication.is_active
    assert old_publication.superseded_by == new_publication
    assert list(get_curriculum_publication_history(curriculum_version))[0].id in {
        old_publication.id,
        new_publication.id,
    }


def test_selectors_are_ordered_hidden_and_bounded(
    curriculum_version,
    django_assert_max_num_queries,
    source_document,
):
    authority = register_curriculum_authority(
        code="knec",
        name="Kenya National Examinations Council",
        official_website="https://knec.ac.ke",
        allowed_domains=["knec.ac.ke"],
    )
    artifact_content = b"source"
    register_source_artifact(
        source_document=source_document,
        file_name="source.pdf",
        content_type="application/pdf",
        file_size=len(artifact_content),
        content=artifact_content,
        capture_method=SourceArtifact.CaptureMethod.MANUAL_UPLOAD,
    )
    create_curriculum_change_set(
        source_document=source_document,
        change_type=CurriculumChangeSet.ChangeType.SOURCE_CHANGED,
        summary="Official source update pending review.",
    )
    publication = create_curriculum_publication(
        curriculum_version=curriculum_version,
        effective_from=timezone.now().date(),
        publication_notes="Reviewed publication.",
        is_active=False,
    )

    with django_assert_max_num_queries(1):
        assert list(get_active_authorities()) == [authority]
    with django_assert_max_num_queries(1):
        artifact = list(get_quarantined_artifacts()).pop()
        assert artifact.source_document == source_document
    with django_assert_max_num_queries(1):
        assert len(list(get_pending_change_sets())) == 1
    with django_assert_max_num_queries(1):
        assert get_active_curriculum_publication() is None

    assert list(get_source_document_history(authority=authority)) == []
    assert resolve_curriculum_version_for_date(on_date=timezone.now().date()) is None
    assert resolve_publication_for_date(
        [publication],
        on_date=timezone.now().date(),
    ) is None


def test_curriculum_governance_policies_fail_closed(
    principal_role,
    principal_user,
    school,
):
    allowed_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.register_source",
        role=principal_role,
    )
    assert can_view_source_registry(allowed_context)
    assert can_register_curriculum_source(allowed_context)

    denied_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.publish_version",
        role=None,
    )
    assert not can_publish_curriculum_version(denied_context)
    assert not can_approve_change_set(denied_context)

    TenantUserRole.objects.filter(
        tenant=school,
        user=principal_user,
        role=principal_role,
    ).update(is_active=False)

    assert not can_register_curriculum_source(allowed_context)


def test_status_mass_assignment_like_override_is_ignored(source_document):
    change_set = create_curriculum_change_set(
        source_document=source_document,
        change_type=CurriculumChangeSet.ChangeType.SOURCE_CHANGED,
        summary="Official source change proposed.",
        status=CurriculumChangeSet.Status.PUBLISHED,
    )

    assert change_set.status == CurriculumChangeSet.Status.DETECTED


def test_phase_boundary_no_crawler_or_future_app_activation(settings, app_root):
    assert "grading" in settings.INSTALLED_APPS
    assert "grading" not in settings.TENANT_APPS
    assert "reports" not in settings.INSTALLED_APPS
    assert not (app_root / "curriculum" / "crawler.py").exists()
