from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase6, pytest.mark.grading, pytest.mark.performance]


def test_phase6d_readiness_paths_do_not_query_all_schools_or_all_students():
    root = Path(__file__).resolve().parents[3]
    paths = [
        root / "app" / "grading" / "services.py",
        root / "app" / "grading" / "selectors.py",
        root / "app" / "grading" / "algorithms" / "readiness_status.py",
        root / "app" / "grading" / "algorithms" / "report_readiness_rules.py",
    ]
    forbidden = [
        "School.objects.all",
        "Student.objects.all",
        "Learner.objects.all",
        "all_schools",
        "all_students",
    ]

    for path in paths:
        text = path.read_text()
        for token in forbidden:
            assert token not in text
