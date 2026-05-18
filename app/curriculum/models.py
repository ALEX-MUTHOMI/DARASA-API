from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from academics.models import GradeLevel, LearningArea
from curriculum.algorithms.artifact_validator import (
    validate_artifact_file_name,
    validate_artifact_metadata,
)
from curriculum.algorithms.authority_registry import validate_authority_domains
from curriculum.algorithms.authority_normalizer import normalize_authority_code
from curriculum.algorithms.pii_guard import validate_governance_text
from curriculum.algorithms.source_url_validator import validate_source_url
from tenant.models import School, TimeStampedModel


code_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
    message=_("Codes must be lowercase alphanumeric slugs."),
)


def _normalize_code(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValidationError({field_name: _("This field is required.")})


def _validate_optional_governance_text(value: str) -> str:
    text = str(value or "").strip()
    if text:
        validate_governance_text(text)
    return text


class CurriculumSourceDocument(TimeStampedModel):
    class SourceAuthority(models.TextChoices):
        KICD = "kicd", _("Kenya Institute of Curriculum Development")
        MINISTRY_OF_EDUCATION = "ministry_of_education", _("Ministry of Education")
        PROJECT_OFFICIAL = "project_official", _("Project-provided official source")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authority = models.ForeignKey(
        "CurriculumAuthority",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_documents",
    )
    source_authority = models.SlugField(
        max_length=64,
    )
    title = models.CharField(max_length=255)
    document_code = models.CharField(max_length=128)
    source_url = models.URLField(max_length=500, blank=True)
    document_version_label = models.CharField(max_length=128)
    publication_date = models.DateField(null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum source document")
        verbose_name_plural = _("Curriculum source documents")
        constraints = [
            models.UniqueConstraint(
                fields=["source_authority", "document_code", "document_version_label"],
                name="curriculum_source_document_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["source_authority", "is_active"],
                name="curr_source_authority_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.source_authority, "source_authority")
        _require_text(self.title, "title")
        _require_text(self.document_code, "document_code")
        _require_text(self.document_version_label, "document_version_label")
        validate_governance_text(self.title)
        validate_governance_text(self.document_version_label)
        self.title = self.title.strip()
        self.document_code = self.document_code.strip()
        self.document_version_label = self.document_version_label.strip()
        if self.checksum:
            self.checksum = self.checksum.strip()
        if self.authority_id:
            if not self.authority.is_active or not self.authority.is_approved:
                raise ValidationError(
                    {"authority": _("Authority is not approved for source use.")}
                )
            self.source_authority = self.authority.code
            self.source_url = validate_source_url(
                self.source_url,
                allowed_domains=self.authority.allowed_domains,
            )
        elif self.source_authority not in self.SourceAuthority.values:
            raise ValidationError(
                {"source_authority": _("Source authority is not approved.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumSourceDocument {self.pk}"


class CurriculumVersion(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_document = models.ForeignKey(
        CurriculumSourceDocument,
        on_delete=models.PROTECT,
        related_name="curriculum_versions",
    )
    version_label = models.CharField(max_length=128)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum version")
        verbose_name_plural = _("Curriculum versions")
        constraints = [
            models.UniqueConstraint(
                fields=["source_document", "version_label"],
                name="curriculum_version_source_label_unique",
            ),
            models.UniqueConstraint(
                fields=["source_document"],
                condition=Q(is_active=True),
                name="curriculum_one_active_version_per_source",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "effective_from"], name="curr_ver_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.version_label, "version_label")
        validate_governance_text(self.version_label)
        self.version_label = self.version_label.strip()
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError(
                {"effective_to": _("End date must follow start date.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumVersion {self.pk}"


class CurriculumStage(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum stage")
        verbose_name_plural = _("Curriculum stages")
        indexes = [
            models.Index(fields=["code", "is_active"], name="curr_stage_code_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.code, "code")
        _require_text(self.name, "name")
        self.code = _normalize_code(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class CurriculumGradeMapping(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        related_name="curriculum_grade_mappings",
    )
    curriculum_stage = models.ForeignKey(
        CurriculumStage,
        on_delete=models.PROTECT,
        related_name="grade_mappings",
    )
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="grade_mappings",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum grade mapping")
        verbose_name_plural = _("Curriculum grade mappings")
        constraints = [
            models.UniqueConstraint(
                fields=["grade_level", "curriculum_version"],
                condition=Q(is_active=True),
                name="curriculum_active_grade_mapping_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["curriculum_version", "grade_level"],
                name="curr_grade_version_idx",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumLearningArea(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="curriculum_learning_areas",
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        related_name="curriculum_learning_areas",
    )
    learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.PROTECT,
        related_name="curriculum_mappings",
    )
    official_name = models.CharField(max_length=150)
    official_code = models.SlugField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum learning area")
        verbose_name_plural = _("Curriculum learning areas")
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_version", "grade_level", "learning_area"],
                name="curriculum_learning_area_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["curriculum_version", "grade_level", "is_active"],
                name="curr_learning_area_lookup_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.official_name, "official_name")
        self.official_name = self.official_name.strip()
        if self.official_code:
            self.official_code = _normalize_code(self.official_code)
        if self.learning_area_id and self.grade_level_id:
            if self.learning_area.grade_level_id != self.grade_level_id:
                raise ValidationError(
                    {"learning_area": _("Learning area grade is invalid.")}
                )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class Strand(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_learning_area = models.ForeignKey(
        CurriculumLearningArea,
        on_delete=models.CASCADE,
        related_name="strands",
    )
    code = models.SlugField(max_length=64, blank=True)
    title = models.CharField(max_length=255)
    sequence_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Strand")
        verbose_name_plural = _("Strands")
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_learning_area", "title"],
                name="curriculum_strand_title_unique",
            ),
            models.UniqueConstraint(
                fields=["curriculum_learning_area", "code"],
                condition=~Q(code=""),
                name="curriculum_strand_code_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["curriculum_learning_area", "sequence_order"],
                name="curr_strand_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.title, "title")
        self.title = self.title.strip()
        if self.code:
            self.code = _normalize_code(self.code)

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class SubStrand(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strand = models.ForeignKey(
        Strand,
        on_delete=models.CASCADE,
        related_name="sub_strands",
    )
    code = models.SlugField(max_length=64, blank=True)
    title = models.CharField(max_length=255)
    sequence_order = models.PositiveIntegerField(default=1)
    suggested_time_allocation = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Sub-strand")
        verbose_name_plural = _("Sub-strands")
        constraints = [
            models.UniqueConstraint(
                fields=["strand", "title"],
                name="curriculum_substrand_title_unique",
            ),
            models.UniqueConstraint(
                fields=["strand", "code"],
                condition=~Q(code=""),
                name="curriculum_substrand_code_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["strand", "sequence_order"],
                name="curr_substrand_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.title, "title")
        self.title = self.title.strip()
        if self.code:
            self.code = _normalize_code(self.code)

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class SpecificLearningOutcome(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.CASCADE,
        related_name="learning_outcomes",
    )
    text = models.TextField()
    sequence_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Specific learning outcome")
        verbose_name_plural = _("Specific learning outcomes")
        indexes = [
            models.Index(
                fields=["sub_strand", "sequence_order"],
                name="curr_outcome_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.text, "text")
        self.text = self.text.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class LearningExperience(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_experiences",
    )
    learning_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_experiences",
    )
    text = models.TextField()
    sequence_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Learning experience")
        verbose_name_plural = _("Learning experiences")
        indexes = [
            models.Index(
                fields=["learning_outcome", "sequence_order"],
                name="curr_experience_outcome_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.text, "text")
        self.text = self.text.strip()
        if bool(self.sub_strand_id) == bool(self.learning_outcome_id):
            raise ValidationError(
                {"learning_outcome": _("Set exactly one curriculum parent.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class KeyInquiryQuestion(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.CASCADE,
        related_name="key_inquiry_questions",
    )
    question_text = models.TextField()
    sequence_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Key inquiry question")
        verbose_name_plural = _("Key inquiry questions")
        indexes = [
            models.Index(
                fields=["sub_strand", "sequence_order"],
                name="curr_inquiry_order_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.question_text, "question_text")
        self.question_text = self.question_text.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CoreCompetency(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def clean(self) -> None:
        super().clean()
        _require_text(self.code, "code")
        _require_text(self.name, "name")
        self.code = _normalize_code(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumValue(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def clean(self) -> None:
        super().clean()
        _require_text(self.code, "code")
        _require_text(self.name, "name")
        self.code = _normalize_code(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class PertinentContemporaryIssue(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def clean(self) -> None:
        super().clean()
        _require_text(self.code, "code")
        _require_text(self.name, "name")
        self.code = _normalize_code(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class OutcomeCompetencyLink(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.CASCADE,
        related_name="competency_links",
    )
    competency = models.ForeignKey(
        CoreCompetency,
        on_delete=models.PROTECT,
        related_name="outcome_links",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["learning_outcome", "competency"],
                name="curr_outcome_competency_unique",
            ),
        ]


class OutcomeValueLink(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.CASCADE,
        related_name="value_links",
    )
    value = models.ForeignKey(
        CurriculumValue,
        on_delete=models.PROTECT,
        related_name="outcome_links",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["learning_outcome", "value"],
                name="curr_outcome_value_unique",
            ),
        ]


class OutcomePCILink(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.CASCADE,
        related_name="pci_links",
    )
    pci = models.ForeignKey(
        PertinentContemporaryIssue,
        on_delete=models.PROTECT,
        related_name="outcome_links",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["learning_outcome", "pci"],
                name="curr_outcome_pci_unique",
            ),
        ]


class AssessmentRubricFoundation(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rubric_foundations",
    )
    learning_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rubric_foundations",
    )
    level_code = models.SlugField(max_length=64, validators=[code_validator])
    level_label = models.CharField(max_length=128)
    descriptor = models.TextField()
    sequence_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Assessment rubric foundation")
        verbose_name_plural = _("Assessment rubric foundations")
        constraints = [
            models.UniqueConstraint(
                fields=["learning_outcome", "level_code"],
                condition=Q(learning_outcome__isnull=False),
                name="curr_rubric_outcome_level_unique",
            ),
            models.UniqueConstraint(
                fields=["sub_strand", "level_code"],
                condition=Q(sub_strand__isnull=False),
                name="curr_rubric_substrand_level_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["learning_outcome", "sequence_order"],
                name="curr_rubric_outcome_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.level_code, "level_code")
        _require_text(self.level_label, "level_label")
        _require_text(self.descriptor, "descriptor")
        self.level_code = _normalize_code(self.level_code)
        self.level_label = self.level_label.strip()
        self.descriptor = self.descriptor.strip()
        if bool(self.sub_strand_id) == bool(self.learning_outcome_id):
            raise ValidationError(
                {"learning_outcome": _("Set exactly one curriculum parent.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumAuthority(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=255)
    official_website = models.URLField(max_length=500)
    allowed_domains = models.JSONField(default=list)
    is_active = models.BooleanField(default=True, db_index=True)
    is_approved = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum authority")
        verbose_name_plural = _("Curriculum authorities")
        indexes = [
            models.Index(
                fields=["code", "is_active", "is_approved"],
                name="curr_authority_lookup_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = normalize_authority_code(self.code)
        _require_text(self.name, "name")
        self.name = self.name.strip()
        if not isinstance(self.allowed_domains, list) or not self.allowed_domains:
            raise ValidationError(
                {"allowed_domains": _("Allowed domains are required.")}
            )
        self.allowed_domains = validate_authority_domains(
            authority_code=self.code,
            allowed_domains=self.allowed_domains,
        )
        self.official_website = validate_source_url(
            self.official_website,
            allowed_domains=self.allowed_domains,
        )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class SourceArtifact(TimeStampedModel):
    class CaptureMethod(models.TextChoices):
        MANUAL_UPLOAD = "manual_upload", _("Manual upload")
        APPROVED_REFERENCE = "approved_reference", _("Approved reference")

    class QuarantineStatus(models.TextChoices):
        QUARANTINED = "quarantined", _("Quarantined")
        TRUSTED = "trusted", _("Trusted")
        REJECTED = "rejected", _("Rejected")

    class ScanStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CLEAN = "clean", _("Clean")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_document = models.ForeignKey(
        CurriculumSourceDocument,
        on_delete=models.PROTECT,
        related_name="artifacts",
    )
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128)
    file_size = models.PositiveIntegerField()
    checksum_algorithm = models.CharField(max_length=32, default="sha256")
    checksum = models.CharField(max_length=96)
    capture_method = models.CharField(
        max_length=32,
        choices=CaptureMethod.choices,
    )
    quarantine_status = models.CharField(
        max_length=32,
        choices=QuarantineStatus.choices,
        default=QuarantineStatus.QUARANTINED,
        db_index=True,
    )
    scan_status = models.CharField(
        max_length=32,
        choices=ScanStatus.choices,
        default=ScanStatus.PENDING,
        db_index=True,
    )
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Source artifact")
        verbose_name_plural = _("Source artifacts")
        constraints = [
            models.UniqueConstraint(
                fields=["source_document", "checksum"],
                name="curr_artifact_source_checksum_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["quarantine_status", "scan_status"],
                name="curr_artifact_quarantine_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.file_name, "file_name")
        self.file_name = validate_artifact_file_name(self.file_name)
        self.content_type = self.content_type.strip().lower()
        self.checksum_algorithm = self.checksum_algorithm.strip().lower()
        self.checksum = self.checksum.strip().lower()
        if self.checksum_algorithm != "sha256":
            raise ValidationError(
                {"checksum_algorithm": _("Only SHA-256 checksums are supported.")}
            )
        validate_artifact_metadata(
            file_size=self.file_size,
            content_type=self.content_type,
            checksum=self.checksum,
        )
        if (
            self.quarantine_status == self.QuarantineStatus.TRUSTED
            and self.scan_status != self.ScanStatus.CLEAN
        ):
            raise ValidationError(
                {"quarantine_status": _("Trusted artifacts must be scan-clean.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SourceArtifact {self.pk}"


class CurriculumChangeSet(TimeStampedModel):
    class ChangeType(models.TextChoices):
        NEW_VERSION = "new_version", _("New version")
        SOURCE_CHANGED = "source_changed", _("Source changed")
        CORRECTION = "correction", _("Correction")

    class Status(models.TextChoices):
        DETECTED = "detected", _("Detected")
        QUARANTINED = "quarantined", _("Quarantined")
        UNDER_REVIEW = "under_review", _("Under review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        PUBLISHED = "published", _("Published")
        SUPERSEDED = "superseded", _("Superseded")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_document = models.ForeignKey(
        CurriculumSourceDocument,
        on_delete=models.PROTECT,
        related_name="change_sets",
    )
    old_curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="old_change_sets",
    )
    proposed_curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="proposed_change_sets",
    )
    change_type = models.CharField(max_length=32, choices=ChangeType.choices)
    summary = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DETECTED,
        db_index=True,
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_curriculum_change_sets",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum change set")
        verbose_name_plural = _("Curriculum change sets")
        indexes = [
            models.Index(
                fields=["status", "detected_at"],
                name="curr_change_status_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.summary)
        self.summary = self.summary.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumChangeSet {self.pk}"


class CurriculumPublication(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="publications",
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    publication_notes = models.TextField()
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_curriculum_publications",
    )
    published_at = models.DateTimeField(auto_now_add=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_publications",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum publication")
        verbose_name_plural = _("Curriculum publications")
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_version"],
                condition=Q(is_active=True),
                name="curriculum_one_active_publication_per_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["is_active", "effective_from"],
                name="curr_publication_active_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.publication_notes)
        self.publication_notes = self.publication_notes.strip()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError(
                {"effective_to": _("Publication end date must follow start date.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumPublication {self.pk}"


class SchoolCurriculumAdoption(TimeStampedModel):
    """Tenant-specific adoption state for a published curriculum version.

    A national publication does not activate curriculum for every school.  This
    record is the explicit school-level control-plane contract that grading and
    later reporting dependencies can trust.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        ACTIVE = "active", _("Active")
        SUPERSEDED = "superseded", _("Superseded")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        ROLLED_BACK = "rolled_back", _("Rolled back")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_adoptions",
    )
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="school_adoptions",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    adopted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_curriculum_adoptions",
    )
    adopted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("School curriculum adoption")
        verbose_name_plural = _("School curriculum adoptions")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "curriculum_version"],
                condition=Q(status__in=["scheduled", "active"]),
                name="curr_adopt_active_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status", "effective_from"],
                name="curr_adopt_tenant_status_idx",
            ),
            models.Index(
                fields=["curriculum_version", "status"],
                name="curr_adopt_version_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.notes:
            validate_governance_text(self.notes)
            self.notes = self.notes.strip()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError(
                {"effective_to": _("Adoption end date must follow start date.")}
            )
        if self.status in {self.Status.SCHEDULED, self.Status.ACTIVE}:
            if not self.curriculum_version.is_active:
                raise ValidationError(
                    {"curriculum_version": _("Curriculum version is inactive.")}
                )
            if not CurriculumPublication.objects.filter(
                curriculum_version=self.curriculum_version,
                is_active=True,
            ).exists():
                raise ValidationError(
                    {"curriculum_version": _("Published curriculum is required.")}
                )
            if CurriculumVersionWithdrawal.objects.filter(
                curriculum_version=self.curriculum_version,
                status=CurriculumVersionWithdrawal.Status.WITHDRAWN,
            ).exists():
                raise ValidationError(
                    {"curriculum_version": _("Withdrawn curriculum cannot be adopted.")}
                )
        if self.adopted_by_id and not self.adopted_by.is_active:
            raise ValidationError({"adopted_by": _("Adoption actor must be active.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SchoolCurriculumAdoption {self.pk}"


class CurriculumVersionWithdrawal(TimeStampedModel):
    """Auditable withdrawal marker that blocks new adoption.

    Withdrawal records do not rewrite historical grading or compilation state.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="withdrawals",
    )
    replacement_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="replacement_for_withdrawals",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )
    reason = models.TextField()
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="withdrawn_curriculum_versions",
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum version withdrawal")
        verbose_name_plural = _("Curriculum version withdrawals")
        indexes = [
            models.Index(
                fields=["curriculum_version", "status"],
                name="curr_withdraw_version_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.reason)
        self.reason = self.reason.strip()
        if self.replacement_version_id == self.curriculum_version_id:
            raise ValidationError(
                {"replacement_version": _("Replacement version must differ.")}
            )
        if self.withdrawn_by_id and not self.withdrawn_by.is_active:
            raise ValidationError({"withdrawn_by": _("Withdrawal actor is inactive.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumVersionWithdrawal {self.pk}"


class CurriculumRollbackPlan(TimeStampedModel):
    """Controlled rollback plan for tenant-scoped adoption changes.

    Rollback planning records intended operational changes.  It deliberately
    does not mutate assessments, grade records, or compiled snapshots.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        APPROVED = "approved", _("Approved")
        EXECUTED = "executed", _("Executed")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_rollback_plans",
    )
    withdrawn_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="rollback_plans_as_withdrawn",
    )
    target_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rollback_plans_as_target",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )
    reason = models.TextField()
    planned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planned_curriculum_rollbacks",
    )
    planned_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    affected_assessment_count = models.PositiveIntegerField(default=0)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum rollback plan")
        verbose_name_plural = _("Curriculum rollback plans")
        indexes = [
            models.Index(
                fields=["tenant", "status", "planned_at"],
                name="curr_rollback_tenant_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.reason)
        self.reason = self.reason.strip()
        if self.target_version_id == self.withdrawn_version_id:
            raise ValidationError({"target_version": _("Target version must differ.")})
        if self.planned_by_id and not self.planned_by.is_active:
            raise ValidationError({"planned_by": _("Planner must be active.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumRollbackPlan {self.pk}"


class CurriculumNoticeBatchRun(TimeStampedModel):
    """Batchable notice issuance record for national-scale CCT operations."""

    class NoticeType(models.TextChoices):
        PRINCIPAL_EVIDENCE = "principal_evidence", _("Principal evidence")
        TEACHER_READINESS = "teacher_readiness", _("Teacher readiness")
        ADOPTION = "adoption", _("Adoption")
        WITHDRAWAL = "withdrawal", _("Withdrawal")

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="curriculum_notice_batches",
    )
    curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notice_batch_runs",
    )
    notice_type = models.CharField(max_length=32, choices=NoticeType.choices)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )
    total_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_curriculum_notice_batches",
    )
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum notice batch run")
        verbose_name_plural = _("Curriculum notice batch runs")
        indexes = [
            models.Index(
                fields=["status", "notice_type", "created_at"],
                name="curr_notice_batch_idx",
            ),
            models.Index(
                fields=["tenant", "status"],
                name="curr_notice_tenant_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.processed_count > self.total_count:
            raise ValidationError(
                {"processed_count": _("Processed count cannot exceed total count.")}
            )
        if self.notes:
            validate_governance_text(self.notes)
            self.notes = self.notes.strip()
        if self.created_by_id and not self.created_by.is_active:
            raise ValidationError({"created_by": _("Batch creator must be active.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumNoticeBatchRun {self.pk}"


class CurriculumEvidenceSubmission(TimeStampedModel):
    """Tenant-owned evidence metadata, not curriculum truth."""

    class EvidenceType(models.TextChoices):
        CURRICULUM_UPDATE = "curriculum_update", _("Curriculum update")
        ROLLBACK = "rollback", _("Rollback")
        WITHDRAWAL = "withdrawal", _("Withdrawal")

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        QUARANTINED = "quarantined", _("Quarantined")
        DUPLICATE_ATTACHED = "duplicate_attached", _("Duplicate attached")
        UNDER_VERIFICATION = "under_verification", _("Under verification")
        VERIFICATION_REPORTED = "verification_reported", _("Verification reported")
        ESCALATED = "escalated", _("Escalated")
        REJECTED = "rejected", _("Rejected")
        GOVERNANCE_READY = "governance_ready", _("Governance ready")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_evidence_submissions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_curriculum_evidence",
    )
    submitter_role = models.CharField(max_length=64)
    evidence_type = models.CharField(
        max_length=32,
        choices=EvidenceType.choices,
        default=EvidenceType.CURRICULUM_UPDATE,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUARANTINED,
        db_index=True,
    )
    storage_reference = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128)
    size_bytes = models.PositiveIntegerField()
    file_checksum = models.CharField(max_length=96)
    evidence_fingerprint = models.CharField(max_length=96, db_index=True)
    duplicate_cluster_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="duplicate_submissions",
    )
    claimed_authority = models.CharField(max_length=128, blank=True)
    claimed_source_reference = models.CharField(max_length=255, blank=True)
    claimed_source_url = models.URLField(max_length=500, blank=True)
    claimed_reference_number = models.CharField(max_length=128, blank=True)
    claimed_publication_number = models.CharField(max_length=128, blank=True)
    claimed_publication_date = models.DateField(null=True, blank=True)
    claimed_effective_date = models.DateField(null=True, blank=True)
    claimed_scope = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum evidence submission")
        verbose_name_plural = _("Curriculum evidence submissions")
        indexes = [
            models.Index(
                fields=["tenant", "status", "created_at"],
                name="curr_evid_tenant_status_idx",
            ),
            models.Index(
                fields=["evidence_fingerprint", "status"],
                name="curr_evid_fingerprint_idx",
            ),
            models.Index(
                fields=["duplicate_cluster_id", "created_at"],
                name="curr_evid_cluster_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.submitter_role = _validate_optional_governance_text(
            self.submitter_role
        )
        self.file_name = _validate_optional_governance_text(self.file_name)
        self.claimed_authority = _validate_optional_governance_text(
            self.claimed_authority
        )
        self.claimed_source_reference = _validate_optional_governance_text(
            self.claimed_source_reference
        )
        self.claimed_reference_number = _validate_optional_governance_text(
            self.claimed_reference_number
        )
        self.claimed_publication_number = _validate_optional_governance_text(
            self.claimed_publication_number
        )
        if self.duplicate_of_id and self.duplicate_of_id == self.id:
            raise ValidationError(
                {"duplicate_of": _("Duplicate cannot reference self.")}
            )
        if self.duplicate_of_id and self.tenant_id:
            if self.duplicate_of.tenant_id != self.tenant_id:
                raise ValidationError(
                    {"duplicate_of": _("Duplicate tenant mismatch.")}
                )
        if self.submitted_by_id and not self.submitted_by.is_active:
            raise ValidationError({"submitted_by": _("Submitter must be active.")})
        if self.duplicate_of_id:
            self.duplicate_cluster_id = self.duplicate_of.duplicate_cluster_id

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumEvidenceSubmission {self.pk}"


class CurriculumVerificationReport(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        COMPLETE = "complete", _("Complete")
        NEEDS_MORE_EVIDENCE = "needs_more_evidence", _("Needs more evidence")
        AWAITING_OFFICIAL_CONFIRMATION = (
            "awaiting_official_confirmation",
            _("Awaiting official confirmation"),
        )
        REJECTED = "rejected", _("Rejected")
        ESCALATED = "escalated", _("Escalated")

    class ConfidenceLevel(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")
        REJECTED = "rejected", _("Rejected")
        NEEDS_GOVERNANCE_REVIEW = (
            "needs_governance_review",
            _("Needs governance review"),
        )

    class RecommendedAction(models.TextChoices):
        KEEP_QUARANTINED = "keep_quarantined", _("Keep quarantined")
        REQUEST_MORE_EVIDENCE = "request_more_evidence", _("Request more evidence")
        AWAIT_OFFICIAL_CONFIRMATION = (
            "await_official_confirmation",
            _("Await official confirmation"),
        )
        ESCALATE_TO_GOVERNANCE = (
            "escalate_to_governance",
            _("Escalate to governance"),
        )
        READY_FOR_GOVERNANCE_REVIEW = (
            "ready_for_governance_review",
            _("Ready for governance review"),
        )
        REJECT = "reject", _("Reject")

    class OfficialSourceMatch(models.TextChoices):
        UNKNOWN = "unknown", _("Unknown")
        MATCHED = "matched", _("Matched")
        UNMATCHED = "unmatched", _("Unmatched")
        AWAITING_CONFIRMATION = (
            "awaiting_confirmation",
            _("Awaiting confirmation"),
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_verification_reports",
    )
    evidence_submission = models.OneToOneField(
        CurriculumEvidenceSubmission,
        on_delete=models.PROTECT,
        related_name="verification_report",
    )
    candidate_id = models.UUIDField(db_index=True)
    fingerprint = models.CharField(max_length=96)
    source_classification = models.CharField(max_length=64, default="school_evidence")
    claimed_authority = models.CharField(max_length=128, blank=True)
    claimed_source_reference = models.CharField(max_length=255, blank=True)
    reference_number_detected = models.BooleanField(default=False)
    reference_number_value = models.CharField(max_length=128, blank=True)
    publication_number_detected = models.BooleanField(default=False)
    publication_number_value = models.CharField(max_length=128, blank=True)
    publication_date_detected = models.BooleanField(default=False)
    effective_date_detected = models.BooleanField(default=False)
    stamp_signal = models.BooleanField(default=False)
    signature_signal = models.BooleanField(default=False)
    template_signal = models.BooleanField(default=False)
    duplicate_signal_count = models.PositiveIntegerField(default=0)
    official_source_match_status = models.CharField(
        max_length=32,
        choices=OfficialSourceMatch.choices,
        default=OfficialSourceMatch.UNKNOWN,
    )
    scope_guess = models.JSONField(default=dict, blank=True)
    confidence_score = models.PositiveSmallIntegerField(default=0)
    confidence_level = models.CharField(
        max_length=32,
        choices=ConfidenceLevel.choices,
        default=ConfidenceLevel.LOW,
    )
    risk_flags = models.JSONField(default=list, blank=True)
    missing_evidence = models.JSONField(default=list, blank=True)
    recommended_next_action = models.CharField(
        max_length=48,
        choices=RecommendedAction.choices,
        default=RecommendedAction.KEEP_QUARANTINED,
    )
    sla_due_at = models.DateTimeField(db_index=True)
    review_status = models.CharField(
        max_length=48,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_curriculum_verification_reports",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum verification report")
        verbose_name_plural = _("Curriculum verification reports")
        indexes = [
            models.Index(
                fields=["tenant", "review_status", "sla_due_at"],
                name="curr_verify_tenant_status_idx",
            ),
            models.Index(
                fields=["candidate_id", "confidence_level"],
                name="curr_verify_candidate_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.evidence_submission_id and self.tenant_id:
            if self.evidence_submission.tenant_id != self.tenant_id:
                raise ValidationError(
                    {"tenant": _("Verification report tenant mismatch.")}
                )
        for value in [
            self.claimed_authority,
            self.claimed_source_reference,
            self.reference_number_value,
            self.publication_number_value,
        ]:
            _validate_optional_governance_text(value)
        if self.confidence_score > 100:
            raise ValidationError({"confidence_score": _("Confidence exceeds 100.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumVerificationReport {self.pk}"


class CurriculumGovernanceDecision(TimeStampedModel):
    class Decision(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED_FOR_PUBLICATION = (
            "approved_for_publication",
            _("Approved for publication"),
        )
        REJECTED = "rejected", _("Rejected")
        REQUIRES_MORE_EVIDENCE = (
            "requires_more_evidence",
            _("Requires more evidence"),
        )
        ESCALATED = "escalated", _("Escalated")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_governance_decisions",
    )
    verification_report = models.ForeignKey(
        CurriculumVerificationReport,
        on_delete=models.PROTECT,
        related_name="governance_decisions",
    )
    decision = models.CharField(
        max_length=48,
        choices=Decision.choices,
        default=Decision.PENDING,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_governance_decisions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum governance decision")
        verbose_name_plural = _("Curriculum governance decisions")
        indexes = [
            models.Index(
                fields=["tenant", "decision", "reviewed_at"],
                name="curr_gov_tenant_decision_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.verification_report_id and self.tenant_id:
            if self.verification_report.tenant_id != self.tenant_id:
                raise ValidationError({"tenant": _("Governance tenant mismatch.")})
        if self.reason:
            self.reason = _validate_optional_governance_text(self.reason)
        if self.reviewed_by_id and not self.reviewed_by.is_active:
            raise ValidationError({"reviewed_by": _("Reviewer must be active.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumGovernanceDecision {self.pk}"


class CurriculumAppImpactPlan(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        REVIEW_REQUIRED = "review_required", _("Review required")
        APPROVED = "approved", _("Approved")
        PAUSED = "paused", _("Paused")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_app_impact_plans",
    )
    verification_report = models.ForeignKey(
        CurriculumVerificationReport,
        on_delete=models.PROTECT,
        related_name="app_impact_plans",
    )
    app_domain = models.CharField(max_length=64, db_index=True)
    impact_type = models.CharField(max_length=64)
    affected_scope = models.JSONField(default=dict, blank=True)
    required_action = models.TextField()
    safe_behavior = models.TextField()
    historical_protection_rule = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum app impact plan")
        verbose_name_plural = _("Curriculum app impact plans")
        indexes = [
            models.Index(
                fields=["tenant", "app_domain", "status"],
                name="curr_app_impact_tenant_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.verification_report_id and self.tenant_id:
            if self.verification_report.tenant_id != self.tenant_id:
                raise ValidationError({"tenant": _("Impact plan tenant mismatch.")})
        self.app_domain = _validate_optional_governance_text(self.app_domain)
        self.impact_type = _validate_optional_governance_text(self.impact_type)
        validate_governance_text(self.required_action)
        validate_governance_text(self.safe_behavior)
        validate_governance_text(self.historical_protection_rule)

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumAppImpactPlan {self.pk}"


class CurriculumRollbackCandidate(TimeStampedModel):
    class Status(models.TextChoices):
        SUSPECTED = "suspected", _("Suspected")
        QUARANTINED = "quarantined", _("Quarantined")
        UNDER_REVIEW = "under_review", _("Under review")
        VERIFIED = "verified", _("Verified")
        REJECTED = "rejected", _("Rejected")
        ROLLBACK_PLANNED = "rollback_planned", _("Rollback planned")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="curriculum_rollback_candidates",
    )
    evidence_submission = models.ForeignKey(
        CurriculumEvidenceSubmission,
        on_delete=models.PROTECT,
        related_name="rollback_candidates",
    )
    verification_report = models.ForeignKey(
        CurriculumVerificationReport,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rollback_candidates",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUARANTINED,
        db_index=True,
    )
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_curriculum_rollback_candidates",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum rollback candidate")
        verbose_name_plural = _("Curriculum rollback candidates")
        indexes = [
            models.Index(
                fields=["tenant", "status", "created_at"],
                name="curr_rb_candidate_tenant_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.evidence_submission_id and self.tenant_id:
            if self.evidence_submission.tenant_id != self.tenant_id:
                raise ValidationError({"tenant": _("Rollback tenant mismatch.")})
        if self.verification_report_id and self.tenant_id:
            if self.verification_report.tenant_id != self.tenant_id:
                raise ValidationError({"tenant": _("Rollback report mismatch.")})
        validate_governance_text(self.reason)
        self.reason = self.reason.strip()
        if self.created_by_id and not self.created_by.is_active:
            raise ValidationError({"created_by": _("Creator must be active.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CurriculumRollbackCandidate {self.pk}"


class CurriculumDiff(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        UNDER_REVIEW = "under_review", _("Under review")
        REVIEWED = "reviewed", _("Reviewed")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    old_curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="old_curriculum_diffs",
    )
    new_curriculum_version = models.ForeignKey(
        CurriculumVersion,
        on_delete=models.PROTECT,
        related_name="new_curriculum_diffs",
    )
    source_change_set = models.ForeignKey(
        CurriculumChangeSet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_diffs",
    )
    diff_status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    summary = models.TextField()
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_curriculum_diffs",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum diff")
        verbose_name_plural = _("Curriculum diffs")
        constraints = [
            models.UniqueConstraint(
                fields=["old_curriculum_version", "new_curriculum_version"],
                name="curriculum_diff_version_pair_unique",
            ),
            models.CheckConstraint(
                condition=~Q(
                    old_curriculum_version=models.F("new_curriculum_version")
                ),
                name="curriculum_diff_versions_differ",
            ),
        ]
        indexes = [
            models.Index(
                fields=["diff_status", "created_at"],
                name="curr_diff_status_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.summary)
        self.summary = self.summary.strip()
        if (
            self.old_curriculum_version_id
            and self.new_curriculum_version_id
            and self.old_curriculum_version_id == self.new_curriculum_version_id
        ):
            raise ValidationError(
                {"new_curriculum_version": _("Diff versions must be different.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumDiffItem(TimeStampedModel):
    class ChangeType(models.TextChoices):
        ADDED = "added", _("Added")
        REMOVED = "removed", _("Removed")
        RENAMED = "renamed", _("Renamed")
        MOVED = "moved", _("Moved")
        UPDATED = "updated", _("Updated")
        RETIRED = "retired", _("Retired")
        REACTIVATED = "reactivated", _("Reactivated")
        ASSESSMENT_CRITERIA_CHANGED = (
            "assessment_criteria_changed",
            _("Assessment criteria changed"),
        )
        EFFECTIVE_DATE_CHANGED = "effective_date_changed", _("Effective date changed")

    class EntityType(models.TextChoices):
        CURRICULUM_VERSION = "curriculum_version", _("Curriculum version")
        GRADE_LEVEL = "grade_level", _("Grade level")
        PATHWAY = "pathway", _("Pathway")
        LEARNING_AREA = "learning_area", _("Learning area")
        STRAND = "strand", _("Strand")
        SUB_STRAND = "sub_strand", _("Sub-strand")
        OUTCOME = "outcome", _("Outcome")
        COMPETENCY = "competency", _("Competency")
        VALUE = "value", _("Value")
        PCI = "pci", _("PCI")
        RUBRIC_FOUNDATION = "rubric_foundation", _("Rubric foundation")
        ASSESSMENT_GUIDANCE = "assessment_guidance", _("Assessment guidance")
        TEACHER_TRAINING_NOTICE = (
            "teacher_training_notice",
            _("Teacher training notice"),
        )
        CIRCULAR = "circular", _("Circular")

    class Severity(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_diff = models.ForeignKey(
        CurriculumDiff,
        on_delete=models.CASCADE,
        related_name="items",
    )
    change_type = models.CharField(max_length=48, choices=ChangeType.choices)
    entity_type = models.CharField(max_length=64, choices=EntityType.choices)
    entity_identifier = models.CharField(max_length=255)
    old_value_fingerprint = models.CharField(max_length=96, blank=True)
    new_value_fingerprint = models.CharField(max_length=96, blank=True)
    summary = models.TextField()
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    requires_review = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum diff item")
        verbose_name_plural = _("Curriculum diff items")
        indexes = [
            models.Index(
                fields=["curriculum_diff", "requires_review"],
                name="curr_diff_item_review_idx",
            ),
            models.Index(
                fields=["entity_type", "change_type"],
                name="curr_diff_item_type_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.entity_identifier, "entity_identifier")
        validate_governance_text(self.summary)
        self.entity_identifier = self.entity_identifier.strip()
        self.summary = self.summary.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class CurriculumImpact(TimeStampedModel):
    class Category(models.TextChoices):
        SENIOR_SCHOOL_CURRICULUM = (
            "senior_school_curriculum",
            _("Senior School curriculum"),
        )
        JUNIOR_TO_SENIOR_TRANSITION = (
            "junior_to_senior_transition",
            _("Junior-to-Senior transition"),
        )
        ASSESSMENT_CRITERIA = "assessment_criteria", _("Assessment criteria")
        TEACHER_READINESS = "teacher_readiness", _("Teacher readiness")
        SCHEME_REVIEW_REQUIRED = "scheme_review_required", _("Scheme review required")
        GRADING_DEPENDENCY_FUTURE = (
            "grading_dependency_future",
            _("Future grading dependency"),
        )
        REPORT_DEPENDENCY_FUTURE = (
            "report_dependency_future",
            _("Future report dependency"),
        )
        LESSON_ASSISTANT_DEPENDENCY_FUTURE = (
            "lesson_assistant_dependency_future",
            _("Future lesson assistant dependency"),
        )
        SCHOOL_ADOPTION_REQUIRED = (
            "school_adoption_required",
            _("School adoption required"),
        )

    class Severity(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum_diff = models.ForeignKey(
        CurriculumDiff,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="impacts",
    )
    diff_item = models.ForeignKey(
        CurriculumDiffItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="impacts",
    )
    affected_stage = models.CharField(max_length=128)
    affected_grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    affected_pathway = models.CharField(max_length=128, blank=True)
    affected_learning_area = models.ForeignKey(
        CurriculumLearningArea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    affected_strand = models.ForeignKey(
        Strand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    affected_sub_strand = models.ForeignKey(
        SubStrand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    affected_outcome = models.ForeignKey(
        SpecificLearningOutcome,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    affected_rubric_foundation = models.ForeignKey(
        AssessmentRubricFoundation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="curriculum_impacts",
    )
    impact_category = models.CharField(max_length=64, choices=Category.choices)
    impact_severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    action_required = models.TextField()

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Curriculum impact")
        verbose_name_plural = _("Curriculum impacts")
        indexes = [
            models.Index(
                fields=["impact_category", "impact_severity"],
                name="curr_impact_cat_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.affected_stage, "affected_stage")
        validate_governance_text(self.action_required)
        if not self.curriculum_diff_id and not self.diff_item_id:
            raise ValidationError(
                {"curriculum_diff": _("A diff or diff item is required.")}
            )
        self.affected_stage = self.affected_stage.strip()
        self.action_required = self.action_required.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class RegulatoryNotice(TimeStampedModel):
    class NoticeType(models.TextChoices):
        MOE_CIRCULAR = "moe_circular", _("MoE circular")
        KICD_CURRICULUM_UPDATE = (
            "kicd_curriculum_update",
            _("KICD curriculum update"),
        )
        KNEC_ASSESSMENT_GUIDANCE = (
            "knec_assessment_guidance",
            _("KNEC assessment guidance"),
        )
        TSC_TEACHER_UPDATE = "tsc_teacher_update", _("TSC teacher update")
        TEACHER_TRAINING_NOTICE = (
            "teacher_training_notice",
            _("Teacher training notice"),
        )
        SENIOR_SCHOOL_TRANSITION_NOTICE = (
            "senior_school_transition_notice",
            _("Senior School transition notice"),
        )
        PATHWAY_GUIDANCE = "pathway_guidance", _("Pathway guidance")
        IMPLEMENTATION_GUIDANCE = (
            "implementation_guidance",
            _("Implementation guidance"),
        )

    class ReviewStatus(models.TextChoices):
        PENDING_REVIEW = "pending_review", _("Pending review")
        VERIFIED = "verified", _("Verified")
        REJECTED = "rejected", _("Rejected")

    class NoticeStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authority = models.ForeignKey(
        CurriculumAuthority,
        on_delete=models.PROTECT,
        related_name="regulatory_notices",
    )
    source_document = models.ForeignKey(
        CurriculumSourceDocument,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="regulatory_notices",
    )
    source_artifact = models.ForeignKey(
        SourceArtifact,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="regulatory_notices",
    )
    notice_type = models.CharField(max_length=48, choices=NoticeType.choices)
    title = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=128, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    summary = models.TextField()
    review_status = models.CharField(
        max_length=32,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING_REVIEW,
        db_index=True,
    )
    notice_status = models.CharField(
        max_length=32,
        choices=NoticeStatus.choices,
        default=NoticeStatus.DRAFT,
        db_index=True,
    )
    affects_senior_school = models.BooleanField(default=False, db_index=True)
    affects_junior_to_senior_transition = models.BooleanField(
        default=False,
        db_index=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_regulatory_notices",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Regulatory notice")
        verbose_name_plural = _("Regulatory notices")
        constraints = [
            models.UniqueConstraint(
                fields=["authority", "reference_number"],
                condition=~Q(reference_number=""),
                name="curr_reg_notice_reference_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["review_status", "notice_status"],
                name="curr_notice_status_idx",
            ),
            models.Index(
                fields=["affects_senior_school"],
                name="curr_notice_senior_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.title, "title")
        validate_governance_text(self.title)
        validate_governance_text(self.summary)
        self.title = self.title.strip()
        self.reference_number = self.reference_number.strip()
        self.summary = self.summary.strip()
        if not self.authority.is_active or not self.authority.is_approved:
            raise ValidationError({"authority": _("Authority is not approved.")})
        if self.review_status == self.ReviewStatus.VERIFIED:
            if not self.source_document_id and not self.source_artifact_id:
                raise ValidationError(
                    {"review_status": _("Verified notices require source evidence.")}
                )
            if self.reviewed_by_id and not self.reviewed_by.is_active:
                raise ValidationError(
                    {"reviewed_by": _("Reviewer must be active.")}
                )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class RegulatoryImpact(TimeStampedModel):
    class Category(models.TextChoices):
        SENIOR_SCHOOL_PATHWAY = "senior_school_pathway", _("Senior School pathway")
        SENIOR_SCHOOL_READINESS = (
            "senior_school_readiness",
            _("Senior School readiness"),
        )
        TEACHER_TRAINING = "teacher_training", _("Teacher training")
        ASSESSMENT_POLICY = "assessment_policy", _("Assessment policy")
        SCHOOL_INFRASTRUCTURE_READINESS = (
            "school_infrastructure_readiness",
            _("School infrastructure readiness"),
        )
        TIMETABLE_OR_TERM_GUIDANCE = (
            "timetable_or_term_guidance",
            _("Timetable or term guidance"),
        )
        CURRICULUM_IMPLEMENTATION = (
            "curriculum_implementation",
            _("Curriculum implementation"),
        )
        JUNIOR_TO_SENIOR_TRANSITION = (
            "junior_to_senior_transition",
            _("Junior-to-Senior transition"),
        )

    class Severity(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regulatory_notice = models.ForeignKey(
        RegulatoryNotice,
        on_delete=models.CASCADE,
        related_name="regulatory_impacts",
    )
    affected_grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="regulatory_impacts",
    )
    affected_pathway = models.CharField(max_length=128, blank=True)
    affected_learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="regulatory_impacts",
    )
    impact_category = models.CharField(max_length=64, choices=Category.choices)
    impact_severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    action_required = models.TextField()

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Regulatory impact")
        verbose_name_plural = _("Regulatory impacts")
        indexes = [
            models.Index(
                fields=["impact_category", "impact_severity"],
                name="curr_reg_impact_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.action_required)
        self.action_required = self.action_required.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class TeacherReadinessRequirement(TimeStampedModel):
    class RequirementType(models.TextChoices):
        TRAINING_REQUIRED = "training_required", _("Training required")
        RETOOLING_REQUIRED = "retooling_required", _("Retooling required")
        ASSESSMENT_TRAINING_REQUIRED = (
            "assessment_training_required",
            _("Assessment training required"),
        )
        PATHWAY_READINESS_REQUIRED = (
            "pathway_readiness_required",
            _("Pathway readiness required"),
        )
        IMPLEMENTATION_BRIEFING_REQUIRED = (
            "implementation_briefing_required",
            _("Implementation briefing required"),
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regulatory_notice = models.ForeignKey(
        RegulatoryNotice,
        on_delete=models.CASCADE,
        related_name="teacher_readiness_requirements",
    )
    affected_learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="teacher_readiness_requirements",
    )
    affected_grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="teacher_readiness_requirements",
    )
    affected_pathway = models.CharField(max_length=128, blank=True)
    requirement_type = models.CharField(max_length=48, choices=RequirementType.choices)
    summary = models.TextField()
    effective_from = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Teacher readiness requirement")
        verbose_name_plural = _("Teacher readiness requirements")
        indexes = [
            models.Index(
                fields=["requirement_type", "is_active"],
                name="curr_teacher_req_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        validate_governance_text(self.summary)
        self.summary = self.summary.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class PrincipalNotificationEvidenceCard(TimeStampedModel):
    class NotificationType(models.TextChoices):
        CURRICULUM_UPDATE = "curriculum_update", _("Curriculum update")
        REGULATORY_NOTICE = "regulatory_notice", _("Regulatory notice")
        TEACHER_READINESS_UPDATE = (
            "teacher_readiness_update",
            _("Teacher readiness update"),
        )
        ASSESSMENT_GUIDANCE_UPDATE = (
            "assessment_guidance_update",
            _("Assessment guidance update"),
        )
        JUNIOR_TO_SENIOR_TRANSITION_UPDATE = (
            "junior_to_senior_transition_update",
            _("Junior-to-Senior transition update"),
        )
        SCHOOL_ACTIVATION_REQUIRED = (
            "school_activation_required",
            _("School activation required"),
        )

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        READY_FOR_REVIEW = "ready_for_review", _("Ready for review")
        ISSUED = "issued", _("Issued")
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")
        ARCHIVED = "archived", _("Archived")

    class Severity(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="principal_notification_cards",
    )
    regulatory_notice = models.ForeignKey(
        RegulatoryNotice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="principal_notification_cards",
    )
    curriculum_diff = models.ForeignKey(
        CurriculumDiff,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="principal_notification_cards",
    )
    curriculum_impact = models.ForeignKey(
        CurriculumImpact,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="principal_notification_cards",
    )
    notification_type = models.CharField(
        max_length=64,
        choices=NotificationType.choices,
    )
    title = models.CharField(max_length=255)
    summary = models.TextField()
    evidence_summary = models.TextField()
    required_action = models.TextField()
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_principal_notification_cards",
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Principal notification evidence card")
        verbose_name_plural = _("Principal notification evidence cards")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "regulatory_notice", "notification_type"],
                name="curr_notice_card_unique_per_school",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="curr_card_tenant_status_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_text(self.title, "title")
        validate_governance_text(self.title)
        validate_governance_text(self.summary)
        validate_governance_text(self.evidence_summary)
        validate_governance_text(self.required_action)
        self.title = self.title.strip()
        self.summary = self.summary.strip()
        self.evidence_summary = self.evidence_summary.strip()
        self.required_action = self.required_action.strip()
        evidence_links = [
            self.regulatory_notice_id,
            self.curriculum_diff_id,
            self.curriculum_impact_id,
        ]
        if not any(evidence_links):
            raise ValidationError(
                {"regulatory_notice": _("Notification evidence is required.")}
            )
        if (
            self.status == self.Status.ISSUED
            and self.regulatory_notice_id
            and self.regulatory_notice.review_status
            != RegulatoryNotice.ReviewStatus.VERIFIED
        ):
            raise ValidationError(
                {"status": _("Verified source evidence is required before issue.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class SchoolUpdateAcknowledgement(TimeStampedModel):
    class Status(models.TextChoices):
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")
        NEEDS_INTERNAL_REVIEW = "needs_internal_review", _("Needs internal review")
        DEFERRED = "deferred", _("Deferred")
        REJECTED_FOR_SCHOOL_CONTEXT = (
            "rejected_for_school_context",
            _("Rejected for school context"),
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="school_update_acknowledgements",
    )
    notification_evidence_card = models.ForeignKey(
        PrincipalNotificationEvidenceCard,
        on_delete=models.PROTECT,
        related_name="acknowledgements",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="school_update_acknowledgements",
    )
    acknowledged_at = models.DateTimeField()
    acknowledgement_status = models.CharField(max_length=48, choices=Status.choices)
    principal_notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("School update acknowledgement")
        verbose_name_plural = _("School update acknowledgements")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "notification_evidence_card"],
                name="curr_school_ack_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "acknowledgement_status"],
                name="curr_ack_tenant_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.notification_evidence_card_id
            and self.tenant_id
            and self.notification_evidence_card.tenant_id != self.tenant_id
        ):
            raise ValidationError(
                {"tenant": _("Acknowledgement tenant does not match notification.")}
            )
        if self.principal_notes:
            validate_governance_text(self.principal_notes)
            self.principal_notes = self.principal_notes.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)
