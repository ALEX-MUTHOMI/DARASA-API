"""Hash audit states without storing raw sensitive values.

Audit records need integrity evidence, not payload copies.  Canonical JSON and
SHA-256 give deterministic old/new state hashes while keeping sensitive content
out of durable audit tables.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.exceptions import ValidationError


def hash_state(state: Any) -> str:
    try:
        encoded = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValidationError({"audit": "Audit state is not serializable."}) from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
