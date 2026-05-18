from __future__ import annotations

import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError

from curriculum.algorithms.artifact_validator import (
    validate_artifact_file_name,
    validate_artifact_metadata,
)
from curriculum.algorithms.pii_guard import validate_governance_text


PRIVATE_STORAGE_PATTERN = re.compile(r"^(private|cct-evidence)://[A-Za-z0-9._/-]+$")


@dataclass(frozen=True)
class UploadMetadata:
    storage_reference: str
    file_name: str
    content_type: str
    size_bytes: int
    file_checksum: str


def validate_storage_reference(value: str) -> str:
    reference = str(value or "").strip()
    if not PRIVATE_STORAGE_PATTERN.fullmatch(reference):
        raise ValidationError(
            {"storage_reference": "Private storage reference is required."}
        )
    if ".." in reference or "\\" in reference:
        raise ValidationError(
            {"storage_reference": "Storage reference is not allowed."}
        )
    return reference


def validate_upload_metadata(
    *,
    storage_reference: str,
    file_name: str,
    content_type: str,
    size_bytes: int,
    file_checksum: str,
) -> UploadMetadata:
    safe_name = validate_artifact_file_name(file_name)
    validate_governance_text(safe_name)
    validate_artifact_metadata(
        file_size=size_bytes,
        content_type=content_type,
        checksum=file_checksum,
    )
    return UploadMetadata(
        storage_reference=validate_storage_reference(storage_reference),
        file_name=safe_name,
        content_type=content_type.strip().lower(),
        size_bytes=size_bytes,
        file_checksum=file_checksum.strip().lower(),
    )
