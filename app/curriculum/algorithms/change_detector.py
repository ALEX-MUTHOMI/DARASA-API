from __future__ import annotations


def detect_source_change(
    old_fingerprint: str | None,
    new_fingerprint: str,
) -> str:
    if not old_fingerprint:
        return "new_version_candidate"
    if old_fingerprint == new_fingerprint:
        return "no_change"
    return "changed_source"
