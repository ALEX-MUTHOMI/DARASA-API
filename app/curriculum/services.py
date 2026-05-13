from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import GradeLevel, LearningArea
from curriculum.algorithms.authority_normalizer import normalize_authority_code
from curriculum.algorithms.checksum import compute_sha256
from curriculum.algorithms.publication_state_machine import validate_transition
from curriculum.models import (
    AssessmentRubricFoundation,
    CoreCompetency,
    CurriculumAuthority,
    CurriculumChangeSet,
    CurriculumGradeMapping,
    CurriculumLearningArea,
    CurriculumPublication,
    CurriculumSourceDocument,
    CurriculumStage,
    CurriculumValue,
    CurriculumVersion,
    OutcomeCompetencyLink,
    OutcomePCILink,
    OutcomeValueLink,
    PertinentContemporaryIssue,
    SourceArtifact,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)


def _save_clean(instance: Any) -> Any:
    instance.full_clean()
    instance.save()
    return instance


def _require_active_reviewer(user: Any) -> None:
    if user is None or not getattr(user, "is_active", False):
        raise ValidationError({"reviewed_by": "An active reviewer is required."})


@transaction.atomic
def register_curriculum_authority(
    *,
    code: str,
    name: str,
    official_website: str,
    allowed_domains: list[str],
    is_active: bool = True,
    is_approved: bool = True,
) -> CurriculumAuthority:
    return _save_clean(
        CurriculumAuthority(
            code=normalize_authority_code(code),
            name=name,
            official_website=official_website,
            allowed_domains=allowed_domains,
            is_active=is_active,
            is_approved=is_approved,
        )
    )


@transaction.atomic
def register_source_document(
    *,
    authority: CurriculumAuthority,
    title: str,
    document_code: str,
    document_version_label: str,
    source_url: str,
    checksum: str,
) -> CurriculumSourceDocument:
    if not authority.is_active or not authority.is_approved:
        raise ValidationError({"authority": "Source authority is not approved."})
    return _save_clean(
        CurriculumSourceDocument(
            authority=authority,
            source_authority=authority.code,
            title=title,
            document_code=document_code,
            document_version_label=document_version_label,
            source_url=source_url,
            checksum=checksum,
        )
    )


def compute_source_checksum(content: bytes) -> str:
    return compute_sha256(content)


@transaction.atomic
def register_source_artifact(
    *,
    source_document: CurriculumSourceDocument,
    file_name: str,
    content_type: str,
    file_size: int,
    content: bytes,
    capture_method: str,
) -> SourceArtifact:
    if file_size != len(content):
        raise ValidationError({"file_size": "Artifact size does not match content."})
    checksum = compute_source_checksum(content)
    return _save_clean(
        SourceArtifact(
            source_document=source_document,
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
            checksum_algorithm="sha256",
            checksum=checksum,
            capture_method=capture_method,
        )
    )


@transaction.atomic
def create_curriculum_change_set(
    *,
    source_document: CurriculumSourceDocument,
    change_type: str,
    summary: str,
    old_curriculum_version: CurriculumVersion | None = None,
    proposed_curriculum_version: CurriculumVersion | None = None,
    status: str | None = None,
) -> CurriculumChangeSet:
    _ = status
    return _save_clean(
        CurriculumChangeSet(
            source_document=source_document,
            old_curriculum_version=old_curriculum_version,
            proposed_curriculum_version=proposed_curriculum_version,
            change_type=change_type,
            summary=summary,
            status=CurriculumChangeSet.Status.DETECTED,
        )
    )


def _move_change_set_to_review(change_set: CurriculumChangeSet) -> None:
    if change_set.status == CurriculumChangeSet.Status.DETECTED:
        validate_transition(
            CurriculumChangeSet.Status.DETECTED,
            CurriculumChangeSet.Status.QUARANTINED,
        )
        change_set.status = CurriculumChangeSet.Status.QUARANTINED
    if change_set.status == CurriculumChangeSet.Status.QUARANTINED:
        validate_transition(
            CurriculumChangeSet.Status.QUARANTINED,
            CurriculumChangeSet.Status.UNDER_REVIEW,
        )
        change_set.status = CurriculumChangeSet.Status.UNDER_REVIEW


@transaction.atomic
def approve_change_set(
    *,
    change_set: CurriculumChangeSet,
    reviewed_by: Any,
) -> CurriculumChangeSet:
    _require_active_reviewer(reviewed_by)
    _move_change_set_to_review(change_set)
    validate_transition(
        change_set.status,
        CurriculumChangeSet.Status.APPROVED,
    )
    change_set.status = CurriculumChangeSet.Status.APPROVED
    change_set.reviewed_by = reviewed_by
    change_set.reviewed_at = timezone.now()
    return _save_clean(change_set)


@transaction.atomic
def reject_change_set(
    *,
    change_set: CurriculumChangeSet,
    reviewed_by: Any,
) -> CurriculumChangeSet:
    _require_active_reviewer(reviewed_by)
    if change_set.status not in {
        CurriculumChangeSet.Status.DETECTED,
        CurriculumChangeSet.Status.QUARANTINED,
        CurriculumChangeSet.Status.UNDER_REVIEW,
        CurriculumChangeSet.Status.APPROVED,
    }:
        validate_transition(change_set.status, CurriculumChangeSet.Status.REJECTED)
    change_set.status = CurriculumChangeSet.Status.REJECTED
    change_set.reviewed_by = reviewed_by
    change_set.reviewed_at = timezone.now()
    return _save_clean(change_set)


@transaction.atomic
def create_curriculum_publication(
    *,
    curriculum_version: CurriculumVersion,
    effective_from: str,
    publication_notes: str,
    approved_by: Any | None = None,
    effective_to: str | None = None,
    is_active: bool = True,
    workflow_approved: bool = False,
) -> CurriculumPublication:
    if is_active and not workflow_approved:
        raise ValidationError(
            {"is_active": "Active publication requires approved workflow."}
        )
    if is_active:
        _require_active_reviewer(approved_by)
    return _save_clean(
        CurriculumPublication(
            curriculum_version=curriculum_version,
            effective_from=effective_from,
            effective_to=effective_to,
            is_active=is_active,
            publication_notes=publication_notes,
            approved_by=approved_by,
        )
    )


@transaction.atomic
def publish_curriculum_version(
    *,
    change_set: CurriculumChangeSet,
    curriculum_version: CurriculumVersion | None,
    approved_by: Any,
    effective_from: str,
    publication_notes: str = "Reviewed curriculum publication.",
) -> CurriculumPublication:
    if curriculum_version is None:
        raise ValidationError(
            {"curriculum_version": "Approved curriculum version is required."}
        )
    _require_active_reviewer(approved_by)
    if change_set.proposed_curriculum_version_id != curriculum_version.id:
        raise ValidationError(
            {"curriculum_version": "Published version must match the change set."}
        )
    validate_transition(change_set.status, CurriculumChangeSet.Status.PUBLISHED)
    publication = create_curriculum_publication(
        curriculum_version=curriculum_version,
        approved_by=approved_by,
        effective_from=effective_from,
        publication_notes=publication_notes,
        workflow_approved=True,
    )
    change_set.status = CurriculumChangeSet.Status.PUBLISHED
    change_set.reviewed_by = approved_by
    change_set.reviewed_at = timezone.now()
    _save_clean(change_set)
    return publication


@transaction.atomic
def supersede_curriculum_publication(
    *,
    publication: CurriculumPublication,
    superseded_by: CurriculumPublication,
) -> CurriculumPublication:
    publication.is_active = False
    publication.superseded_by = superseded_by
    return _save_clean(publication)


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
