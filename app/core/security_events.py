"""Structured security-event logging.

Security-relevant occurrences (rate limiting, auth failures, access denials)
must be visible without being buried in general request logs, and must never
carry raw PII (admission numbers, names, guardian contacts). Callers pass
already-minimized fields only.
"""

from __future__ import annotations

from typing import Any

from core.metrics import record_security_event
from core.observability import get_logger


security_logger = get_logger("darasa.security")


def log_security_event(event_type: str, **fields: Any) -> None:
    security_logger.warning("security.event", event_type=event_type, **fields)
    record_security_event(event_type)
