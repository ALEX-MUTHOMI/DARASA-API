"""Internal handler registry for local event dispatch.

Phase 5 deliberately dispatches only to in-process handlers.  External broker
adapters can be added later behind this seam without changing producers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


EventHandler = Callable[[Any], None]
_HANDLERS: dict[str, list[tuple[str, EventHandler]]] = {}


def register_handler(
    event_type: str,
    consumer_name: str,
    handler: EventHandler,
) -> None:
    _HANDLERS.setdefault(event_type, [])
    if any(name == consumer_name for name, _ in _HANDLERS[event_type]):
        raise ValueError("consumer already registered")
    _HANDLERS[event_type].append((consumer_name, handler))


def clear_handlers() -> None:
    _HANDLERS.clear()


def get_handlers(event_type: str) -> list[tuple[str, EventHandler]]:
    return list(_HANDLERS.get(event_type, []))
