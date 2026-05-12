from __future__ import annotations

import hashlib


def compute_sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
