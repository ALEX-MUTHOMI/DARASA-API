"""
academics/models.py
===================
Structural Base for the CBC Compiler & Fast-Grid
Back To Front Development

SECURITY & OPTIMIZATION:
    - All PKs are UUIDv4.
    - CheckConstraints applied to prevent logical corruption at DB level.
    - Strict `related_name` definitions to prevent ORM reverse-traversal collisions.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tenant.models import TimeStampedModel


def current_year():
    return timezone.now().year


class Subject(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Subject Name"), max_length=150)
    knec_code = models.CharField(
        _("KNEC Subject Code"),
        max_length=20,
        unique=True,
        help_text=_("Official KNEC exam code (e.g., 101 for English)"),
    )

    class Meta:
        verbose_name = _("Subject")
        verbose_name_plural = _("Subjects")
        indexes = [
            models.Index(fields=["knec_code"], name="idx_subject_knec"),
        ]

    def __str__(self):
        return f"{self.name} ({self.knec_code})"


class Cohort(TimeStampedModel):
    """
    Represents a specific Class/Stream in a given Academic Year.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Cohort Name"), max_length=100)
    academic_year = models.IntegerField(
        _("Academic Year"),
        default=current_year,
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
    )
    is_graduated = models.BooleanField(
        _("Has Graduated?"),
        default=False,
        help_text=_(
            "Graduated cohorts are read-only to preserve historical integrity."
        ),
    )

    class Meta:
        verbose_name = _("Cohort")
        verbose_name_plural = _("Cohorts")
        constraints = [
            models.UniqueConstraint(
                fields=["name", "academic_year"],
                name="unique_cohort_per_year",
            ),
            models.CheckConstraint(
                check=Q(academic_year__gte=2000) & Q(academic_year__lte=2100),
                name="check_valid_academic_year",
            ),
        ]
        indexes = [
            models.Index(
                fields=["academic_year", "is_graduated"],
                name="idx_cohort_year_grad",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class Student(TimeStampedModel):
    """
    Core Student Record.
    Scoped entirely to the Tenant's Database Schema.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(_("First Name"), max_length=100)
    last_name = models.CharField(_("Last Name"), max_length=100)
    admission_number = models.CharField(
        _("Admission Number"),
        max_length=50,
        unique=True,
        help_text=_("Must be unique within this specific School/Tenant."),
    )
    date_of_birth = models.DateField(_("Date of Birth"))
    is_active = models.BooleanField(
        _("Active Student?"),
        default=True,
        help_text=_("False if transferred or expelled. Retains historical data."),
    )

    class Meta:
        verbose_name = _("Student")
        verbose_name_plural = _("Students")
        constraints = [
            models.CheckConstraint(
                # Avoid raw NOW() constraints for DB-agnostic safety.
                check=Q(is_active__in=[True, False]),
                name="check_student_active_boolean",
            ),
        ]
        indexes = [
            models.Index(fields=["admission_number"], name="idx_student_adm"),
            models.Index(fields=["last_name", "first_name"], name="idx_student_name"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} [{self.admission_number}]"


class Enrollment(TimeStampedModel):
    """
    Maps a Student to a Cohort.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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

    class Meta:
        verbose_name = _("Enrollment")
        verbose_name_plural = _("Enrollments")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "cohort"],
                name="unique_student_cohort_enrollment",
            ),
        ]
        indexes = [
            models.Index(fields=["cohort", "student"], name="idx_enrollment_lookup"),
        ]

    def __str__(self):
        return f"{self.student.admission_number} -> {self.cohort.name}"


class TeacherAssignment(TimeStampedModel):
    """
    Maps a Teacher to a Cohort and Subject in the tenant schema.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        help_text=_("Cross-schema foreign key to the public identity model."),
    )
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )

    class Meta:
        verbose_name = _("Teacher Assignment")
        verbose_name_plural = _("Teacher Assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "cohort", "subject"],
                name="unique_teacher_cohort_subject",
            ),
        ]
        indexes = [
            models.Index(
                fields=["teacher", "cohort", "subject"],
                name="idx_fast_grid_auth",
            ),
            models.Index(fields=["cohort", "subject"], name="idx_cohort_subject"),
        ]

    def __str__(self):
        return (
            f"Teacher {self.teacher_id} -> {self.subject.name} "
            f"in {self.cohort.name}"
        )
