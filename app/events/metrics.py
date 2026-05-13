"""Small metrics helpers for the local relay."""

from __future__ import annotations

from events.selectors import get_dead_letter_summary, get_event_backlog_summary


def get_event_metrics() -> dict[str, object]:
    return {
        "backlog": get_event_backlog_summary(),
        "dead_letters": get_dead_letter_summary(),
    }
