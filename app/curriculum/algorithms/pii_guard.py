from __future__ import annotations

import re

from django.core.exceptions import ValidationError


PII_PATTERNS = (
    re.compile(r"\b(admission|adm)[-_\s]?(number|no\.?)?[-_\s]?[a-z0-9-]{3,}\b", re.I),
    re.compile(r"\bguardian\b", re.I),
    re.compile(r"\bpupil\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", re.I),
    re.compile(r"\blearner\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", re.I),
)
HTML_INJECTION_PATTERNS = (
    re.compile(r"<\s*(script|img|svg|iframe|object|embed|a)\b", re.I),
    re.compile(r"\bon[a-z]+\s*=", re.I),
    re.compile(r"javascript\s*:", re.I),
)


def validate_governance_text(value: str) -> None:
    if not value or not value.strip():
        raise ValidationError({"summary": "Governance text is required."})
    for pattern in PII_PATTERNS:
        if pattern.search(value):
            raise ValidationError(
                {"summary": "Governance text must not contain learner PII."}
            )
    for pattern in HTML_INJECTION_PATTERNS:
        if pattern.search(value):
            raise ValidationError(
                {"summary": "Governance text must not contain executable HTML."}
            )
