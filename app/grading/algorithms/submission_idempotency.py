"""Stable hashes and idempotency checks for grade submissions.

Slow networks can replay the same request.  The service layer uses these pure
helpers to distinguish a safe retry from a same-key/different-payload attack.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.exceptions import ValidationError


def canonical_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def require_idempotency_key(idempotency_key: str | None) -> str:
    value = (idempotency_key or "").strip()
    if not value:
        raise ValidationError({"idempotency_key": "Idempotency key is required."})
    return value


def ensure_same_payload(*, existing_hash: str, new_hash: str) -> None:
    if existing_hash and existing_hash != new_hash:
        raise ValidationError(
            {"idempotency_key": "Idempotency key was used with a different payload."}
        )
