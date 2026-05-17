from __future__ import annotations

import inspect
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from core.policies import PolicyContext
from curriculum.models import (
    AssessmentRubricFoundation,
    CurriculumLearningArea,
    CurriculumPublication,
    CurriculumSourceDocument,
    CurriculumVersion,
    SchoolCurriculumAdoption,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)
from grading.models import Assessment, GradeRecord
from grading.policies import can_enter_grades, can_submit_grade_batch
from grading.selectors import get_assessment_for_teacher, get_teacher_grading_contexts
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_second_curriculum_context(
    *,
    curriculum_source_document,
    grade_level,
    learning_area,
):
    source = CurriculumSourceDocument.objects.create(
        authority=curriculum_source_document.authority,
        source_authority=curriculum_source_document.source_authority,
        title=f"Second curriculum {_code('doc')}",
        document_code=_code("doc"),
        source_url="https://kicd.ac.ke/curriculum-designs",
        document_version_label=_code("v"),
        checksum="second-fixture-checksum",
    )
    version = CurriculumVersion.objects.create(
        source_document=source,
        version_label=_code("version"),
        effective_from="2027-01-01",
    )
    CurriculumPublication.objects.create(
        curriculum_version=version,
        effective_from="2027-01-01",
        publication_notes="Approved later curriculum fixture.",
    )
    SchoolCurriculumAdoption.objects.create(
        tenant=learning_area.tenant,
        curriculum_version=version,
        effective_from="2027-01-01",
        status=SchoolCurriculumAdoption.Status.ACTIVE,
        notes="Fixture adoption for historical binding tests.",
    )
    area = CurriculumLearningArea.objects.create(
        curriculum_version=version,
        grade_level=grade_level,
        learning_area=learning_area,
        official_name="Computer Studies",
        official_code=_code("cs"),
    )
    strand = Strand.objects.create(
        curriculum_learning_area=area,
        title=f"Second strand {_code('strand')}",
    )
    sub_strand = SubStrand.objects.create(
        strand=strand,
        title=f"Second sub-strand {_code('sub')}",
    )
    outcome = SpecificLearningOutcome.objects.create(
        sub_strand=sub_strand,
        text=f"Second outcome {_code('outcome')}",
    )
    rubric = AssessmentRubricFoundation.objects.create(
        learning_outcome=outcome,
        level_code=_code("level"),
        level_label="Meets expectation",
        descriptor="Demonstrates the assessed competency.",
    )
    return version, rubric


def test_draft_assessment_may_be_unbound_but_cannot_receive_submitted_batch(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    learning_area,
    principal_user,
    teacher_user,
    teacher_assignment,
):
    draft = Assessment.objects.create(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=learning_area,
        title="Draft without CCT binding",
        max_score=Decimal("100.00"),
        status=Assessment.Status.DRAFT,
        created_by=principal_user,
    )

    assert draft.curriculum_version_id is None
    assert draft.rubric_foundation_id is None
    with pytest.raises(ValidationError):
        build_submission_batch(
            tenant=school,
            actor=teacher_user,
            assessment=draft,
            teacher_assignment=teacher_assignment,
            idempotency_key="draft-submit",
        )


def test_open_assessment_requires_published_curriculum_and_rubric(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    learning_area,
    curriculum_version,
    curriculum_publication,
    curriculum_rubric_foundation,
    principal_user,
):
    base = {
        "tenant": school,
        "academic_year": academic_year,
        "term": term,
        "grade_level": grade_level,
        "cohort": cohort,
        "learning_area": learning_area,
        "title": "Binding check",
        "max_score": Decimal("100.00"),
        "status": Assessment.Status.OPEN,
        "created_by": principal_user,
    }

    with pytest.raises(ValidationError):
        Assessment(**base).full_clean()

    with pytest.raises(ValidationError):
        Assessment(**base, curriculum_version=curriculum_version).full_clean()

    assessment = Assessment.objects.create(
        **base,
        curriculum_version=curriculum_version,
        rubric_foundation=curriculum_rubric_foundation,
    )
    assert assessment.curriculum_binding_locked_at is not None
    assert assessment.is_operationally_bound()


