from __future__ import annotations

import re

from django.core.exceptions import ValidationError


def normalize_authority_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValidationError({"code": "Authority code is required."})
    return normalized
