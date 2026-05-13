import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import TenantUserRole
from core.policies import PolicyContext
from curriculum.models import (
    AssessmentRubricFoundation,
    CurriculumSourceDocument,
    CurriculumVersion,
    OutcomeCompetencyLink,
    OutcomePCILink,
    OutcomeValueLink,
    SpecificLearningOutcome,
    Strand,
)
from curriculum.policies import (
    can_activate_curriculum_version,
    can_create_curriculum_structure,
    can_manage_curriculum_source_documents,
    can_view_curriculum_map,
    can_view_rubric_foundation,
)
from curriculum.selectors import (
    get_active_curriculum_version,
    get_competencies_for_outcome,
    get_curriculum_learning_areas_for_grade,
    get_curriculum_map,
    get_outcomes_for_sub_strand,
    get_rubric_foundation_descriptors,
    get_strands_for_learning_area,
    get_sub_strands_for_strand,
)
from curriculum.services import (
    create_curriculum_source_document,
    create_curriculum_version,
    create_learning_outcome,
    create_rubric_foundation_descriptor,
    create_strand,
    create_sub_strand,
    link_outcome_to_competency,
    link_outcome_to_pci,
    link_outcome_to_value,
    map_grade_level_to_curriculum_version,
    map_learning_area_to_curriculum_version,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def test_curriculum_migration_exists_and_models_use_uuid_primary_keys(
    app_root,
    core_competency,
    curriculum_learning_area,
    curriculum_stage,
    curriculum_value,
    curriculum_version,
    grade_mapping,
    key_inquiry_question,
    learning_experience,
    learning_outcome,
    pci,
    source_document,
    strand,
    sub_strand,
):
    assert (app_root / "curriculum" / "migrations" / "0001_initial.py").exists()

    rubric = AssessmentRubricFoundation.objects.create(
        learning_outcome=learning_outcome,
        level_code="approaching",
        level_label="Approaching expectation",
        descriptor="Foundational descriptor.",
        sequence_order=1,
    )
    competency_link = OutcomeCompetencyLink.objects.create(
        learning_outcome=learning_outcome,
        competency=core_competency,
    )
    value_link = OutcomeValueLink.objects.create(
        learning_outcome=learning_outcome,
        value=curriculum_value,
    )
    pci_link = OutcomePCILink.objects.create(
        learning_outcome=learning_outcome,
        pci=pci,
    )

    for instance in [
        source_document,
        curriculum_version,
        curriculum_stage,
        grade_mapping,
        curriculum_learning_area,
        strand,
        sub_strand,
        learning_outcome,
        learning_experience,
        key_inquiry_question,
        core_competency,
        curriculum_value,
        pci,
        rubric,
        competency_link,
        value_link,
        pci_link,
    ]:
        assert isinstance(instance.pk, uuid.UUID)


def test_source_document_integrity_validation():
    with pytest.raises(ValidationError):
        create_curriculum_source_document(
            source_authority="random_blog",
            title="Unofficial Summary",
            document_code="BLOG-1",
            document_version_label="draft",
        )

    with pytest.raises(ValidationError):
        create_curriculum_source_document(
            source_authority=CurriculumSourceDocument.SourceAuthority.KICD,
            title=" ",
            document_code="KICD-BLANK",
            document_version_label="2026",
        )

    with pytest.raises(ValidationError):
        create_curriculum_source_document(
            source_authority=CurriculumSourceDocument.SourceAuthority.KICD,
            title="Official Reference",
            document_code="KICD-BAD-URL",
            source_url="not-a-url",
            document_version_label="2026",
        )


def test_duplicate_source_and_version_are_rejected(source_document):
    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            CurriculumSourceDocument.objects.create(
                source_authority=source_document.source_authority,
                title="Duplicate",
                document_code=source_document.document_code,
                document_version_label=source_document.document_version_label,
            )

    create_curriculum_version(
        source_document=source_document,
        version_label="duplicate-version",
        effective_from="2026-01-01",
    )

    with pytest.raises((IntegrityError, ValidationError)):
        create_curriculum_version(
            source_document=source_document,
            version_label="duplicate-version",
            effective_from="2026-01-01",
        )


def test_curriculum_structure_creation_and_duplicate_protection(
    curriculum_learning_area,
    curriculum_stage,
    curriculum_version,
    grade_level,
    learning_area,
    strand,
    sub_strand,
):
    mapping = map_grade_level_to_curriculum_version(
        grade_level=grade_level,
        curriculum_stage=curriculum_stage,
        curriculum_version=curriculum_version,
        is_active=False,
    )
    assert mapping.grade_level == grade_level

    assert curriculum_learning_area.learning_area == learning_area

    with pytest.raises((IntegrityError, ValidationError)):
        map_learning_area_to_curriculum_version(
            curriculum_version=curriculum_version,
            grade_level=grade_level,
            learning_area=learning_area,
            official_name="Duplicate learning area",
            official_code="official-code",
            is_active=False,
        )

    with pytest.raises((IntegrityError, ValidationError)):
        create_strand(
            curriculum_learning_area=curriculum_learning_area,
            title=strand.title,
            sequence_order=2,
        )

    with pytest.raises((IntegrityError, ValidationError)):
        create_sub_strand(
            strand=strand,
            title=sub_strand.title,
            sequence_order=2,
        )


def test_blank_curriculum_text_is_rejected(sub_strand):
    with pytest.raises(ValidationError):
        create_learning_outcome(
            sub_strand=sub_strand,
            text=" ",
            sequence_order=1,
        )


def test_cbe_structure_can_represent_foundational_curriculum_graph(
    core_competency,
    curriculum_value,
    key_inquiry_question,
    learning_experience,
    learning_outcome,
    pci,
    sub_strand,
):
    competency_link = link_outcome_to_competency(
        learning_outcome=learning_outcome,
        competency=core_competency,
    )
    value_link = link_outcome_to_value(
        learning_outcome=learning_outcome,
        value=curriculum_value,
    )
    pci_link = link_outcome_to_pci(
        learning_outcome=learning_outcome,
        pci=pci,
    )
    rubric = create_rubric_foundation_descriptor(
        learning_outcome=learning_outcome,
        level_code="meeting",
        level_label="Meeting expectation",
        descriptor="Descriptor for future rubric use.",
        sequence_order=1,
    )

    assert learning_outcome.sub_strand == sub_strand
    assert learning_experience.learning_outcome == learning_outcome
    assert key_inquiry_question.sub_strand == sub_strand
    assert competency_link.learning_outcome == learning_outcome
    assert value_link.learning_outcome == learning_outcome
    assert pci_link.learning_outcome == learning_outcome
    assert rubric.learning_outcome == learning_outcome


def test_ordered_selectors_return_active_content(
    curriculum_learning_area,
    learning_outcome,
    strand,
    sub_strand,
):
    Strand.objects.create(
        curriculum_learning_area=curriculum_learning_area,
        title="Inactive Strand",
        sequence_order=2,
        is_active=False,
    )
    SpecificLearningOutcome.objects.create(
        sub_strand=sub_strand,
        text="Inactive outcome",
        sequence_order=2,
        is_active=False,
    )

    assert list(get_strands_for_learning_area(curriculum_learning_area))[0] == strand
    assert list(get_sub_strands_for_strand(strand))[0] == sub_strand
    assert list(get_outcomes_for_sub_strand(sub_strand))[0] == learning_outcome


def test_curriculum_map_selector_is_version_and_grade_aware(
    curriculum_learning_area,
    curriculum_version,
    grade_level,
    learning_area,
):
    assert get_active_curriculum_version() == curriculum_version
    assert list(
        get_curriculum_learning_areas_for_grade(
            curriculum_version=curriculum_version,
            grade_level=grade_level,
        )
    ) == [curriculum_learning_area]
    assert get_curriculum_map(
        curriculum_version=curriculum_version,
        grade_level=grade_level,
        learning_area=learning_area,
    ) == curriculum_learning_area


def test_link_and_rubric_selectors_are_ordered_and_bounded(
    core_competency,
    django_assert_max_num_queries,
    learning_outcome,
):
    link_outcome_to_competency(
        learning_outcome=learning_outcome,
        competency=core_competency,
    )
    create_rubric_foundation_descriptor(
        learning_outcome=learning_outcome,
        level_code="exceeding",
        level_label="Exceeding expectation",
        descriptor="Descriptor for future assessment use.",
        sequence_order=1,
    )

    with django_assert_max_num_queries(1):
        competencies = list(get_competencies_for_outcome(learning_outcome))
    with django_assert_max_num_queries(1):
        rubric = list(get_rubric_foundation_descriptors(learning_outcome))

    assert competencies == [core_competency]
    assert rubric[0].level_code == "exceeding"


def test_curriculum_map_selector_uses_bounded_queries(
    curriculum_learning_area,
    curriculum_version,
    django_assert_max_num_queries,
    grade_level,
    learning_area,
):
    with django_assert_max_num_queries(1):
        result = get_curriculum_map(
            curriculum_version=curriculum_version,
            grade_level=grade_level,
            learning_area=learning_area,
        )

    assert result == curriculum_learning_area


def test_curriculum_policies_fail_closed_for_mutation(
    curriculum_learning_area,
    principal_role,
    principal_user,
    school,
):
    assert not can_manage_curriculum_source_documents(
        PolicyContext(tenant=school, actor=None, action="curriculum.manage_source")
    )
    assert not can_create_curriculum_structure(
        PolicyContext(
            tenant=school,
            actor=principal_user,
            action="curriculum.create_structure",
            role=None,
        )
    )
    assert can_view_curriculum_map(
        PolicyContext(
            tenant=school,
            actor=principal_user,
            action="curriculum.view_map",
            role=principal_role,
        ),
        curriculum_learning_area=curriculum_learning_area,
    )


def test_inactive_role_binding_denies_curriculum_management(
    principal_role,
    principal_user,
    school,
):
    TenantUserRole.objects.filter(
        tenant=school,
        user=principal_user,
        role=principal_role,
    ).update(is_active=False)

    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.manage_source",
        role=principal_role,
    )

    assert not can_manage_curriculum_source_documents(context)
    assert not can_activate_curriculum_version(context)


def test_rubric_foundation_view_policy_is_read_only(
    learning_outcome,
    principal_role,
    principal_user,
    school,
):
    context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.view_rubric_foundation",
        role=principal_role,
    )

    assert can_view_rubric_foundation(context, learning_outcome=learning_outcome)


def test_inactive_curriculum_version_not_returned_by_default(
    source_document,
):
    inactive = CurriculumVersion.objects.create(
        source_document=source_document,
        version_label="inactive-version",
        effective_from="2027-01-01",
        is_active=False,
    )

    assert get_active_curriculum_version() != inactive


def test_phase_boundaries_keep_grading_quarantined(settings):
    assert "grading" not in settings.INSTALLED_APPS
    assert "grading" not in settings.TENANT_APPS
