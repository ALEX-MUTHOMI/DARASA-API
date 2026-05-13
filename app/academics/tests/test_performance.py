import pytest

from academics.selectors import get_cohort_roster, verify_teacher_assignment


pytestmark = [pytest.mark.django_db, pytest.mark.phase3]


def test_roster_selector_uses_bounded_queries(
    cohort,
    django_assert_max_num_queries,
    enrollment_factory,
    learning_area,
    school,
    teacher_assignment_factory,
    teacher_user,
):
    teacher_assignment_factory(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
    )
    enrollment_factory.create_batch(50, tenant=school, cohort=cohort)

    with django_assert_max_num_queries(2):
        roster = get_cohort_roster(
            tenant=school,
            actor=teacher_user,
            cohort=cohort,
            learning_area=learning_area,
        )

    assert len(roster) == 50
    assert {"id", "first_name", "last_name", "admission_number"} <= set(roster[0])


def test_teacher_assignment_verification_uses_bounded_queries(
    cohort,
    django_assert_max_num_queries,
    learning_area,
    school,
    teacher_assignment_factory,
    teacher_user,
):
    teacher_assignment_factory(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=learning_area,
    )

    with django_assert_max_num_queries(1):
        assert verify_teacher_assignment(
            tenant=school,
            teacher=teacher_user,
            cohort=cohort,
            learning_area=learning_area,
        )
