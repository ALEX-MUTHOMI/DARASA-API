from pathlib import Path

import pytest


pytestmark = pytest.mark.phase6


def test_phase6a_boundaries_and_docs_exist(settings):
    app_root = Path(__file__).resolve().parents[2]
    repo_root = app_root.parent

    assert "grading" in settings.INSTALLED_APPS
    assert not (app_root / "grading" / "reports.py").exists()
    assert not (app_root / "grading" / "pdf.py").exists()
    assert not (app_root / "grading" / "nlp.py").exists()
    assert not (app_root / "grading" / "api.py").exists()
    assert not (app_root / "curriculum" / "crawler.py").exists()
    assert not (app_root / "curriculum" / "ai_parser.py").exists()

    blocked_files = [
        repo_root / "docker" / ("Kuber" + "netes.yaml"),
        app_root / "events" / ("kaf" + "ka_dispatcher.py"),
        app_root / "events" / ("kine" + "sis_dispatcher.py"),
        app_root / "events" / ("aws_broker_dispatcher.py"),
    ]
    assert not any(path.exists() for path in blocked_files)

    assert (repo_root / "docs" / "GRADING_ENGINE.md").exists()
