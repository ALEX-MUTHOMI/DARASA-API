from __future__ import annotations

import hashlib
import hmac

from django.conf import settings


def normalize_admission_number(admission_number: str) -> str:
    return "".join(str(admission_number or "").upper().split())


def send_parent_login_code_request(admission_number: str) -> bool:
    normalized_admission = normalize_admission_number(admission_number)
    secret = settings.SECRET_KEY.encode("utf-8")
    digest = hmac.new(
        secret,
        normalized_admission.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    hmac.compare_digest(digest, digest)
    return False
