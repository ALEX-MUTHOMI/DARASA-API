"""Validate event payload shape without touching the database.

Consumers need predictable JSON objects, not raw model dumps or arbitrary
Python objects.  This module enforces required fields and optional primitive
types while leaving business interpretation to consumers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError


TYPE_MAP = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "bool": bool,
    "boolean": bool,
    "dict": dict,
    "object": dict,
    "list": list,
}


def ensure_json_serializable(payload: Mapping[str, Any]) -> None:
    try:
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"payload": "Event payload must be JSON-safe."}) from exc


def validate_payload_schema(
    *,
    payload: Mapping[str, Any],
    payload_schema: Mapping[str, Any],
) -> None:
    if not isinstance(payload, Mapping):
        raise ValidationError({"payload": "Event payload must be an object."})
    ensure_json_serializable(payload)

    required = payload_schema.get("required", [])
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValidationError({"payload": "Event payload is missing required fields."})

    types = payload_schema.get("types", {})
    if not isinstance(types, Mapping):
        raise ValidationError({"payload_schema": "Payload field types are invalid."})
    for field, type_name in types.items():
        if field not in payload:
            continue
        expected = TYPE_MAP.get(str(type_name).lower())
        if expected is None:
            raise ValidationError(
                {"payload_schema": "Payload field type is unsupported."}
            )
        if not isinstance(payload[field], expected):
            raise ValidationError({"payload": "Event payload field type is invalid."})
