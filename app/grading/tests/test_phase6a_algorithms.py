from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from grading.algorithms.correction_hash import hash_grade_state
from grading.algorithms.grading_context import build_grading_context_identity
from grading.algorithms.score_bounds import validate_score_bounds


pytestmark = pytest.mark.phase6


def test_score_bounds_reject_invalid_scores():
    assert validate_score_bounds(score=Decimal("50"), max_score=Decimal("100")) == 50

    with pytest.raises(ValidationError):
        validate_score_bounds(score=-1, max_score=100)
    with pytest.raises(ValidationError):
        validate_score_bounds(score=101, max_score=100)
    with pytest.raises(ValidationError):
        validate_score_bounds(score=1, max_score=0)
    with pytest.raises(ValidationError):
        validate_score_bounds(score="not-a-score", max_score=100)


def test_correction_hash_is_deterministic():
    state = {"grade_record_id": "record-1", "raw_score": "80.00", "version": 1}

    assert hash_grade_state(state) == hash_grade_state(dict(reversed(state.items())))
    assert hash_grade_state(state) != hash_grade_state(
        {"grade_record_id": "record-1", "raw_score": "81.00", "version": 1}
    )


def test_grading_context_identity_is_stable():
    context = build_grading_context_identity(
        tenant_id="tenant-1",
        teacher_id="teacher-1",
        assessment_id="assessment-1",
        cohort_id="cohort-1",
        learning_area_id="area-1",
        academic_year_id="year-1",
        term_id="term-1",
    )

    assert context.key == (
        "tenant:tenant-1:teacher:teacher-1:assessment:assessment-1:"
        "cohort:cohort-1:learning_area:area-1:year:year-1:term:term-1"
    )

    with pytest.raises(ValidationError):
        build_grading_context_identity(
            tenant_id="tenant-1",
            teacher_id="",
            assessment_id="assessment-1",
            cohort_id="cohort-1",
            learning_area_id="area-1",
            academic_year_id="year-1",
            term_id="term-1",
        )
