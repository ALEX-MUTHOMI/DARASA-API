from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def build_evidence_fingerprint(
    *,
    file_checksum: str,
    claimed_authority: str = "",
    claimed_reference_number: str = "",
    claimed_publication_number: str = "",
    claimed_publication_date: Any = "",
    claimed_effective_date: Any = "",
) -> str:
    """Fingerprint the submitted document identity, not its storage location."""
    parts = [
        str(file_checksum).strip().lower(),
        str(claimed_authority).strip().lower(),
        str(claimed_reference_number).strip().lower(),
        str(claimed_publication_number).strip().lower(),
        str(claimed_publication_date or "").strip().lower(),
        str(claimed_effective_date or "").strip().lower(),
    ]
    payload = "\x1f".join(parts).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def fingerprint_payload(payload: Mapping[str, Any]) -> str:
    return build_evidence_fingerprint(
        file_checksum=str(payload.get("file_checksum", "")),
        claimed_authority=str(payload.get("claimed_authority", "")),
        claimed_reference_number=str(payload.get("claimed_reference_number", "")),
        claimed_publication_number=str(payload.get("claimed_publication_number", "")),
        claimed_publication_date=payload.get("claimed_publication_date", ""),
        claimed_effective_date=payload.get("claimed_effective_date", ""),
    )
