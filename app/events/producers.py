"""Producer-facing helpers.

Business modules should import these helpers or the service API instead of
writing `EventOutbox` rows directly.
"""

from __future__ import annotations

from events.services import write_outbox_event

__all__ = ["write_outbox_event"]
