from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.phase6, pytest.mark.grading]


def test_phase6e_does_not_add_report_pdf_nlp_frontend_or_cct_upload_drift():
    grading_files = [
        path
        for path in Path("app/grading").rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in grading_files)

    forbidden = [
        "reportlab",
        "WeasyPrint",
        "pdfkit",
        "APIView",
        "ViewSet",
        "urlpatterns",
        "requests.",
        "httpx.",
        "BeautifulSoup",
        "openai",
        "parent portal",
        "mpesa",
        "daraja",
        "kafka",
        "kinesis",
    ]
    assert not [token for token in forbidden if token in combined]
