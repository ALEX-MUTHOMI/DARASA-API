"""Normalize and validate event names before they reach the outbox.

The event bus accepts facts, not commands.  This module rejects command-shaped
names and enforces a controlled namespace with an explicit version suffix for
full event names.  Services may store the namespace and version separately, but
new code should still use these helpers to avoid event-name drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError


BASE_EVENT_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
VERSIONED_EVENT_PATTERN = re.compile(
    r"^(?P<event_type>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)"
    r"\.v(?P<version>[1-9][0-9]*)$"
)
COMMAND_TOKENS = frozenset(
    {
        "command",
        "delete",
        "delete_everything",
        "do",
        "execute",
        "now",
        "publish_this",
        "run",
        "send",
        "send_message",
        "update_every",
        "update_every_school",
    }
)


@dataclass(frozen=True)
class NormalizedEventName:
    event_type: str
    event_version: int
    canonical_name: str


def _parts(value: str) -> list[str]:
    return [part for segment in value.split(".") for part in segment.split("_")]


def _reject_command_language(value: str) -> None:
    parts = set(_parts(value))
    segments = set(value.split("."))
    if parts & COMMAND_TOKENS or segments & COMMAND_TOKENS:
        raise ValidationError({"event_type": "Events must describe facts."})


def validate_event_namespace(event_type: str) -> str:
    """Validate the stored event namespace without the ``.vN`` suffix."""

    value = str(event_type or "").strip().lower()
    if not BASE_EVENT_PATTERN.fullmatch(value):
        raise ValidationError({"event_type": "Event type name is invalid."})
    _reject_command_language(value)
    return value


def normalize_event_name(event_name: str) -> NormalizedEventName:
    """Return normalized namespace/version from a full ``name.vN`` event."""

    value = str(event_name or "").strip().lower()
    match = VERSIONED_EVENT_PATTERN.fullmatch(value)
    if not match:
        raise ValidationError(
            {"event_type": "Event name must include a version suffix."}
        )
    event_type = validate_event_namespace(match.group("event_type"))
    event_version = int(match.group("version"))
    return NormalizedEventName(
        event_type=event_type,
        event_version=event_version,
        canonical_name=f"{event_type}.v{event_version}",
    )


def build_event_name(event_type: str, event_version: int) -> str:
    namespace = validate_event_namespace(event_type)
    if int(event_version) < 1:
        raise ValidationError({"event_version": "Event version is invalid."})
    return f"{namespace}.v{int(event_version)}"
