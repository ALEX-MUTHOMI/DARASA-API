from __future__ import annotations

import re

from django.core.exceptions import ValidationError


MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_FILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def validate_artifact_metadata(
    *,
    file_size: int,
    content_type: str,
    checksum: str,
) -> None:
    if file_size <= 0 or file_size > MAX_ARTIFACT_BYTES:
        raise ValidationError({"file_size": "Artifact size is not allowed."})
    if content_type.strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError({"content_type": "Artifact content type is not allowed."})
    if not CHECKSUM_PATTERN.fullmatch(checksum.strip().lower()):
        raise ValidationError({"checksum": "A valid SHA-256 checksum is required."})


def validate_artifact_file_name(file_name: str) -> str:
    value = file_name.strip()
    if (
        not SAFE_FILE_NAME_PATTERN.fullmatch(value)
        or ".." in value
        or "/" in value
        or "\\" in value
    ):
        raise ValidationError({"file_name": "Artifact file name is not allowed."})
    return value
