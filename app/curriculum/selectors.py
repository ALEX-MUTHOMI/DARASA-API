from __future__ import annotations

from datetime import date

from django.db.models import QuerySet

from academics.models import GradeLevel, LearningArea
from curriculum.algorithms.version_resolver import resolve_publication_for_date
from curriculum.models import (
    AssessmentRubricFoundation,
    CoreCompetency,
    CurriculumAuthority,
    CurriculumChangeSet,
    CurriculumLearningArea,
    CurriculumPublication,
    CurriculumSourceDocument,
    CurriculumVersion,
    CurriculumValue,
    PertinentContemporaryIssue,
    SourceArtifact,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)


def get_active_curriculum_version() -> CurriculumVersion | None:
    return (
        CurriculumVersion.objects.filter(
            is_active=True,
            source_document__is_active=True,
        )
        .select_related("source_document")
        .order_by("-effective_from", "-created_at")
        .first()
    )


def get_curriculum_learning_areas_for_grade(
    *,
    curriculum_version: CurriculumVersion,
    grade_level: GradeLevel,
) -> QuerySet[CurriculumLearningArea]:
    return CurriculumLearningArea.objects.filter(
        curriculum_version=curriculum_version,
        grade_level=grade_level,
        is_active=True,
        curriculum_version__is_active=True,
    ).select_related("learning_area", "grade_level", "curriculum_version")


def get_curriculum_map(
    *,
    curriculum_version: CurriculumVersion,
    grade_level: GradeLevel,
    learning_area: LearningArea,
) -> CurriculumLearningArea | None:
    return CurriculumLearningArea.objects.filter(
        curriculum_version=curriculum_version,
        grade_level=grade_level,
        learning_area=learning_area,
        is_active=True,
        curriculum_version__is_active=True,
    ).first()


def get_strands_for_learning_area(
    curriculum_learning_area: CurriculumLearningArea,
) -> QuerySet[Strand]:
    return Strand.objects.filter(
        curriculum_learning_area=curriculum_learning_area,
        is_active=True,
        curriculum_learning_area__is_active=True,
    ).order_by("sequence_order", "title")


def get_sub_strands_for_strand(strand: Strand) -> QuerySet[SubStrand]:
    return SubStrand.objects.filter(
        strand=strand,
        is_active=True,
        strand__is_active=True,
    ).order_by("sequence_order", "title")


def get_outcomes_for_sub_strand(
    sub_strand: SubStrand,
) -> QuerySet[SpecificLearningOutcome]:
    return SpecificLearningOutcome.objects.filter(
        sub_strand=sub_strand,
        is_active=True,
        sub_strand__is_active=True,
    ).order_by("sequence_order", "id")


def get_competencies_for_outcome(
    learning_outcome: SpecificLearningOutcome,
) -> QuerySet[CoreCompetency]:
    return CoreCompetency.objects.filter(
        outcome_links__learning_outcome=learning_outcome,
        outcome_links__is_active=True,
        is_active=True,
    ).order_by("name")


def get_values_for_outcome(
    learning_outcome: SpecificLearningOutcome,
) -> QuerySet[CurriculumValue]:
    return CurriculumValue.objects.filter(
        outcome_links__learning_outcome=learning_outcome,
        outcome_links__is_active=True,
        is_active=True,
    ).order_by("name")


def get_pcis_for_outcome(
    learning_outcome: SpecificLearningOutcome,
) -> QuerySet[PertinentContemporaryIssue]:
    return PertinentContemporaryIssue.objects.filter(
        outcome_links__learning_outcome=learning_outcome,
        outcome_links__is_active=True,
        is_active=True,
    ).order_by("name")


def get_rubric_foundation_descriptors(
    learning_outcome: SpecificLearningOutcome,
) -> QuerySet[AssessmentRubricFoundation]:
    return AssessmentRubricFoundation.objects.filter(
        learning_outcome=learning_outcome,
        is_active=True,
    ).order_by("sequence_order", "level_code")


def get_active_authorities() -> QuerySet[CurriculumAuthority]:
    return CurriculumAuthority.objects.filter(
        is_active=True,
        is_approved=True,
    ).order_by("code")


def get_source_document_history(
    *,
    authority: CurriculumAuthority,
) -> QuerySet[CurriculumSourceDocument]:
    return CurriculumSourceDocument.objects.filter(
        authority=authority,
        is_active=True,
    ).order_by("-created_at", "document_code")


def get_quarantined_artifacts() -> QuerySet[SourceArtifact]:
    return SourceArtifact.objects.filter(
        quarantine_status=SourceArtifact.QuarantineStatus.QUARANTINED,
    ).select_related("source_document").order_by("captured_at")


def get_pending_change_sets() -> QuerySet[CurriculumChangeSet]:
    return CurriculumChangeSet.objects.filter(
        status__in=[
            CurriculumChangeSet.Status.DETECTED,
            CurriculumChangeSet.Status.QUARANTINED,
            CurriculumChangeSet.Status.UNDER_REVIEW,
        ],
    ).order_by("detected_at")


def get_approved_change_sets() -> QuerySet[CurriculumChangeSet]:
    return CurriculumChangeSet.objects.filter(
        status=CurriculumChangeSet.Status.APPROVED,
    ).order_by("reviewed_at", "detected_at")


def get_rejected_change_sets() -> QuerySet[CurriculumChangeSet]:
    return CurriculumChangeSet.objects.filter(
        status=CurriculumChangeSet.Status.REJECTED,
    ).order_by("reviewed_at", "detected_at")


def get_active_curriculum_publication() -> CurriculumPublication | None:
    return (
        CurriculumPublication.objects.filter(
            is_active=True,
            superseded_by__isnull=True,
        )
        .select_related("curriculum_version", "curriculum_version__source_document")
        .order_by("-effective_from", "-published_at")
        .first()
    )


def get_curriculum_publication_history(
    curriculum_version: CurriculumVersion,
) -> QuerySet[CurriculumPublication]:
    return CurriculumPublication.objects.filter(
        curriculum_version=curriculum_version,
    ).order_by("-effective_from", "-published_at")


def resolve_curriculum_version_for_date(
    *,
    on_date: date,
) -> CurriculumVersion | None:
    publications = CurriculumPublication.objects.filter(
        effective_from__lte=on_date,
    ).select_related("curriculum_version")
    publication = resolve_publication_for_date(publications, on_date=on_date)
    if publication is None:
        return None
    return publication.curriculum_version
