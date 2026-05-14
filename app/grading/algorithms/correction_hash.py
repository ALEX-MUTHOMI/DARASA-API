"""Hash old grade state without storing raw academic payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.exceptions import ValidationError


def hash_grade_state(state: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {"grade_state": "Grade state is not serializable."}
        ) from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
