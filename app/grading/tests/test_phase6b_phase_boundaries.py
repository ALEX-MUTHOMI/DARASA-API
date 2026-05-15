from pathlib import Path

import pytest


pytestmark = pytest.mark.phase6


def test_phase6b_boundaries_remain_backend_only():
    app_root = Path(__file__).resolve().parents[2]

    forbidden = [
        app_root / "grading" / "reports.py",
        app_root / "grading" / "pdf.py",
        app_root / "grading" / "nlp.py",
        app_root / "grading" / "api.py",
        app_root / "curriculum" / "crawler.py",
        app_root / "curriculum" / "ai_parser.py",
        app_root / "events" / "kafka_dispatcher.py",
        app_root / "events" / "kinesis_dispatcher.py",
        app_root / "events" / "aws_broker_dispatcher.py",
    ]

    assert not any(path.exists() for path in forbidden)
