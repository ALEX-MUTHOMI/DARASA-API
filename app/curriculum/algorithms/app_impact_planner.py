from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


APP_DOMAINS = (
    "academics",
    "assessments",
    "examinations",
    "grading",
    "compilation",
    "reports_future",
    "schemes_of_work_future",
    "lesson_plans_future",
    "teacher_readiness",
    "principal_notices",
    "parent_analytics_future",
    "nlp_future",
)


@dataclass(frozen=True)
class AppImpactProposal:
    app_domain: str
    impact_type: str
    affected_scope: dict[str, Any]
    required_action: str
    safe_behavior: str
    historical_protection_rule: str
    status: str = "planned"


def plan_app_impacts(
    *,
    scope: Mapping[str, Any],
    app_domains: Iterable[str] | None = None,
) -> tuple[AppImpactProposal, ...]:
    selected = tuple(app_domains or APP_DOMAINS)
    proposals: list[AppImpactProposal] = []
    for domain in selected:
        if domain == "grading":
            safe_behavior = "New assessments may bind only after tenant adoption."
            history = "Existing assessments and grade records preserve old context."
        elif domain == "compilation":
            safe_behavior = "Future compilations use stored assessment context."
            history = "Compiled snapshots preserve old curriculum context."
        elif domain == "reports_future":
            safe_behavior = "Reports must consume compiled snapshots later."
            history = "Historical reports must not re-resolve live CCT state."
        elif domain == "nlp_future":
            safe_behavior = "NLP may use approved facts only in future phases."
            history = "NLP cannot decide or mutate academic records."
        else:
            safe_behavior = "Review required before future work changes behavior."
            history = "Existing academic history must not mutate silently."
        proposals.append(
            AppImpactProposal(
                app_domain=domain,
                impact_type="review_required",
                affected_scope=dict(scope),
                required_action="review_before_activation",
                safe_behavior=safe_behavior,
                historical_protection_rule=history,
            )
        )
    return tuple(proposals)
