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
    CurriculumDiff,
    CurriculumDiffItem,
    CurriculumImpact,
    CurriculumLearningArea,
    CurriculumPublication,
    CurriculumSourceDocument,
    CurriculumVersion,
    CurriculumValue,
    PertinentContemporaryIssue,
    PrincipalNotificationEvidenceCard,
    RegulatoryNotice,
    SchoolUpdateAcknowledgement,
    SourceArtifact,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
    TeacherReadinessRequirement,
)
from tenant.models import School


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


def get_curriculum_diffs() -> QuerySet[CurriculumDiff]:
    return CurriculumDiff.objects.exclude(
        diff_status=CurriculumDiff.Status.REJECTED,
    ).select_related(
        "old_curriculum_version",
        "new_curriculum_version",
        "source_change_set",
    ).order_by("-created_at")


def get_diff_items_for_review() -> QuerySet[CurriculumDiffItem]:
    return CurriculumDiffItem.objects.filter(
        requires_review=True,
        curriculum_diff__diff_status__in=[
            CurriculumDiff.Status.DRAFT,
            CurriculumDiff.Status.UNDER_REVIEW,
        ],
    ).select_related("curriculum_diff").order_by(
        "severity",
        "entity_type",
        "entity_identifier",
    )


def get_impacts_for_senior_school() -> QuerySet[CurriculumImpact]:
    return CurriculumImpact.objects.filter(
        impact_category=CurriculumImpact.Category.SENIOR_SCHOOL_CURRICULUM,
    ).select_related(
        "diff_item",
        "affected_grade_level",
        "affected_learning_area",
    ).order_by("-created_at")


def get_impacts_for_junior_to_senior_transition() -> QuerySet[CurriculumImpact]:
    return CurriculumImpact.objects.filter(
        impact_category=CurriculumImpact.Category.JUNIOR_TO_SENIOR_TRANSITION,
    ).select_related("diff_item", "affected_grade_level").order_by("-created_at")


def get_regulatory_notices_for_review() -> QuerySet[RegulatoryNotice]:
    return RegulatoryNotice.objects.filter(
        review_status=RegulatoryNotice.ReviewStatus.PENDING_REVIEW,
    ).select_related("authority", "source_document", "source_artifact").order_by(
        "created_at"
    )


def get_verified_regulatory_notices() -> QuerySet[RegulatoryNotice]:
    return RegulatoryNotice.objects.filter(
        review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
        notice_status__in=[
            RegulatoryNotice.NoticeStatus.DRAFT,
            RegulatoryNotice.NoticeStatus.ACTIVE,
        ],
    ).select_related("authority", "source_document", "source_artifact").order_by(
        "-effective_date",
        "-created_at",
    )


def get_teacher_readiness_requirements() -> QuerySet[TeacherReadinessRequirement]:
    return TeacherReadinessRequirement.objects.filter(
        is_active=True,
        regulatory_notice__review_status=RegulatoryNotice.ReviewStatus.VERIFIED,
    ).select_related(
        "regulatory_notice",
        "affected_learning_area",
        "affected_grade_level",
    ).order_by("-effective_from", "requirement_type")


def get_pending_principal_notifications(
    *,
    tenant: School | None = None,
) -> QuerySet[PrincipalNotificationEvidenceCard]:
    queryset = PrincipalNotificationEvidenceCard.objects.filter(
        status=PrincipalNotificationEvidenceCard.Status.READY_FOR_REVIEW,
    ).select_related("tenant", "regulatory_notice", "curriculum_diff")
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    return queryset.order_by("-created_at")


def get_issued_principal_notifications_for_school(
    *,
    tenant: School,
) -> QuerySet[PrincipalNotificationEvidenceCard]:
    return PrincipalNotificationEvidenceCard.objects.filter(
        tenant=tenant,
        status__in=[
            PrincipalNotificationEvidenceCard.Status.ISSUED,
            PrincipalNotificationEvidenceCard.Status.ACKNOWLEDGED,
        ],
    ).select_related("regulatory_notice", "curriculum_diff").order_by("-created_at")


def get_acknowledgements_for_school(
    *,
    tenant: School,
) -> QuerySet[SchoolUpdateAcknowledgement]:
    return SchoolUpdateAcknowledgement.objects.filter(
        tenant=tenant,
    ).select_related(
        "notification_evidence_card",
        "acknowledged_by",
    ).order_by("-acknowledged_at")
