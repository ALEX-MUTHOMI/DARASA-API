from __future__ import annotations

import hashlib
import hmac

from django.conf import settings


ADMISSION_FINGERPRINT_LENGTH = 12


def normalize_admission_number(admission_number: str) -> str:
    return "".join(str(admission_number or "").upper().split())


def fingerprint_admission_number(admission_number: str) -> str:
    """Return a short, non-reversible correlation token for audit logs.

    Never log a raw admission number: it identifies a specific learner.
    This fingerprint lets operators correlate repeated attempts (e.g. for
    abuse detection) without exposing or storing the underlying PII, and is
    keyed by SECRET_KEY so it cannot be brute-forced offline by an attacker
    without the server secret.
    """

    normalized_admission = normalize_admission_number(admission_number)
    secret = settings.SECRET_KEY.encode("utf-8")
    digest = hmac.new(
        secret,
        normalized_admission.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:ADMISSION_FINGERPRINT_LENGTH]


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
