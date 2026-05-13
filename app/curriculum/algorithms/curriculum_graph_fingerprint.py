from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def stable_graph_hash(payload: Mapping[str, Any] | list[Mapping[str, Any]]) -> str:
    canonical = json.dumps(
        _canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_node(*, entity_type: str, values: Mapping[str, Any]) -> str:
    return stable_graph_hash({"entity_type": entity_type, "values": dict(values)})


def fingerprint_curriculum_version(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="curriculum_version", values=values)


def fingerprint_learning_area(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="learning_area", values=values)


def fingerprint_strand(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="strand", values=values)


def fingerprint_sub_strand(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="sub_strand", values=values)


def fingerprint_outcome(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="outcome", values=values)


def fingerprint_rubric_foundation(values: Mapping[str, Any]) -> str:
    return fingerprint_node(entity_type="rubric_foundation", values=values)
