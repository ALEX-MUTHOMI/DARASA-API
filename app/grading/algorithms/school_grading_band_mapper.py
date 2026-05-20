"""Map raw scores to tenant internal grading bands without touching CBE truth."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class BandMapping:
    raw_score: Decimal
    max_score: Decimal
    normalized_percentage: Decimal
    band_label: str
    band_descriptor: str
    points: Decimal | None


def normalize_percentage(*, raw_score: Any, max_score: Any) -> Decimal:
    raw = Decimal(str(raw_score))
    maximum = Decimal(str(max_score))
    if maximum <= 0:
        raise ValueError("max_score_must_be_positive")
    if raw < 0 or raw > maximum:
        raise ValueError("raw_score_out_of_range")
    return ((raw / maximum) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def map_score_to_band(
    *,
    raw_score: Any,
    max_score: Any,
    bands: list[dict[str, Any]],
) -> BandMapping:
    percentage = normalize_percentage(raw_score=raw_score, max_score=max_score)
    for band in sorted(
        bands,
        key=lambda item: (
            Decimal(str(item["min_percentage"])),
            Decimal(str(item["max_percentage"])),
        ),
    ):
        minimum = Decimal(str(band["min_percentage"]))
        maximum = Decimal(str(band["max_percentage"]))
        if minimum <= percentage <= maximum:
            points = band.get("points")
            return BandMapping(
                raw_score=Decimal(str(raw_score)),
                max_score=Decimal(str(max_score)),
                normalized_percentage=percentage,
                band_label=str(band["label"]),
                band_descriptor=str(band.get("descriptor", "")),
                points=Decimal(str(points)) if points is not None else None,
            )
    raise ValueError("no_matching_band")
