"""
grading/models.py
=================
Immutable Grade Record for the CBC Grading Engine
Back To Front Development

SECURITY & CONCURRENCY:
    - UUIDv4 Primary Keys to prevent IDOR enumeration.
    - OCC (Optimistic Concurrency Control) via the `version` field.
    - Unique Constraint ensures 1 Grade per Subject per Assessment per Student.
"""

import uuid
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from tenant.models import TimeStampedModel


class ExamAssessment(TimeStampedModel):
    """
    The Temporal Event Boundary (e.g., "Term 1 Midterm 2026").
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Assessment Name"), max_length=150)
    academic_year = models.IntegerField(
        _("Academic Year"),
        validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    term = models.IntegerField(
        _("Term"), 
        validators=[MinValueValidator(1), MaxValueValidator(3)]
    )

    class Meta:
        verbose_name = _("Exam Assessment")
        verbose_name_plural = _("Exam Assessments")
        constraints = [
            models.UniqueConstraint(
                fields=["name", "academic_year", "term"],
                name="unique_exam_assessment"
            )
        ]
        indexes = [
            models.Index(fields=["academic_year", "term"], name="idx_exam_year_term"),
        ]

    def __str__(self):
        return f"{self.name} - Term {self.term} ({self.academic_year})"


class GradeRecord(TimeStampedModel):
    """
    The core grade history entry.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    student = models.ForeignKey(
        "academics.Student", 
        on_delete=models.CASCADE, 
        related_name="grades"
    )
    subject = models.ForeignKey(
        "academics.Subject", 
        on_delete=models.CASCADE, 
        related_name="grades"
    )
    assessment = models.ForeignKey(
        ExamAssessment, 
        on_delete=models.CASCADE, 
        related_name="grades"
    )
    
    # Precision: 1 decimal place (e.g., 85.5)
    raw_score = models.FloatField(
        _("Raw Score"),
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    cbc_score = models.IntegerField(
        _("CBC Score"),
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text=_("1-4 scale representing the CBC competency level.")
    )
    remarks = models.CharField(
        _("Remarks"), 
        max_length=500, 
        blank=True
    )
    
    # Optimistic Concurrency Control (OCC)
    # Allows frontends to verify they are overwriting the correct version of a grade.
    version = models.IntegerField(_("Version"), default=1)

    class Meta:
        verbose_name = _("Grade Record")
        verbose_name_plural = _("Grade Records")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "assessment"],
                name="unique_student_subject_assessment_grade"
            )
        ]
        indexes = [
            models.Index(fields=["assessment", "subject", "student"], name="idx_grade_lookup"),
        ]

    def clean(self):
        super().clean()
        if not (0.0 <= self.raw_score <= 100.0):
            raise ValidationError({"raw_score": _("Raw score must be between 0 and 100.")})
        if not (1 <= self.cbc_score <= 4):
            raise ValidationError({"cbc_score": _("CBC score must be between 1 and 4.")})

    def __str__(self):
        return f"{self.student.admission_number} - {self.subject.knec_code}: {self.cbc_score}"
