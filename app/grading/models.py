"""Tenant-scoped grading records for Phase 6A.

Grades are sensitive academic records.  The models enforce tenant consistency,
teacher assignment context, score bounds, and auditable correction requests
before later phases add submission workflows or compiled academic summaries.
Operational assessments are also bound to CCT curriculum context so grading
cannot drift into an isolated marks table.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from academics.models import (
    AcademicYear,
    Cohort,
    Enrollment,
    GradeLevel,
    LearningArea,
    Student,
    TeacherAssignment,
    Term,
)
from grading.algorithms.assessment_lifecycle import (
    changed_curriculum_context_fields,
    curriculum_context_mutation_allowed,
)
from grading.algorithms.curriculum_binding import (
    assessment_status_requires_binding,
    validate_curriculum_binding,
)
from grading.algorithms.score_bounds import validate_score_bounds
from tenant.models import School, TimeStampedModel


def _related_tenant_id(instance: Any, attribute: str) -> Any:
    try:
        related = getattr(instance, attribute)
    except (AttributeError, instance.__class__.DoesNotExist):
        return None
    return getattr(related, "tenant_id", None)


class Assessment(TimeStampedModel):
    class AssessmentType(models.TextChoices):
        QUIZ = "quiz", _("Quiz")
        ASSIGNMENT = "assignment", _("Assignment")
        PRACTICAL = "practical", _("Practical")
        EXAM = "exam", _("Exam")
        PROJECT = "project", _("Project")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        OPEN = "open", _("Open")
        LOCKED = "locked", _("Locked")
        SUBMITTED = "submitted", _("Submitted")
        APPROVED = "approved", _("Approved")
        ARCHIVED = "archived", _("Archived")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="assessments")
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessments",
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    curriculum_version = models.ForeignKey(
        "curriculum.CurriculumVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessments",
    )
    rubric_foundation = models.ForeignKey(
        "curriculum.AssessmentRubricFoundation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessments",
    )
    title = models.CharField(max_length=150)
    assessment_type = models.CharField(
        max_length=32,
        choices=AssessmentType.choices,
        default=AssessmentType.EXAM,
    )
    max_score = models.DecimalField(max_digits=7, decimal_places=2)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=Decimal("1.00"),
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_assessments",
    )
    curriculum_binding_locked_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["tenant", "status"], name="grading_assess_status_idx"),
            models.Index(
                fields=["tenant", "cohort", "learning_area"],
                name="grading_assess_context_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_score__gt=0),
                name="grading_assessment_max_score_positive",
            ),
            models.CheckConstraint(
                condition=Q(weight__gte=0) & Q(weight__lte=100),
                name="grading_assessment_weight_bounded",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.title:
            self.title = self.title.strip()
        validate_score_bounds(score=0, max_score=self.max_score)
        related_tenants = [
            _related_tenant_id(self, "academic_year"),
            _related_tenant_id(self, "term"),
            _related_tenant_id(self, "cohort"),
            _related_tenant_id(self, "learning_area"),
        ]
        if self.tenant_id and any(value != self.tenant_id for value in related_tenants):
            raise ValidationError({"tenant": _("Assessment tenant is invalid.")})
        if self.cohort_id and self.grade_level_id:
            if self.cohort.grade_level_id != self.grade_level_id:
                raise ValidationError(
                    {"grade_level": _("Assessment grade is invalid.")}
                )
        if self.opens_at and self.closes_at and self.opens_at >= self.closes_at:
            raise ValidationError({"closes_at": _("Close time must follow open time.")})
        self._validate_curriculum_binding_for_status()
        self._validate_curriculum_context_immutability()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        if (
            assessment_status_requires_binding(self.status)
            and self.curriculum_binding_locked_at is None
        ):
            # This timestamp records the curriculum snapshot used when the
            # assessment became operational.  It is not a school activation.
            self.curriculum_binding_locked_at = timezone.now()
        return super().save(*args, **kwargs)

    def is_operationally_bound(self) -> bool:
        """Return whether the stored assessment context is safe for grading.

        Policies and selectors use this cheap persisted check instead of
        asking CCT to resolve curriculum truth for every score.
        """

        if not assessment_status_requires_binding(self.status):
            return False
        return validate_curriculum_binding(
            status=self.status,
            curriculum_version_id=self.curriculum_version_id,
            learning_area_id=self.learning_area_id,
            rubric_foundation_id=self.rubric_foundation_id,
            curriculum_version_is_active=True,
            has_active_publication=True,
            rubric_matches_context=self._rubric_matches_assessment_context(),
            require_locked_binding=True,
            binding_locked=self.curriculum_binding_locked_at is not None,
        ).is_bound

    def _validate_curriculum_binding_for_status(self) -> None:
        if not assessment_status_requires_binding(self.status):
            return
        result = validate_curriculum_binding(
            status=self.status,
            curriculum_version_id=self.curriculum_version_id,
            learning_area_id=self.learning_area_id,
            rubric_foundation_id=self.rubric_foundation_id,
            curriculum_version_is_active=bool(
                getattr(self.curriculum_version, "is_active", False)
            ),
            has_active_publication=self._has_active_curriculum_publication(),
            rubric_matches_context=self._rubric_matches_assessment_context(),
        )
        if not result.is_bound:
            raise ValidationError(
                {"curriculum_version": _("Assessment curriculum binding is invalid.")}
            )

    def _has_active_curriculum_publication(self) -> bool:
        if self.curriculum_version_id is None:
            return False
        from curriculum.models import CurriculumPublication

        return CurriculumPublication.objects.filter(
            curriculum_version_id=self.curriculum_version_id,
            is_active=True,
        ).exists()

    def _rubric_matches_assessment_context(self) -> bool:
        if (
            self.rubric_foundation_id is None
            or self.curriculum_version_id is None
            or self.learning_area_id is None
        ):
            return False
        rubric = self.rubric_foundation
        if not getattr(rubric, "is_active", False):
            return False
        sub_strand = getattr(rubric, "sub_strand", None)
        outcome = getattr(rubric, "learning_outcome", None)
        if outcome is not None:
            sub_strand = outcome.sub_strand
        if sub_strand is None:
            return False
        curriculum_learning_area = sub_strand.strand.curriculum_learning_area
        return (
            curriculum_learning_area.curriculum_version_id
            == self.curriculum_version_id
            and curriculum_learning_area.learning_area_id == self.learning_area_id
        )

    def _validate_curriculum_context_immutability(self) -> None:
        if self.pk is None:
            return
        original = (
            Assessment.objects.filter(pk=self.pk)
            .values("curriculum_version_id", "learning_area_id", "rubric_foundation_id")
            .first()
        )
        if original is None:
            return
        changed_fields = changed_curriculum_context_fields(
            old_values={
                "curriculum_version": original["curriculum_version_id"],
                "learning_area": original["learning_area_id"],
                "rubric_foundation": original["rubric_foundation_id"],
            },
            new_values={
                "curriculum_version": self.curriculum_version_id,
                "learning_area": self.learning_area_id,
                "rubric_foundation": self.rubric_foundation_id,
            },
        )
        if not changed_fields:
            return
        has_submitted_batches = self.submission_batches.exclude(
            status=GradeSubmissionBatch.Status.DRAFT,
        ).exists()
        has_grade_records = self.grade_records.exists()
        if not curriculum_context_mutation_allowed(
            changed_fields=changed_fields,
            has_submitted_batches=has_submitted_batches,
            has_grade_records=has_grade_records,
        ):
            raise ValidationError(
                {
                    "curriculum_version": _(
                        "Assessment curriculum context cannot be changed "
                        "after grading begins."
                    )
                }
            )

    def __str__(self) -> str:
        return f"Assessment {self.pk}"


class GradeSubmissionBatch(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        VALIDATED = "validated", _("Validated")
        REJECTED = "rejected", _("Rejected")
        COMPILED = "compiled", _("Compiled")
        FAILED = "failed", _("Failed")
        SUPERSEDED = "superseded", _("Superseded")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="grade_batches",
    )
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.PROTECT,
        related_name="submission_batches",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grade_submission_batches",
    )
    teacher_assignment = models.ForeignKey(
        TeacherAssignment,
        on_delete=models.PROTECT,
        related_name="grade_submission_batches",
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.PROTECT,
        related_name="grade_batches",
    )
    learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.PROTECT,
        related_name="grade_batches",
    )
    idempotency_key = models.CharField(max_length=180, blank=True)
    record_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    compiled_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(
                fields=["tenant", "assessment"],
                name="grading_batch_assess_idx",
            ),
            models.Index(
                fields=["tenant", "teacher"],
                name="grading_batch_teacher_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "assessment", "teacher", "teacher_assignment"],
                condition=Q(status__in=["submitted", "validated", "compiled"]),
                name="grading_active_batch_unique",
            ),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="grading_batch_idempotency_unique",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        related_tenants = [
            getattr(self.assessment, "tenant_id", None),
            getattr(self.teacher_assignment, "tenant_id", None),
            getattr(self.cohort, "tenant_id", None),
            getattr(self.learning_area, "tenant_id", None),
        ]
        if self.tenant_id and any(value != self.tenant_id for value in related_tenants):
            raise ValidationError({"tenant": _("Grade batch tenant is invalid.")})
        if self.assessment_id:
            if self.assessment.cohort_id != self.cohort_id:
                raise ValidationError({"cohort": _("Grade batch cohort is invalid.")})
            if self.assessment.learning_area_id != self.learning_area_id:
                raise ValidationError(
                    {"learning_area": _("Grade batch area is invalid.")}
                )
        if self.teacher_assignment_id:
            assignment = self.teacher_assignment
            if assignment.teacher_id != self.teacher_id:
                raise ValidationError({"teacher": _("Grade batch teacher is invalid.")})
            if assignment.cohort_id != self.cohort_id:
                raise ValidationError({"cohort": _("Teacher assignment is invalid.")})
            if assignment.learning_area_id != self.learning_area_id:
                raise ValidationError(
                    {"learning_area": _("Teacher assignment is invalid.")}
                )
            if not assignment.is_active:
                raise ValidationError(
                    {"teacher_assignment": _("Teacher assignment is inactive.")}
                )
        if self.status != self.Status.DRAFT and not self.idempotency_key.strip():
            raise ValidationError(
                {"idempotency_key": _("Idempotency key is required.")}
            )
        if (
            self.status != self.Status.DRAFT
            and not self.assessment.is_operationally_bound()
        ):
            raise ValidationError(
                {"assessment": _("Assessment is not open for CBE-bound grading.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"GradeSubmissionBatch {self.pk}"


class GradeRecord(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="grade_records",
    )
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.PROTECT,
        related_name="grade_records",
    )
    submission_batch = models.ForeignKey(
        GradeSubmissionBatch,
        on_delete=models.PROTECT,
        related_name="grade_records",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="grade_records",
    )
    raw_score = models.DecimalField(max_digits=7, decimal_places=2)
    normalized_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rubric_level = models.CharField(max_length=32, blank=True)
    remarks = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_grade_records",
    )

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(
                fields=["tenant", "assessment"],
                name="grading_record_assess_idx",
            ),
            models.Index(
                fields=["tenant", "student"],
                name="grading_record_student_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "assessment", "student"],
                name="grading_record_assessment_student_unique",
            ),
            models.CheckConstraint(
                condition=Q(raw_score__gte=0),
                name="grading_record_score_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1),
                name="grading_record_version_positive",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_score_bounds(score=self.raw_score, max_score=self.assessment.max_score)
        related_tenants = [
            getattr(self.assessment, "tenant_id", None),
            getattr(self.submission_batch, "tenant_id", None),
            getattr(self.student, "tenant_id", None),
        ]
        if self.tenant_id and any(value != self.tenant_id for value in related_tenants):
            raise ValidationError({"tenant": _("Grade record tenant is invalid.")})
        if (
            self.submission_batch_id
            and self.submission_batch.assessment_id != self.assessment_id
        ):
            raise ValidationError({"submission_batch": _("Grade batch is invalid.")})
        if (
            self.submission_batch_id
            and self.submission_batch.teacher_id != self.submitted_by_id
        ):
            raise ValidationError({"submitted_by": _("Submitted by is invalid.")})
        if self.student_id and self.assessment_id:
            enrolled = Enrollment.objects.filter(
                tenant_id=self.tenant_id,
                student_id=self.student_id,
                cohort_id=self.assessment.cohort_id,
                academic_year_id=self.assessment.academic_year_id,
                term_id=self.assessment.term_id,
                is_active=True,
            ).exists()
            if not enrolled:
                raise ValidationError(
                    {"student": _("Grade record student is invalid.")}
                )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"GradeRecord {self.pk}"


class GradeCorrectionRequest(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="grade_correction_requests",
    )
    grade_record = models.ForeignKey(
        GradeRecord,
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grade_correction_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_grade_corrections",
    )
    reason = models.TextField()
    old_state_hash = models.CharField(max_length=96)
    proposed_raw_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    proposed_remarks = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["tenant", "status"], name="grading_corr_status_idx"),
            models.Index(
                fields=["grade_record", "status"],
                name="grading_corr_record_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.tenant_id and self.grade_record_id:
            if self.grade_record.tenant_id != self.tenant_id:
                raise ValidationError({"tenant": _("Correction tenant is invalid.")})
        if not self.reason.strip():
            raise ValidationError({"reason": _("Correction reason is required.")})
        if not self.old_state_hash.strip():
            raise ValidationError({"old_state_hash": _("Old state hash is required.")})
        if self.proposed_raw_score is not None:
            validate_score_bounds(
                score=self.proposed_raw_score,
                max_score=self.grade_record.assessment.max_score,
            )
        if self.reviewed_by_id and self.reviewed_by_id == self.requested_by_id:
            raise ValidationError({"reviewed_by": _("Reviewer is invalid.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"GradeCorrectionRequest {self.pk}"
