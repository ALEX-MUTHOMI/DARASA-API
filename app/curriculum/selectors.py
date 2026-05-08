from __future__ import annotations

from django.db.models import QuerySet

from academics.models import GradeLevel, LearningArea
from curriculum.models import (
    AssessmentRubricFoundation,
    CoreCompetency,
    CurriculumLearningArea,
    CurriculumVersion,
    CurriculumValue,
    PertinentContemporaryIssue,
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
