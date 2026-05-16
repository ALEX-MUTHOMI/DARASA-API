"""Validate the in-memory input contract for grade compilation.

Services fetch tenant-scoped rows from the database.  This algorithm verifies
that the assembled records belong to one submitted, CBE/CCT-bound assessment
context before any snapshot facts are built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError

from grading.models import Assessment, GradeSubmissionBatch


@dataclass(frozen=True)
class CompilationInput:
    tenant_id: str
    assessment: Any
    roster_student_ids: set[str]
    grade_records: list[Any]
    components: list[Any]
    source_batch_ids: list[str]


def build_compilation_input(
    *,
    tenant: Any,
    assessment: Any,
    roster: list[Any],
    grade_records: list[Any],
    components: list[Any],
) -> CompilationInput:
    if tenant is None or assessment is None:
        raise ValidationError({"tenant": "Compilation context is required."})
    if assessment.tenant_id != tenant.id:
        raise ValidationError({"assessment": "Assessment tenant is invalid."})
    if assessment.status != Assessment.Status.OPEN:
        raise ValidationError({"assessment": "Assessment is not compilable."})
    if not assessment.is_operationally_bound():
        raise ValidationError({"assessment": "Assessment is not CBE/CCT-bound."})
    roster_student_ids = {str(student.id) for student in roster}
    source_batch_ids = set()
    for record in grade_records:
        if record.tenant_id != tenant.id or record.assessment_id != assessment.id:
            raise ValidationError({"grade_record": "Grade record scope is invalid."})
        if record.submission_batch.status != GradeSubmissionBatch.Status.SUBMITTED:
            raise ValidationError({"grade_record": "Only submitted records compile."})
        source_batch_ids.add(str(record.submission_batch_id))
    for component in components:
        if component.tenant_id != tenant.id or component.assessment_id != assessment.id:
            raise ValidationError({"component": "Component scope is invalid."})
    return CompilationInput(
        tenant_id=str(tenant.id),
        assessment=assessment,
        roster_student_ids=roster_student_ids,
        grade_records=grade_records,
        components=components,
        source_batch_ids=sorted(source_batch_ids),
    )
