from __future__ import annotations

from typing import Any


def evaluate_report_eligibility(readiness: dict[str, Any]) -> dict[str, Any]:
    blocker_codes = sorted(
        {
            str(blocker.get("code", "unknown_blocker"))
            for blocker in readiness.get("blockers", [])
            if blocker.get("severity", "blocking") == "blocking"
        }
    )
    compilation_status = str(readiness.get("compilation_status") or "not_started")
    readiness_status = str(readiness.get("readiness_status") or "unknown")
    pending_corrections = int(readiness.get("pending_correction_count") or 0)
    compilation_run_id = str(readiness.get("compilation_run_id") or "")

    if not compilation_run_id:
        blocker_codes.append("compilation_missing")
    if compilation_status != "complete":
        blocker_codes.append(f"compilation_{compilation_status}")
    if readiness_status != "ready_for_reports":
        blocker_codes.append(f"readiness_{readiness_status}")
    if pending_corrections > 0:
        blocker_codes.append("correction_unresolved")
    if not readiness.get("report_ready", False):
        blocker_codes.append("readiness_not_cleared")

    blocker_codes = sorted(set(blocker_codes))
    return {
        "eligible": not blocker_codes,
        "status": "eligible" if not blocker_codes else "blocked",
        "readiness_status": readiness_status,
        "compilation_status": compilation_status,
        "compilation_run_id": compilation_run_id,
        "assessment_id": str(readiness.get("assessment_id") or ""),
        "cohort_id": str(readiness.get("cohort_id") or ""),
        "learning_area_id": str(readiness.get("learning_area_id") or ""),
        "blocker_codes": blocker_codes,
    }


def summarize_eligibility(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_count = len([result for result in results if result.get("eligible")])
    blocked_count = len(results) - eligible_count
    blocker_counts: dict[str, int] = {}
    for result in results:
        for code in result.get("blocker_codes", []):
            blocker_counts[code] = blocker_counts.get(code, 0) + 1
    return {
        "assessment_count": len(results),
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "all_eligible": bool(results) and blocked_count == 0,
        "blocker_counts": dict(sorted(blocker_counts.items())),
    }
