"""Assessment lifecycle helpers for CBE/CCT grading integrity.

These helpers prevent the most damaging grading mistake: changing the
curriculum or rubric context after marks have started to accumulate.  The
functions are intentionally pure so the model layer can decide how to obtain
the database facts without hiding side effects inside the algorithm package.
"""

from __future__ import annotations

from collections.abc import Iterable


CURRICULUM_CONTEXT_FIELDS = frozenset(
    {
        "curriculum_version",
        "learning_area",
        "rubric_foundation",
    }
)


def changed_curriculum_context_fields(
    *,
    old_values: dict[str, object | None],
    new_values: dict[str, object | None],
) -> set[str]:
    return {
        field
        for field in CURRICULUM_CONTEXT_FIELDS
        if old_values.get(field) != new_values.get(field)
    }


def curriculum_context_mutation_allowed(
    *,
    changed_fields: Iterable[str],
    has_submitted_batches: bool,
    has_grade_records: bool,
) -> bool:
    """Deny curriculum context mutation after grading has begun."""

    changed = set(changed_fields) & CURRICULUM_CONTEXT_FIELDS
    if not changed:
        return True
    return not (has_submitted_batches or has_grade_records)
