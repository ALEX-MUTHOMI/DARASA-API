"""Event contract registry helpers.

The database is the source of truth for active event contracts.  This module is
a small convenience layer for code that needs the initial Phase 5 contract list
or wants to bootstrap those records in tests and management tasks.
"""

from __future__ import annotations

from events.constants import INITIAL_EVENT_CONTRACTS
from events.services import register_initial_event_types

__all__ = ["INITIAL_EVENT_CONTRACTS", "register_initial_event_types"]
