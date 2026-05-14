"""Stable identity for a teacher grading context.

The context is intentionally value-only.  It helps selectors, policies, and
future idempotency logic reason about tenant, teacher, assessment, cohort,
learning area, year, and term without querying the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class GradingContextIdentity:
    tenant_id: str
    teacher_id: str
    assessment_id: str
    cohort_id: str
    learning_area_id: str
    academic_year_id: str
    term_id: str

    @property
    def key(self) -> str:
        return (
            f"tenant:{self.tenant_id}:teacher:{self.teacher_id}:"
            f"assessment:{self.assessment_id}:cohort:{self.cohort_id}:"
            f"learning_area:{self.learning_area_id}:"
            f"year:{self.academic_year_id}:term:{self.term_id}"
        )


def build_grading_context_identity(
    *,
    tenant_id: Any,
    teacher_id: Any,
    assessment_id: Any,
    cohort_id: Any,
    learning_area_id: Any,
    academic_year_id: Any,
    term_id: Any,
) -> GradingContextIdentity:
    values = {
        "tenant_id": tenant_id,
        "teacher_id": teacher_id,
        "assessment_id": assessment_id,
        "cohort_id": cohort_id,
        "learning_area_id": learning_area_id,
        "academic_year_id": academic_year_id,
        "term_id": term_id,
    }
    if any(value in (None, "") for value in values.values()):
        raise ValidationError({"grading_context": "Grading context is incomplete."})
    return GradingContextIdentity(**{key: str(value) for key, value in values.items()})
