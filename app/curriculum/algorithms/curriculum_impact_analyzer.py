from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SENIOR_SIGNALS = frozenset({"grade 10", "grade 11", "grade 12", "senior school"})
JUNIOR_TO_SENIOR_SIGNALS = frozenset(
    {"grade 9", "kjsea", "grade 10 transition", "pathway placement"}
)


def _text(value: Mapping[str, Any]) -> str:
    return " ".join(str(item or "") for item in value.values()).lower()


def analyze_diff_item_impact(diff_item: Mapping[str, Any]) -> list[dict[str, str]]:
    text = _text(diff_item)
    entity_type = str(diff_item.get("entity_type", "")).lower()
    change_type = str(diff_item.get("change_type", "")).lower()
    impacts: list[dict[str, str]] = []

    if any(signal in text for signal in SENIOR_SIGNALS):
        impacts.append(
            {
                "impact_category": "senior_school_curriculum",
                "impact_severity": "medium",
                "action_required": "Principal curriculum review required.",
            }
        )
    if any(signal in text for signal in JUNIOR_TO_SENIOR_SIGNALS):
        impacts.append(
            {
                "impact_category": "junior_to_senior_transition",
                "impact_severity": "medium",
                "action_required": "Review Senior School transition impact.",
            }
        )
    if entity_type in {"rubric_foundation", "assessment_guidance"} or (
        "assessment" in text
    ):
        impacts.append(
            {
                "impact_category": "assessment_criteria",
                "impact_severity": "high",
                "action_required": "Review assessment guidance.",
            }
        )
    if entity_type in {"learning_area", "teacher_training_notice"} or (
        "teacher" in text
    ):
        impacts.append(
            {
                "impact_category": "teacher_readiness",
                "impact_severity": "medium",
                "action_required": "Review teacher readiness requirements.",
            }
        )
    if change_type in {"added", "updated", "renamed", "removed", "retired"}:
        impacts.extend(
            [
                {
                    "impact_category": "scheme_review_required",
                    "impact_severity": "low",
                    "action_required": "Future schemes review required.",
                },
                {
                    "impact_category": "grading_dependency_future",
                    "impact_severity": "low",
                    "action_required": "Future grading dependency review required.",
                },
                {
                    "impact_category": "report_dependency_future",
                    "impact_severity": "low",
                    "action_required": "Future report dependency review required.",
                },
                {
                    "impact_category": "lesson_assistant_dependency_future",
                    "impact_severity": "low",
                    "action_required": "Future lesson assistant review required.",
                },
            ]
        )
    return impacts
