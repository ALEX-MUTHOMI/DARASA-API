"""Boundary checks between CBE/CCT context and school internal schemas."""

from __future__ import annotations

from dataclasses import dataclass

from grading.algorithms.school_grading_schema_validator import (
    is_internal_assessment_type,
)


@dataclass(frozen=True)
class SchemaBindingDecision:
    allowed: bool
    reason: str


def can_bind_school_schema(
    *,
    assessment_type: str,
    schema_assessment_type: str,
    has_cbe_context: bool,
) -> SchemaBindingDecision:
    if assessment_type == "cbe_rubric_assessment":
        return SchemaBindingDecision(False, "cbe_rubric_schema_override_denied")
    if not is_internal_assessment_type(assessment_type):
        return SchemaBindingDecision(False, "assessment_type_not_internal")
    if assessment_type != schema_assessment_type:
        return SchemaBindingDecision(False, "schema_type_mismatch")
    if not has_cbe_context:
        return SchemaBindingDecision(False, "missing_cbe_context")
    return SchemaBindingDecision(True, "allowed")
