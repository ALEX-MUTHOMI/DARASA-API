from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from curriculum.algorithms.curriculum_graph_fingerprint import fingerprint_node


ASSESSMENT_ENTITY_TYPES = frozenset(
    {"rubric_foundation", "assessment_guidance", "teacher_training_notice"}
)


def _node_key(node: Mapping[str, Any]) -> str:
    entity_type = str(node.get("entity_type", "")).strip()
    identifier = str(node.get("identifier", "")).strip()
    return f"{entity_type}:{identifier}"


def _node_fingerprint(node: Mapping[str, Any]) -> str:
    if node.get("fingerprint"):
        return str(node["fingerprint"])
    return fingerprint_node(
        entity_type=str(node.get("entity_type", "")),
        values={
            key: value
            for key, value in node.items()
            if key not in {"fingerprint", "identifier", "entity_type"}
        },
    )


def _change_type(old: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    old_active = old.get("is_active", True)
    new_active = new.get("is_active", True)
    if old_active and not new_active:
        return "retired"
    if not old_active and new_active:
        return "reactivated"
    if old.get("effective_date") != new.get("effective_date"):
        return "effective_date_changed"
    if new.get("entity_type") in ASSESSMENT_ENTITY_TYPES:
        return "assessment_criteria_changed"
    if old.get("title") != new.get("title") or old.get("name") != new.get("name"):
        return "renamed"
    return "updated"


def diff_graph_snapshots(
    old_snapshot: Iterable[Mapping[str, Any]],
    new_snapshot: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_nodes = {_node_key(node): node for node in old_snapshot}
    new_nodes = {_node_key(node): node for node in new_snapshot}
    diff_items: list[dict[str, Any]] = []

    for key in sorted(set(old_nodes) | set(new_nodes)):
        old = old_nodes.get(key)
        new = new_nodes.get(key)
        if old is None and new is not None:
            diff_items.append(
                {
                    "change_type": "added",
                    "entity_type": new.get("entity_type"),
                    "entity_identifier": new.get("identifier"),
                    "old_value_fingerprint": "",
                    "new_value_fingerprint": _node_fingerprint(new),
                    "summary": f"Added {new.get('entity_type')}.",
                }
            )
            continue
        if new is None and old is not None:
            diff_items.append(
                {
                    "change_type": "removed",
                    "entity_type": old.get("entity_type"),
                    "entity_identifier": old.get("identifier"),
                    "old_value_fingerprint": _node_fingerprint(old),
                    "new_value_fingerprint": "",
                    "summary": f"Removed {old.get('entity_type')}.",
                }
            )
            continue
        if old is None or new is None:
            continue
        old_fingerprint = _node_fingerprint(old)
        new_fingerprint = _node_fingerprint(new)
        if old_fingerprint == new_fingerprint:
            continue
        diff_items.append(
            {
                "change_type": _change_type(old, new),
                "entity_type": new.get("entity_type"),
                "entity_identifier": new.get("identifier"),
                "old_value_fingerprint": old_fingerprint,
                "new_value_fingerprint": new_fingerprint,
                "summary": f"Updated {new.get('entity_type')}.",
            }
        )
    return diff_items
