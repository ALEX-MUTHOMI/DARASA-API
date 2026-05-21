from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.grading, pytest.mark.boundary]


def test_phase7a_does_not_implement_rendering_or_parent_portal_drift():
    grading_files = [
        path
        for path in Path("app/grading").rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in grading_files)

    forbidden = [
        "render_pdf",
        "generate_pdf",
        "report_card_template",
        "nlp_remark",
        "parent_portal_report",
        "kafka",
        "kinesis",
        "mpesa",
        "daraja",
    ]
    assert not any(token in content.lower() for token in forbidden)
