from __future__ import annotations


def classify_regulatory_notice(
    *,
    authority_code: str,
    title: str,
    summary: str,
) -> str:
    haystack = f"{authority_code} {title} {summary}".lower()
    if "tsc" in haystack or "teacher service" in haystack:
        if "training" in haystack or "retool" in haystack:
            return "teacher_training_notice"
        return "tsc_teacher_update"
    if "knec" in haystack or "assessment" in haystack or "examination" in haystack:
        return "knec_assessment_guidance"
    if "kicd" in haystack or "curriculum design" in haystack:
        return "kicd_curriculum_update"
    if "pathway" in haystack:
        return "pathway_guidance"
    if "senior school" in haystack or "grade 10" in haystack:
        return "senior_school_transition_notice"
    if "implementation" in haystack:
        return "implementation_guidance"
    return "moe_circular"
