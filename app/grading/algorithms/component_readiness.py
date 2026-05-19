from __future__ import annotations

from typing import Any

from grading.algorithms.readiness_blockers import ReadinessBlocker, blocker


def component_readiness_blockers(
    *,
    component_summary: dict[str, Any] | None,
) -> list[ReadinessBlocker]:
    summary = component_summary or {}
    missing_required = int(summary.get("missing_required_component_count") or 0)
    if missing_required <= 0:
        return []
    return [
        blocker(
            code="missing_required_component",
            message="Required practical/component marks are incomplete.",
            scope="component",
        )
    ]
