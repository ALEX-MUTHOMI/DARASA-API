import pytest

from academics.selectors import get_fast_grid_roster

pytestmark = [pytest.mark.django_db, pytest.mark.phase3]


def test_fast_grid_roster_performance_o1_queries(
    cohort,
    django_assert_max_num_queries,
    enrollment_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    MANDATORY PERFORMANCE GATE:
    Asserts that the Fast-Grid roster executes in exactly 2 queries:
    1. Auth verification (exists)
    2. Payload retrieval (.values() join)
    Regardless of roster size (50 students tested here).
    """
    teacher_assignment_factory(
        teacher=teacher_user,
        cohort=cohort,
        subject=subject,
    )
    enrollment_factory.create_batch(50, cohort=cohort)

    with django_assert_max_num_queries(2):
        roster = get_fast_grid_roster(teacher_user, cohort.id, subject.id)

    assert len(roster) == 50
    assert "admission_number" in roster[0]
    assert "first_name" in roster[0]
