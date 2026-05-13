from __future__ import annotations


def map_junior_to_senior_signals(*, title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    signals: list[str] = []
    if "grade 9" in text and "grade 10" in text:
        signals.append("grade_9_to_grade_10_transition")
    if "kjsea" in text:
        signals.append("kjsea_transition_signal")
    if "pathway" in text or "placement" in text:
        signals.append("pathway_selection_signal")
    if "readiness" in text and ("senior" in text or "grade 10" in text):
        signals.append("grade_10_readiness_signal")
    if "prerequisite" in text:
        signals.append("senior_learning_area_prerequisite_signal")
    return signals
