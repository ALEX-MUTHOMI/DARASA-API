from __future__ import annotations

from typing import Any

from django.db import transaction

from academics.models import GradeLevel, LearningArea
from curriculum.models import (
    AssessmentRubricFoundation,
    CoreCompetency,
    CurriculumGradeMapping,
    CurriculumLearningArea,
    CurriculumSourceDocument,
    CurriculumStage,
    CurriculumValue,
    CurriculumVersion,
    OutcomeCompetencyLink,
    OutcomePCILink,
    OutcomeValueLink,
    PertinentContemporaryIssue,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)


def _save_clean(instance: Any) -> Any:
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_curriculum_source_document(
    *,
    source_authority: str,
    title: str,
    document_code: str,
    document_version_label: str,
    source_url: str = "",
    checksum: str = "",
) -> CurriculumSourceDocument:
    return _save_clean(
        CurriculumSourceDocument(
            source_authority=source_authority,
            title=title,
            document_code=document_code,
            document_version_label=document_version_label,
            source_url=source_url,
            checksum=checksum,
        )
    )


@transaction.atomic
def create_curriculum_version(
    *,
    source_document: CurriculumSourceDocument,
    version_label: str,
    effective_from: str,
    effective_to: str | None = None,
    is_active: bool = True,
) -> CurriculumVersion:
    return _save_clean(
        CurriculumVersion(
            source_document=source_document,
            version_label=version_label,
            effective_from=effective_from,
            effective_to=effective_to,
            is_active=is_active,
        )
    )


@transaction.atomic
def map_grade_level_to_curriculum_version(
    *,
    grade_level: GradeLevel,
    curriculum_stage: CurriculumStage,
    curriculum_version: CurriculumVersion,
    is_active: bool = True,
) -> CurriculumGradeMapping:
    return _save_clean(
        CurriculumGradeMapping(
            grade_level=grade_level,
            curriculum_stage=curriculum_stage,
            curriculum_version=curriculum_version,
            is_active=is_active,
        )
    )


@transaction.atomic
def map_learning_area_to_curriculum_version(
    *,
    curriculum_version: CurriculumVersion,
    grade_level: GradeLevel,
    learning_area: LearningArea,
    official_name: str,
    official_code: str = "",
    is_active: bool = True,
) -> CurriculumLearningArea:
    return _save_clean(
        CurriculumLearningArea(
            curriculum_version=curriculum_version,
            grade_level=grade_level,
            learning_area=learning_area,
            official_name=official_name,
            official_code=official_code,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_strand(
    *,
    curriculum_learning_area: CurriculumLearningArea,
    title: str,
    sequence_order: int,
    code: str = "",
    is_active: bool = True,
) -> Strand:
    return _save_clean(
        Strand(
            curriculum_learning_area=curriculum_learning_area,
            code=code,
            title=title,
            sequence_order=sequence_order,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_sub_strand(
    *,
    strand: Strand,
    title: str,
    sequence_order: int,
    code: str = "",
    suggested_time_allocation: str = "",
    is_active: bool = True,
) -> SubStrand:
    return _save_clean(
        SubStrand(
            strand=strand,
            code=code,
            title=title,
            sequence_order=sequence_order,
            suggested_time_allocation=suggested_time_allocation,
            is_active=is_active,
        )
    )


@transaction.atomic
def create_learning_outcome(
    *,
    sub_strand: SubStrand,
    text: str,
    sequence_order: int,
    is_active: bool = True,
) -> SpecificLearningOutcome:
    return _save_clean(
        SpecificLearningOutcome(
            sub_strand=sub_strand,
            text=text,
            sequence_order=sequence_order,
            is_active=is_active,
        )
    )


@transaction.atomic
def link_outcome_to_competency(
    *,
    learning_outcome: SpecificLearningOutcome,
    competency: CoreCompetency,
) -> OutcomeCompetencyLink:
    return _save_clean(
        OutcomeCompetencyLink(
            learning_outcome=learning_outcome,
            competency=competency,
        )
    )


@transaction.atomic
def link_outcome_to_value(
    *,
    learning_outcome: SpecificLearningOutcome,
    value: CurriculumValue,
) -> OutcomeValueLink:
    return _save_clean(
        OutcomeValueLink(
            learning_outcome=learning_outcome,
            value=value,
        )
    )


@transaction.atomic
def link_outcome_to_pci(
    *,
    learning_outcome: SpecificLearningOutcome,
    pci: PertinentContemporaryIssue,
) -> OutcomePCILink:
    return _save_clean(
        OutcomePCILink(
            learning_outcome=learning_outcome,
            pci=pci,
        )
    )


@transaction.atomic
def create_rubric_foundation_descriptor(
    *,
    learning_outcome: SpecificLearningOutcome,
    level_code: str,
    level_label: str,
    descriptor: str,
    sequence_order: int,
    is_active: bool = True,
) -> AssessmentRubricFoundation:
    return _save_clean(
        AssessmentRubricFoundation(
            learning_outcome=learning_outcome,
            level_code=level_code,
            level_label=level_label,
            descriptor=descriptor,
            sequence_order=sequence_order,
            is_active=is_active,
        )
    )