def test_open_assessment_without_learning_area_fails_closed(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    curriculum_version,
    curriculum_publication,
    curriculum_rubric_foundation,
    principal_user,
):
    assessment = Assessment(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=None,
        curriculum_version=curriculum_version,
        rubric_foundation=curriculum_rubric_foundation,
        title="Missing area",
        max_score=Decimal("100.00"),
        status=Assessment.Status.OPEN,
        created_by=principal_user,
    )

    with pytest.raises(ValidationError):
        assessment.full_clean()


def test_policy_denies_unbound_or_unassigned_operational_assessment(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
):
    context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="grading.grades.enter",
        role=subject_teacher_role,
    )
    assert can_enter_grades(context, assessment=assessment)

    Assessment.objects.filter(pk=assessment.pk).update(
        curriculum_binding_locked_at=None,
    )
    assessment.refresh_from_db()
    assert not can_enter_grades(context, assessment=assessment)
    assert not can_submit_grade_batch(
        PolicyContext(
            tenant=school,
            actor=teacher_user,
            action="grading.batch.submit",
            role=subject_teacher_role,
        ),
        assessment=assessment,
    )

    teacher_assignment.is_active = False
    teacher_assignment.save()
    assessment.curriculum_binding_locked_at = None
    assert not can_enter_grades(context, assessment=assessment)


def test_teacher_grade_entry_selectors_exclude_unbound_assessments(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
):
    assert list(get_teacher_grading_contexts(actor=teacher_user, tenant=school)) == [
        assessment
    ]
    assert (
        get_assessment_for_teacher(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )
        == assessment
    )

    Assessment.objects.filter(pk=assessment.pk).update(
        curriculum_binding_locked_at=None,
    )
    assert list(get_teacher_grading_contexts(actor=teacher_user, tenant=school)) == []
    assert (
        get_assessment_for_teacher(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )
        is None
    )


def test_curriculum_context_cannot_change_after_grading_begins(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    curriculum_source_document,
    grade_level,
    learning_area,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="historical-batch",
    )
    build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("80.00"),
    )
    original_version_id = assessment.curriculum_version_id
    original_rubric_id = assessment.rubric_foundation_id
    later_version, later_rubric = _create_second_curriculum_context(
        curriculum_source_document=curriculum_source_document,
        grade_level=grade_level,
        learning_area=learning_area,
    )

    assessment.curriculum_version = later_version
    with pytest.raises(ValidationError):
        assessment.full_clean()

    assessment.refresh_from_db()
    assessment.rubric_foundation = later_rubric
    with pytest.raises(ValidationError):
        assessment.full_clean()

    assessment.refresh_from_db()
    assert assessment.curriculum_version_id == original_version_id
    assert assessment.rubric_foundation_id == original_rubric_id
    assert GradeRecord.objects.get(assessment=assessment).assessment_id == assessment.id


def test_later_curriculum_publication_does_not_rebind_existing_assessment(
    assessment,
    curriculum_source_document,
    grade_level,
    learning_area,
):
    original_version_id = assessment.curriculum_version_id

    _create_second_curriculum_context(
        curriculum_source_document=curriculum_source_document,
        grade_level=grade_level,
        learning_area=learning_area,
    )

    assessment.refresh_from_db()
    assert assessment.curriculum_version_id == original_version_id
    assert assessment.is_operationally_bound()


def test_grade_record_validation_does_not_call_cct_source_hot_path():
    source = inspect.getsource(GradeRecord.clean)

    forbidden = [
        "CurriculumPublication",
        "source_url",
        "change_detector",
        "source_fingerprint",
        "ssrf",
        "artifact",
    ]
    assert all(term not in source for term in forbidden)
