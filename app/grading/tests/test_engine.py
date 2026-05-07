import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from grading.algorithms import CBCTranslator
from grading.models import GradeRecord
from grading.services import BatchGradeService

pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


# =============================================================================
# 1. THE ALGORITHM TESTS (Pure Unit)
# =============================================================================


def test_cbc_translator_bounds_and_edge_cases():
    """
    Assert the CBCTranslator correctly maps edges and standard ranges.
    """
    assert CBCTranslator.translate_percentage(100.0) == 4
    assert CBCTranslator.translate_percentage(80.0) == 4
    assert CBCTranslator.translate_percentage(79.9) == 3
    assert CBCTranslator.translate_percentage(65.0) == 3
    assert CBCTranslator.translate_percentage(64.9) == 2
    assert CBCTranslator.translate_percentage(50.0) == 2
    assert CBCTranslator.translate_percentage(49.9) == 1
    assert CBCTranslator.translate_percentage(0.0) == 1


def test_cbc_translator_fails_fast_on_invalid_input():
    """
    Assert the translator strictly enforces bounds via explicit exceptions.
    """
    with pytest.raises(ValueError):
        CBCTranslator.translate_percentage(-0.1)

    with pytest.raises(ValueError):
        CBCTranslator.translate_percentage(100.1)

    with pytest.raises(ValueError):
        CBCTranslator.translate_percentage("80")  # type: ignore


# =============================================================================
# 2. THE IDOR & ADVERSARIAL TESTS
# =============================================================================


def test_batch_service_idor_rejection(
    assessment,
    cohort,
    enrollment_factory,
    student_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    SECURITY GATE (IDOR):
    Teacher A attempts to grade a student they are NOT assigned to.
    The service must hard-fail and save NOTHING.
    """
    teacher_assignment_factory(teacher=teacher_user, cohort=cohort, subject=subject)

    valid_student = student_factory()
    enrollment_factory(student=valid_student, cohort=cohort)

    invalid_student = student_factory()

    payload = [
        {"student_uuid": valid_student.id, "raw_score": 90.0},
        {"student_uuid": invalid_student.id, "raw_score": 85.0},
    ]

    with pytest.raises(PermissionDenied) as exc:
        BatchGradeService.submit_fast_grid_payload(
            teacher_user,
            assessment.id,
            subject.id,
            payload,
        )

    assert "not authorized" in str(exc.value)
    assert GradeRecord.objects.count() == 0


def test_payload_validation_fails_fast(
    assessment,
    cohort,
    enrollment_factory,
    student_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    AUTONOMOUS SECURITY GATE:
    Ensure malformed payloads are caught before touching the database.
    """
    teacher_assignment_factory(teacher=teacher_user, cohort=cohort, subject=subject)
    student = student_factory()
    enrollment_factory(student=student, cohort=cohort)

    payload = [{"student_uuid": student.id, "raw_score": "DROP TABLE students; --"}]

    with pytest.raises(ValidationError) as exc:
        BatchGradeService.submit_fast_grid_payload(
            teacher_user,
            assessment.id,
            subject.id,
            payload,
        )

    assert "Invalid raw_score format" in str(exc.value)


# =============================================================================
# 3. THE O(1) BULK PERFORMANCE TEST
# =============================================================================


def test_o1_bulk_performance_is_constant(
    assessment,
    cohort,
    django_assert_max_num_queries,
    enrollment_factory,
    student_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    PERFORMANCE GATE:
    Assert that submitting 50 grades has a stable DB query count.
    """
    teacher_assignment_factory(teacher=teacher_user, cohort=cohort, subject=subject)

    payload = []
    for i in range(50):
        student = student_factory()
        enrollment_factory(student=student, cohort=cohort)
        payload.append(
            {
                "student_uuid": student.id,
                "raw_score": float(i + 50) % 100,
            }
        )

    with django_assert_max_num_queries(4):
        processed = BatchGradeService.submit_fast_grid_payload(
            teacher_user,
            assessment.id,
            subject.id,
            payload,
        )

    assert processed == 50
    assert GradeRecord.objects.count() == 50


def test_occ_versioning_upsert(
    assessment,
    cohort,
    enrollment_factory,
    student_factory,
    subject,
    teacher_assignment_factory,
    teacher_user,
):
    """
    AUTONOMOUS CONCURRENCY GATE:
    Verify that update_conflicts successfully overwrites existing grades
    without causing IntegrityErrors (UniqueConstraint violations).
    """
    teacher_assignment_factory(teacher=teacher_user, cohort=cohort, subject=subject)
    student = student_factory()
    enrollment_factory(student=student, cohort=cohort)

    payload_initial = [{"student_uuid": student.id, "raw_score": 50.0}]
    BatchGradeService.submit_fast_grid_payload(
        teacher_user,
        assessment.id,
        subject.id,
        payload_initial,
    )

    assert GradeRecord.objects.get(student=student).cbc_score == 2

    payload_update = [{"student_uuid": student.id, "raw_score": 90.0}]
    BatchGradeService.submit_fast_grid_payload(
        teacher_user,
        assessment.id,
        subject.id,
        payload_update,
    )

    assert GradeRecord.objects.count() == 1
    assert GradeRecord.objects.get(student=student).cbc_score == 4
