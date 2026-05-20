"""Validation helpers for tenant-owned internal grading schemas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


INTERNAL_ASSESSMENT_TYPES = frozenset(
    {
        "quiz",
        "assignment",
        "practical",
        "exam",
        "project",
        "cat",
        "internal_exam",
        "mock_exam",
        "trial_exam",
        "departmental_test",
        "practical_component",
    }
)


@dataclass(frozen=True)
class SchemaValidationResult:
    is_valid: bool
    errors: tuple[str, ...]


def is_internal_assessment_type(assessment_type: str) -> bool:
    return assessment_type in INTERNAL_ASSESSMENT_TYPES


def validate_schema_bands(
    *,
    bands: list[dict[str, Any]],
    requires_full_coverage: bool,
) -> SchemaValidationResult:
    errors: list[str] = []
    normalized = sorted(
        [
            {
                "min": Decimal(str(band["min_percentage"])),
                "max": Decimal(str(band["max_percentage"])),
            }
            for band in bands
        ],
        key=lambda item: (item["min"], item["max"]),
    )
    if not normalized:
        errors.append("bands_required")
    for item in normalized:
        if item["min"] < 0 or item["max"] > 100 or item["min"] > item["max"]:
            errors.append("invalid_range")
    for previous, current in zip(normalized, normalized[1:]):
        if current["min"] <= previous["max"]:
            errors.append("overlapping_ranges")
    if requires_full_coverage and normalized:
        if normalized[0]["min"] != Decimal("0.00"):
            errors.append("coverage_gap")
        if normalized[-1]["max"] != Decimal("100.00"):
            errors.append("coverage_gap")
        for previous, current in zip(normalized, normalized[1:]):
            if current["min"] != previous["max"] + Decimal("0.01"):
                errors.append("coverage_gap")
                break
    return SchemaValidationResult(
        is_valid=not errors,
        errors=tuple(sorted(set(errors))),
    )
