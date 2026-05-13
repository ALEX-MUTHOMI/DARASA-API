from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import TenantUserRole
from tenant.models import School, TimeStampedModel


code_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
    message=_("Codes must be lowercase alphanumeric slugs."),
)

admission_number_validator = RegexValidator(
    regex=r"^[A-Z0-9-]{3,32}$",
    message=_("Admission numbers must be uppercase alphanumeric codes."),
)


class AcademicYear(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="academic_years",
    )
    label = models.CharField(max_length=64)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Academic year")
        verbose_name_plural = _("Academic years")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "label"],
                name="academics_year_tenant_label_unique",
            ),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(is_active=True),
                name="academics_one_active_year_per_tenant",
            ),
            models.CheckConstraint(
                condition=Q(start_date__lt=models.F("end_date")),
                name="academics_year_dates_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="acad_year_active_idx"),
            models.Index(fields=["tenant", "start_date"], name="acad_year_start_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.label:
            self.label = self.label.strip()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": _("End date must follow start date.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"AcademicYear {self.pk}"


class Term(TimeStampedModel):
    class TermCode(models.TextChoices):
        TERM_1 = "term_1", _("Term 1")
        TERM_2 = "term_2", _("Term 2")
        TERM_3 = "term_3", _("Term 3")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="academic_terms",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    code = models.SlugField(max_length=32, choices=TermCode.choices)
    name = models.CharField(max_length=64)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Term")
        verbose_name_plural = _("Terms")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "academic_year", "code"],
                name="academics_term_year_code_unique",
            ),
            models.CheckConstraint(
                condition=Q(start_date__lt=models.F("end_date")),
                name="academics_term_dates_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="acad_term_active_idx"),
            models.Index(fields=["academic_year", "code"], name="acad_term_year_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if self.academic_year_id and self.tenant_id != self.academic_year.tenant_id:
            raise ValidationError({"tenant": _("Term tenant is invalid.")})
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": _("End date must follow start date.")})
        if self.academic_year_id and self.start_date and self.end_date:
            if (
                self.start_date < self.academic_year.start_date
                or self.end_date > self.academic_year.end_date
            ):
                raise ValidationError({"start_date": _("Term is outside the year.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Term {self.pk}"


class GradeLevel(TimeStampedModel):
    class Stage(models.TextChoices):
        PRE_PRIMARY = "pre_primary", _("Pre-primary")
        PRIMARY = "primary", _("Primary")
        JUNIOR_SCHOOL = "junior_school", _("Junior school")
        SENIOR_SCHOOL = "senior_school", _("Senior school")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, validators=[code_validator])
    name = models.CharField(max_length=128)
    stage = models.SlugField(max_length=32, choices=Stage.choices)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Grade level")
        verbose_name_plural = _("Grade levels")
        indexes = [
            models.Index(fields=["stage", "is_active"], name="acad_grade_stage_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.code:
            self.code = self.code.strip().lower().replace(" ", "-")
        if self.name:
            self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class LearningArea(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="learning_areas",
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        related_name="learning_areas",
    )
    code = models.SlugField(max_length=64, validators=[code_validator])
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Learning area")
        verbose_name_plural = _("Learning areas")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "grade_level", "code"],
                name="academics_learning_area_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "grade_level", "is_active"],
                name="acad_learning_area_idx",
            ),
        ]

    @property
    def knec_code(self) -> str:
        return self.code

    def clean(self) -> None:
        super().clean()
        if self.code:
            self.code = self.code.strip().lower().replace(" ", "-")
        if self.name:
            self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class Subject(LearningArea):
    class Meta:
        proxy = True
        verbose_name = _("Subject compatibility view")
        verbose_name_plural = _("Subject compatibility views")


class Cohort(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="cohorts",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="cohorts",
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        related_name="cohorts",
    )
    name = models.CharField(max_length=100)
    stream_label = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Cohort")
        verbose_name_plural = _("Cohorts")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "academic_year", "grade_level", "name"],
                name="academics_cohort_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="acad_cohort_active_idx"),
            models.Index(
                fields=["tenant", "academic_year", "grade_level"],
                name="acad_cohort_lookup_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if self.stream_label:
            self.stream_label = self.stream_label.strip()
        if self.academic_year_id and self.tenant_id != self.academic_year.tenant_id:
            raise ValidationError({"tenant": _("Cohort tenant is invalid.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Cohort {self.pk}"


class Student(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="learners",
    )
    admission_number = models.CharField(
        max_length=32,
        validators=[admission_number_validator],
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Learner")
        verbose_name_plural = _("Learners")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "admission_number"],
                name="academics_learner_admission_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "is_active"],
                name="acad_learner_active_idx",
            ),
            models.Index(
                fields=["tenant", "admission_number"],
                name="acad_learner_admission_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.admission_number:
            self.admission_number = self.admission_number.strip().upper()
        if self.first_name:
            self.first_name = self.first_name.strip()
        if self.last_name:
            self.last_name = self.last_name.strip()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Learner {self.pk}"


class Enrollment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Enrollment")
        verbose_name_plural = _("Enrollments")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student", "cohort", "academic_year", "term"],
                condition=Q(is_active=True),
                name="academics_active_enrollment_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "student"], name="acad_enroll_student_idx"),
            models.Index(fields=["tenant", "cohort"], name="acad_enroll_cohort_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        tenant_id = self.tenant_id
        related_tenant_ids = [
            getattr(self.student, "tenant_id", None),
            getattr(self.cohort, "tenant_id", None),
            getattr(self.academic_year, "tenant_id", None),
            getattr(self.term, "tenant_id", None),
        ]
        if tenant_id and any(value != tenant_id for value in related_tenant_ids):
            raise ValidationError({"tenant": _("Enrollment tenant is invalid.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Enrollment {self.pk}"


class TeacherAssignment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    learning_area = models.ForeignKey(
        LearningArea,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    assigned_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = _("Teacher assignment")
        verbose_name_plural = _("Teacher assignments")
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "teacher",
                    "cohort",
                    "learning_area",
                    "academic_year",
                    "term",
                ],
                condition=Q(is_active=True),
                name="academics_active_teacher_assignment_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "teacher"], name="acad_assign_teacher_idx"),
            models.Index(fields=["tenant", "cohort"], name="acad_assign_cohort_idx"),
            models.Index(
                fields=["tenant", "learning_area"],
                name="acad_assign_learning_area_idx",
            ),
        ]

    @property
    def subject_id(self) -> Any:
        return getattr(self, "learning_area_id", None)

    def clean(self) -> None:
        super().clean()
        tenant_id = self.tenant_id
        related_tenant_ids = [
            getattr(self.cohort, "tenant_id", None),
            getattr(self.learning_area, "tenant_id", None),
            getattr(self.academic_year, "tenant_id", None),
            getattr(self.term, "tenant_id", None),
        ]
        if tenant_id and any(value != tenant_id for value in related_tenant_ids):
            raise ValidationError({"tenant": _("Teacher assignment is invalid.")})
        if self.teacher_id and tenant_id:
            tenant_bound = TenantUserRole.objects.filter(
                tenant_id=tenant_id,
                user_id=self.teacher_id,
                is_active=True,
                role__is_active=True,
            ).exists()
            if not tenant_bound:
                raise ValidationError({"teacher": _("Teacher assignment is invalid.")})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"TeacherAssignment {self.pk}"
