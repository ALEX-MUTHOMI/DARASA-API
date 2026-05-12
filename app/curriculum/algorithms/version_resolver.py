from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol


class PublicationLike(Protocol):
    effective_from: date
    effective_to: date | None
    is_active: bool
    superseded_by_id: object | None


def resolve_publication_for_date(
    publications: Iterable[PublicationLike],
    *,
    on_date: date,
) -> PublicationLike | None:
    candidates = [
        publication
        for publication in publications
        if publication.is_active
        and publication.superseded_by_id is None
        and publication.effective_from <= on_date
        and (publication.effective_to is None or publication.effective_to >= on_date)
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: item.effective_from,
        reverse=True,
    )[0]
