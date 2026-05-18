from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


REFERENCE_PATTERN = re.compile(
    r"^[A-Z]{2,8}[/.-][A-Z0-9]{2,16}[/.-]\d{4}([/.-]\d{1,6})?$"
)
PUBLICATION_PATTERN = re.compile(r"^[A-Z0-9]{2,12}[/.-]\d{4}([/.-]\d{1,6})?$")


@dataclass(frozen=True)
class DocumentSignalReport:
    reference_number_detected: bool
    reference_number_valid: bool
    publication_number_detected: bool
    publication_number_valid: bool
    publication_date_detected: bool
    effective_date_detected: bool
    stamp_signal: bool
    signature_signal: bool
    template_signal: bool
    risk_flags: tuple[str, ...]
    missing_evidence: tuple[str, ...]


def _valid_reference(value: str) -> bool:
    return bool(REFERENCE_PATTERN.fullmatch(value.strip().upper()))


def _valid_publication(value: str) -> bool:
    return bool(PUBLICATION_PATTERN.fullmatch(value.strip().upper()))


def validate_document_signals(
    *,
    claimed_reference_number: str = "",
    claimed_publication_number: str = "",
    claimed_publication_date: date | None = None,
    claimed_effective_date: date | None = None,
    stamp_signal: bool = False,
    signature_signal: bool = False,
    template_signal: bool = False,
) -> DocumentSignalReport:
    risks: list[str] = []
    missing: list[str] = []

    reference_detected = bool(str(claimed_reference_number).strip())
    reference_valid = (
        _valid_reference(claimed_reference_number) if reference_detected else False
    )
    if not reference_detected:
        missing.append("reference_number")
    elif not reference_valid:
        risks.append("invalid_reference_number_format")

    publication_detected = bool(str(claimed_publication_number).strip())
    publication_valid = (
        _valid_publication(claimed_publication_number)
        if publication_detected
        else False
    )
    if publication_detected and not publication_valid:
        risks.append("invalid_publication_number_format")

    publication_date_detected = claimed_publication_date is not None
    effective_date_detected = claimed_effective_date is not None
    if not publication_date_detected:
        missing.append("publication_date")
    if not effective_date_detected:
        missing.append("effective_date")
    if (
        publication_date_detected
        and effective_date_detected
        and claimed_effective_date < claimed_publication_date
    ):
        risks.append("effective_date_before_publication_date")

    if not stamp_signal:
        missing.append("stamp_signal")
    if not signature_signal:
        missing.append("signature_signal")

    return DocumentSignalReport(
        reference_number_detected=reference_detected,
        reference_number_valid=reference_valid,
        publication_number_detected=publication_detected,
        publication_number_valid=publication_valid,
        publication_date_detected=publication_date_detected,
        effective_date_detected=effective_date_detected,
        stamp_signal=stamp_signal,
        signature_signal=signature_signal,
        template_signal=template_signal,
        risk_flags=tuple(risks),
        missing_evidence=tuple(missing),
    )
