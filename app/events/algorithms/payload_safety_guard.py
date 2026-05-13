"""Reject event payloads that try to move secrets, PII, or raw documents.

Event payloads are durable and may be replayed.  They must carry references and
small metadata, not child data, credentials, full documents, or upload bytes.
The scan is recursive and reports sanitized reasons only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError


SENSITIVE_KEY_FRAGMENTS = (
    "access_token",
    "admission",
    "email",
    "full_curriculum_text",
    "guardian",
    "learner_name",
    "learner_names",
    "password",
    "phone",
    "private_key",
    "raw_curriculum",
    "raw_payload",
    "raw_uploaded_file",
    "secret",
    "student_name",
    "student_names",
    "teacher_private_notes",
    "token",
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b[A-Z]{2,5}[-_]?\d{3,}\b"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(password|token|secret)\s*[:=]", re.IGNORECASE),
)


def payload_size_bytes(payload: Mapping[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def validate_payload_size(payload: Mapping[str, Any], *, max_bytes: int) -> None:
    if payload_size_bytes(payload) > max_bytes:
        raise ValidationError({"payload": "Event payload is too large."})


def reject_sensitive_payload(payload: Mapping[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                key_text = str(key).strip().lower()
                if any(fragment in key_text for fragment in SENSITIVE_KEY_FRAGMENTS):
                    raise ValidationError(
                        {"payload": "Event payload contains sensitive fields."}
                    )
                walk(nested)
            return
        if isinstance(value, list):
            if value and all(isinstance(item, str) for item in value):
                joined = " ".join(value).lower()
                if "learner" in joined or "student" in joined:
                    raise ValidationError(
                        {"payload": "Event payload contains sensitive values."}
                    )
            for item in value:
                walk(item)
            return
        if isinstance(value, str):
            for pattern in SENSITIVE_VALUE_PATTERNS:
                if pattern.search(value):
                    raise ValidationError(
                        {"payload": "Event payload contains sensitive values."}
                    )

    walk(payload)


def sanitize_failure_text(value: str, *, fallback: str = "sanitized_failure") -> str:
    text = str(value or "")[:255]
    try:
        reject_sensitive_payload({"message": text})
    except ValidationError:
        return fallback
    return text
