"""Dispatcher entrypoints for the local outbox relay.

The dispatcher delegates batch safety to `events.algorithms` through the
service layer.  Keeping dispatch planning deterministic prevents relay workers
from taking unbounded work or colliding on fresh locks.
"""

from __future__ import annotations

from events.services import dispatch_pending_events, lock_pending_events

__all__ = ["dispatch_pending_events", "lock_pending_events"]
