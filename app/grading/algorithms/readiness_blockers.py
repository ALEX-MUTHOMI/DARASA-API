from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessBlocker:
    code: str
    severity: str
    message: str
    scope: str
    resource_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def blocker(
    *,
    code: str,
    message: str,
    scope: str = "assessment",
    severity: str = "blocking",
    resource_id: Any = "",
) -> ReadinessBlocker:
    return ReadinessBlocker(
        code=code,
        severity=severity,
        message=message,
        scope=scope,
        resource_id=str(resource_id or ""),
    )


def blocker_dicts(blockers: list[ReadinessBlocker]) -> list[dict[str, str]]:
    return [item.to_dict() for item in blockers]


def blocker_codes(blockers: list[ReadinessBlocker]) -> set[str]:
    return {item.code for item in blockers}
