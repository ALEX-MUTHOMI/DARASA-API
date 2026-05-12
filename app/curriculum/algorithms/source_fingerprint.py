from __future__ import annotations

import hashlib


def build_source_fingerprint(
    *,
    authority_code: str,
    source_reference: str,
    version_label: str,
    checksum: str,
) -> str:
    parts = [
        authority_code.strip().lower(),
        source_reference.strip().lower(),
        version_label.strip().lower(),
        checksum.strip().lower(),
    ]
    payload = "\x1f".join(parts).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
