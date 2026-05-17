"""Deterministic dependency guards for apps that consume CCT truth.

These helpers do not query or mutate data.  Services and models pass persisted
state into them so grading, compilation, and future reporting can fail closed
without reinterpreting curriculum governance inline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyGuardResult:
    is_allowed: bool
    reason: str


def validate_grading_dependency_state(
    *,
    is_published: bool,
    is_school_adopted: bool,
    is_withdrawn: bool,
    has_learning_area_context: bool,
    has_rubric_context: bool,
) -> DependencyGuardResult:
    if is_withdrawn:
        return DependencyGuardResult(False, "curriculum_version_withdrawn")
    if not is_published:
        return DependencyGuardResult(False, "curriculum_version_unpublished")
    if not is_school_adopted:
        return DependencyGuardResult(False, "curriculum_version_not_adopted")
    if not has_learning_area_context:
        return DependencyGuardResult(False, "learning_area_context_required")
    if not has_rubric_context:
        return DependencyGuardResult(False, "rubric_context_required")
    return DependencyGuardResult(True, "allowed")


def validate_historical_dependency_state(
    *,
    has_curriculum_version: bool,
    has_learning_area_context: bool,
    has_snapshot_context: bool,
) -> DependencyGuardResult:
    """Validate preserved historical context without requiring current adoption."""

    if not has_curriculum_version:
        return DependencyGuardResult(False, "curriculum_version_required")
    if not has_learning_area_context:
        return DependencyGuardResult(False, "learning_area_context_required")
    if not has_snapshot_context:
        return DependencyGuardResult(False, "snapshot_context_required")
    return DependencyGuardResult(True, "historical_context_preserved")


def validate_reporting_dependency_state(
    *,
    has_compiled_snapshot: bool,
    has_preserved_curriculum_context: bool,
    is_report_phase_enabled: bool,
) -> DependencyGuardResult:
    if not is_report_phase_enabled:
        return DependencyGuardResult(False, "reports_not_enabled")
    if not has_compiled_snapshot:
        return DependencyGuardResult(False, "compiled_snapshot_required")
    if not has_preserved_curriculum_context:
        return DependencyGuardResult(False, "curriculum_context_required")
    return DependencyGuardResult(True, "allowed")
