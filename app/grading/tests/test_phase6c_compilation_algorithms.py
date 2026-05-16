from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from grading.algorithms.cbe_band_mapper import map_cbe_band
from grading.algorithms.cohort_summary_builder import build_cohort_summary
from grading.algorithms.component_summary import build_component_summary
from grading.algorithms.compilation_status import determine_compilation_status
from grading.algorithms.missing_marks import detect_missing_marks
from grading.algorithms.score_summary import percentage


pytestmark = pytest.mark.phase6


class Component:
    def __init__(self, component_id, max_score="10.00", required=True):
        self.id = component_id
        self.max_score = Decimal(max_score)
        self.is_required = required
        self.rubric_foundation_id = "rubric-1"


class Record:
    def __init__(self, student_id, component_scores=None):
        self.student_id = student_id
        self.component_scores = component_scores or {}


def test_missing_marks_detects_missing_components_and_roster_gaps():
    component = Component("component-1")
    findings = detect_missing_marks(
        roster_student_ids={"learner-1", "learner-2"},
        grade_records=[Record("learner-1", {})],
        components=[component],
    )

    assert {item["code"] for item in findings} == {
        "missing_required_component",
        "missing_learner_mark",
    }


def test_score_and_component_summaries_are_deterministic():
    assert percentage(Decimal("25.00"), Decimal("50.00")) == Decimal("50.00")

    summary = build_component_summary(
        component_scores={"component-1": "8.00"},
        components=[Component("component-1")],
        assessment_max_score=Decimal("20.00"),
    )

    assert summary["component_total"] == "8.00"
    assert summary["components"][0]["component_id"] == "component-1"


def test_component_summary_rejects_invalid_scores():
    with pytest.raises(ValidationError):
        build_component_summary(
            component_scores={"component-1": "11.00"},
            components=[Component("component-1")],
            assessment_max_score=Decimal("20.00"),
        )


def test_cbe_band_mapping_is_conservative():
    mapped = map_cbe_band(rubric_foundation_id="rubric-1")

    assert mapped["status"] == "unresolved_due_to_missing_rubric_mapping"
    assert mapped["resolved_band"] is None


def test_cohort_summary_and_status_rules():
    summary = build_cohort_summary(
        assessment=type(
            "Assessment",
            (),
            {
                "tenant_id": "tenant-1",
                "id": "assessment-1",
                "cohort_id": "cohort-1",
                "learning_area_id": "learning-area-1",
            },
        )(),
        expected_count=4,
        submitted_count=3,
        missing_count=1,
        component_summary={"component_count": 0},
        status="partial",
    )

    assert summary["completion_percentage"] == "75.00"
    assert determine_compilation_status(
        missing_marks=[{"code": "missing_learner_mark"}],
        invalid_records=[],
        has_submitted_records=True,
    ) == "partial"
