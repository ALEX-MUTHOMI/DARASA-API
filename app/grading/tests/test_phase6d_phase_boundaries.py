from __future__ import annotations

from pathlib import Path

import pytest

from grading import services


pytestmark = [pytest.mark.phase6, pytest.mark.grading, pytest.mark.boundary]


def test_phase6d_does_not_implement_reports_pdf_nlp_frontend_or_cct_uploads():
    root = Path(__file__).resolve().parents[3]
    phase6d_files = [
        root / "app" / "grading" / "algorithms" / "readiness_status.py",
        root / "app" / "grading" / "algorithms" / "readiness_blockers.py",
        root / "app" / "grading" / "algorithms" / "report_readiness_rules.py",
        root / "app" / "grading" / "algorithms" / "role_readiness_projection.py",
        root / "app" / "grading" / "services.py",
        root / "app" / "grading" / "selectors.py",
        root / "app" / "grading" / "policies.py",
    ]
    forbidden = [
        "render_pdf",
        "generate_pdf",
        "report_card",
        "nlp_output",
        "parent_portal",
        "upload_evidence",
        "requests.",
        "httpx.",
        "urllib.request",
        "Kafka",
        "Kinesis",
        "M-Pesa",
        "Daraja",
    ]

    for path in phase6d_files:
        text = path.read_text()
        for token in forbidden:
            assert token not in text


def test_phase6d_exports_backend_readiness_contracts_only():
    assert hasattr(services, "compute_assessment_readiness")
    assert hasattr(services, "get_teacher_readiness_projection")
    assert hasattr(services, "get_hod_readiness_projection")
    assert hasattr(services, "get_deputy_academics_readiness_projection")
    assert hasattr(services, "get_principal_readiness_projection")
    assert hasattr(services, "get_future_parent_report_readiness_projection")
