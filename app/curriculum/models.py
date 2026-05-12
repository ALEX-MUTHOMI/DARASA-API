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
from curriculum.algorithms.artifact_validator import validate_artifact_metadata
from curriculum.algorithms.authority_normalizer import normalize_authority_code
from curriculum.algorithms.pii_guard import validate_governance_text
from curriculum.algorithms.source_url_validator import validate_source_url
from tenant.models import TimeStampedModel


code_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
    message=_("Codes must be lowercase alphanumeric slugs."),
)


def _normalize_code(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValidationError({field_name: _("This field is required.")})


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
        self.allowed_domains = [
            domain.strip().lower().rstrip(".")
            for domain in self.allowed_domains
            if isinstance(domain, str) and domain.strip()
        ]
        if not self.allowed_domains:
            raise ValidationError(
                {"allowed_domains": _("Allowed domains are required.")}
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
        self.file_name = self.file_name.strip()
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
