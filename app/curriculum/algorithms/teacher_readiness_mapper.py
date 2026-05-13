from __future__ import annotations


def map_teacher_readiness_requirement(*, title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if "assessment" in text and "training" in text:
        return "assessment_training_required"
    if "retool" in text:
        return "retooling_required"
    if "pathway" in text and "readiness" in text:
        return "pathway_readiness_required"
    if "briefing" in text or "implementation" in text:
        return "implementation_briefing_required"
    return "training_required"
