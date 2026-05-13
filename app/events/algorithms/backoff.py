"""Calculate bounded retry delays for failed dispatch attempts.

Retry timing is deterministic to keep tests reproducible and to avoid retry
storms when a dependency is unhealthy.  Jitter can be added later at the relay
edge without changing the policy contract.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError


def calculate_backoff_seconds(
    *,
    attempt_number: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> int:
    if attempt_number < 1:
        raise ValidationError({"attempt_number": "Attempt number is invalid."})
    delay = base_delay_seconds * (2 ** (attempt_number - 1))
    return min(delay, max_delay_seconds)
