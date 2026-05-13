"""Build stable partition keys for future national-scale routing.

Phase 5 stays local-first, but every event already needs a deterministic
partition key.  Tenant-scoped facts default to a tenant partition so a future
broker can preserve school locality without changing producers.
"""

from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError


PARTITION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def validate_partition_key(partition_key: str) -> str:
    value = str(partition_key or "").strip()
    if not PARTITION_KEY_PATTERN.fullmatch(value):
        raise ValidationError({"partition_key": "Partition key is invalid."})
    return value


def build_partition_key(
    *,
    tenant_id: Any | None = None,
    event_type: str | None = None,
    region: str | None = None,
    priority: str | None = None,
    requires_tenant: bool = False,
) -> str:
    if requires_tenant and tenant_id is None:
        raise ValidationError({"tenant": "Tenant is required for partitioning."})
    if tenant_id is not None:
        key = f"tenant:{tenant_id}"
    elif region and event_type:
        key = f"region:{region}:event_type:{event_type}"
    elif priority and tenant_id is not None:
        key = f"priority:{priority}:tenant:{tenant_id}"
    elif event_type:
        key = f"event_type:{event_type}"
    else:
        key = "global"
    return validate_partition_key(key)
