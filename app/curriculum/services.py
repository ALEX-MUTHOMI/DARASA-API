"""Write-side curriculum services.

The services in this module are deliberately explicit about workflow state:
registering a source, approving a change, publishing a curriculum version,
issuing a principal evidence card, and acknowledging that card are separate
operations.  Keeping those steps apart prevents mass-assignment shortcuts and
preserves the audit trail a school principal needs.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import GradeLevel, LearningArea
from curriculum.algorithms.curriculum_impact_analyzer import analyze_diff_item_impact
from curriculum.algorithms.authority_normalizer import normalize_authority_code
from curriculum.algorithms.checksum import compute_sha256
from curriculum.algorithms.principal_notification_builder import (
    build_notification_payload,
)
from curriculum.algorithms.publication_state_machine import validate_transition
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
    AssessmentRubricFoundation,
    CoreCompetency,
    CurriculumAuthority,
    CurriculumChangeSet,
    CurriculumDiff,
    CurriculumDiffItem,
    CurriculumGradeMapping,
    CurriculumImpact,
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
    PrincipalNotificationEvidenceCard,
    RegulatoryImpact,
    RegulatoryNotice,
    SchoolUpdateAcknowledgement,
    SourceArtifact,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
    TeacherReadinessRequirement,
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


@transaction.atomic
def create_curriculum_diff(
    *,
    old_curriculum_version: CurriculumVersion,
    new_curriculum_version: CurriculumVersion,
    summary: str,
    source_change_set: CurriculumChangeSet | None = None,
    diff_status: str = CurriculumDiff.Status.DRAFT,
) -> CurriculumDiff:
    return _save_clean(
        CurriculumDiff(
            old_curriculum_version=old_curriculum_version,
            new_curriculum_version=new_curriculum_version,
            source_change_set=source_change_set,
            diff_status=diff_status,
            summary=summary,
        )
    )


@transaction.atomic
def create_curriculum_diff_items(
    *,
    curriculum_diff: CurriculumDiff,
    items: list[dict[str, Any]],
) -> list[CurriculumDiffItem]:
    created: list[CurriculumDiffItem] = []
    for item in items:
        created.append(
            _save_clean(
                CurriculumDiffItem(
                    curriculum_diff=curriculum_diff,
                    change_type=item["change_type"],
                    entity_type=item["entity_type"],
                    entity_identifier=item["entity_identifier"],
                    old_value_fingerprint=item.get("old_value_fingerprint", ""),
                    new_value_fingerprint=item.get("new_value_fingerprint", ""),
                    summary=item["summary"],
                    severity=item.get("severity", CurriculumDiffItem.Severity.MEDIUM),
                    requires_review=item.get("requires_review", True),
                )
            )
        )
    return created


@transaction.atomic
def analyze_curriculum_impact(
    *,
    diff_item: CurriculumDiffItem,
    affected_stage: str,
    affected_grade_level: GradeLevel | None = None,
    affected_learning_area: CurriculumLearningArea | None = None,
) -> list[CurriculumImpact]:
    proposals = analyze_diff_item_impact(
        {
            "change_type": diff_item.change_type,
            "entity_type": diff_item.entity_type,
            "entity_identifier": diff_item.entity_identifier,
            "summary": diff_item.summary,
            "affected_stage": affected_stage,
            "affected_grade_level": getattr(affected_grade_level, "name", ""),
            "affected_learning_area": getattr(
                affected_learning_area,
                "official_name",
                "",
            ),
        }
    )
    impacts: list[CurriculumImpact] = []
    for proposal in proposals:
        impacts.append(
            _save_clean(
                CurriculumImpact(
                    curriculum_diff=diff_item.curriculum_diff,
                    diff_item=diff_item,
                    affected_stage=affected_stage,
                    affected_grade_level=affected_grade_level,
                    affected_learning_area=affected_learning_area,
                    impact_category=proposal["impact_category"],
                    impact_severity=proposal["impact_severity"],
                    action_required=proposal["action_required"],
                )
            )
        )
    return impacts


@transaction.atomic
def register_regulatory_notice(
    *,
    authority: CurriculumAuthority,
    title: str,
    summary: str,
    notice_type: str | None = None,
    source_document: CurriculumSourceDocument | None = None,
    source_artifact: SourceArtifact | None = None,
    reference_number: str = "",
    publication_date: str | None = None,
    effective_date: str | None = None,
    review_status: str = RegulatoryNotice.ReviewStatus.PENDING_REVIEW,
    reviewed_by: Any | None = None,
    status: str | None = None,
) -> RegulatoryNotice:
    """Register source-backed regulatory intelligence without auto-activation."""
    _ = status
    if review_status == RegulatoryNotice.ReviewStatus.VERIFIED:
        _require_active_reviewer(reviewed_by)
    classified_type = notice_type or classify_notice_algorithm(
        authority_code=authority.code,
        title=title,
        summary=summary,
    )
    transition_signals = map_junior_to_senior_signals(title=title, summary=summary)
    affects_senior = any(
        signal in f"{title} {summary}".lower()
        for signal in ["senior school", "grade 10", "grade 11", "grade 12"]
    )
    notice = RegulatoryNotice(
        authority=authority,
        source_document=source_document,
        source_artifact=source_artifact,
        notice_type=classified_type,
        title=title,
        reference_number=reference_number,
        publication_date=publication_date,
        effective_date=effective_date,
        summary=summary,
        review_status=review_status,
        notice_status=RegulatoryNotice.NoticeStatus.DRAFT,
        affects_senior_school=affects_senior or bool(transition_signals),
        affects_junior_to_senior_transition=bool(transition_signals),
        reviewed_at=timezone.now()
        if review_status == RegulatoryNotice.ReviewStatus.VERIFIED
        else None,
        reviewed_by=reviewed_by
        if review_status == RegulatoryNotice.ReviewStatus.VERIFIED
        else None,
    )
    return _save_clean(notice)


@transaction.atomic
def classify_regulatory_notice(
    *,
    regulatory_notice: RegulatoryNotice,
) -> RegulatoryNotice:
    regulatory_notice.notice_type = classify_notice_algorithm(
        authority_code=regulatory_notice.authority.code,
        title=regulatory_notice.title,
        summary=regulatory_notice.summary,
    )
    regulatory_notice.affects_junior_to_senior_transition = bool(
        map_junior_to_senior_signals(
            title=regulatory_notice.title,
            summary=regulatory_notice.summary,
        )
    )
    if regulatory_notice.affects_junior_to_senior_transition:
        regulatory_notice.affects_senior_school = True
    return _save_clean(regulatory_notice)


@transaction.atomic
def create_regulatory_impact(
    *,
    regulatory_notice: RegulatoryNotice,
    impact_category: str,
    action_required: str,
    affected_grade_level: GradeLevel | None = None,
    affected_learning_area: LearningArea | None = None,
    affected_pathway: str = "",
    impact_severity: str = RegulatoryImpact.Severity.MEDIUM,
) -> RegulatoryImpact:
    return _save_clean(
        RegulatoryImpact(
            regulatory_notice=regulatory_notice,
            affected_grade_level=affected_grade_level,
            affected_learning_area=affected_learning_area,
            affected_pathway=affected_pathway,
            impact_category=impact_category,
            impact_severity=impact_severity,
            action_required=action_required,
        )
    )


@transaction.atomic
def map_teacher_readiness_requirement(
    *,
    regulatory_notice: RegulatoryNotice,
    summary: str,
    affected_learning_area: LearningArea | None = None,
    affected_grade_level: GradeLevel | None = None,
    affected_pathway: str = "",
    requirement_type: str | None = None,
) -> TeacherReadinessRequirement:
    mapped_type = requirement_type or map_teacher_requirement_algorithm(
        title=regulatory_notice.title,
        summary=f"{regulatory_notice.summary} {summary}",
    )
    return _save_clean(
        TeacherReadinessRequirement(
            regulatory_notice=regulatory_notice,
            affected_learning_area=affected_learning_area,
            affected_grade_level=affected_grade_level,
            affected_pathway=affected_pathway,
            requirement_type=mapped_type,
            summary=summary,
            effective_from=regulatory_notice.effective_date,
        )
    )


@transaction.atomic
def build_principal_notification_evidence_card(
    *,
    tenant: Any,
    regulatory_notice: RegulatoryNotice | None = None,
    curriculum_diff: CurriculumDiff | None = None,
    curriculum_impact: CurriculumImpact | None = None,
    notification_type: str = (
        PrincipalNotificationEvidenceCard.NotificationType.REGULATORY_NOTICE
    ),
    impact_summary: str = "Senior School regulatory update requires review.",
    required_action: str = "Principal review is required.",
    severity: str = PrincipalNotificationEvidenceCard.Severity.MEDIUM,
) -> PrincipalNotificationEvidenceCard:
    """Create a review-ready card from verified evidence, not a delivery event."""
    if (
        regulatory_notice is None
        and curriculum_diff is None
        and curriculum_impact is None
    ):
        raise ValidationError({"regulatory_notice": "Source evidence is required."})
    authority_name = "Curriculum source"
    source_reference = "Curriculum diff evidence"
    checksum = ""
    review_status = "approved"
    if regulatory_notice is not None:
        authority_name = regulatory_notice.authority.name
        source = regulatory_notice.source_document
        artifact = regulatory_notice.source_artifact
        source_reference = (
            source.document_code
            if source is not None
            else str(artifact.file_name if artifact is not None else "")
        )
        checksum = (
            source.checksum
            if source is not None and source.checksum
            else getattr(artifact, "checksum", "")
        )
        review_status = regulatory_notice.review_status
    payload = build_notification_payload(
        authority_name=authority_name,
        source_reference=source_reference,
        checksum=checksum,
        review_status=review_status,
        impact_summary=impact_summary,
        required_action=required_action,
    )
    return _save_clean(
        PrincipalNotificationEvidenceCard(
            tenant=tenant,
            regulatory_notice=regulatory_notice,
            curriculum_diff=curriculum_diff,
            curriculum_impact=curriculum_impact,
            notification_type=notification_type,
            title=payload["title"],
            summary=payload["summary"],
            evidence_summary=payload["evidence_summary"],
            required_action=payload["required_action"],
            severity=severity,
            status=PrincipalNotificationEvidenceCard.Status.READY_FOR_REVIEW,
        )
    )


@transaction.atomic
def issue_principal_notification_evidence_card(
    *,
    evidence_card: PrincipalNotificationEvidenceCard,
) -> PrincipalNotificationEvidenceCard:
    if (
        evidence_card.status
        != PrincipalNotificationEvidenceCard.Status.READY_FOR_REVIEW
    ):
        raise ValidationError({"status": "Evidence card is not ready for issue."})
    evidence_card.status = PrincipalNotificationEvidenceCard.Status.ISSUED
    return _save_clean(evidence_card)


@transaction.atomic
def acknowledge_school_update(
    *,
    evidence_card: PrincipalNotificationEvidenceCard,
    tenant: Any,
    acknowledged_by: Any,
    acknowledgement_status: str,
    principal_notes: str = "",
) -> SchoolUpdateAcknowledgement:
    """Record school acknowledgement without activating curriculum changes."""
    if evidence_card.tenant_id != tenant.id:
        raise ValidationError({"tenant": "Acknowledgement tenant is invalid."})
    if evidence_card.status not in {
        PrincipalNotificationEvidenceCard.Status.ISSUED,
        PrincipalNotificationEvidenceCard.Status.ACKNOWLEDGED,
    }:
        raise ValidationError({"status": "Notification has not been issued."})
    acknowledgement = _save_clean(
        SchoolUpdateAcknowledgement(
            tenant=tenant,
            notification_evidence_card=evidence_card,
            acknowledged_by=acknowledged_by,
            acknowledged_at=timezone.now(),
            acknowledgement_status=acknowledgement_status,
            principal_notes=principal_notes,
        )
    )
    evidence_card.status = PrincipalNotificationEvidenceCard.Status.ACKNOWLEDGED
    evidence_card.acknowledged_at = acknowledgement.acknowledged_at
    evidence_card.acknowledged_by = acknowledged_by
    _save_clean(evidence_card)
    return acknowledgement


@transaction.atomic
def archive_notification_evidence_card(
    *,
    evidence_card: PrincipalNotificationEvidenceCard,
) -> PrincipalNotificationEvidenceCard:
    evidence_card.status = PrincipalNotificationEvidenceCard.Status.ARCHIVED
    return _save_clean(evidence_card)
