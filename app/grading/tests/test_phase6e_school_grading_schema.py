from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from grading.models import Assessment
from grading.services import (
    activate_school_grading_schema,
    bind_schema_to_assessment,
    create_school_grading_schema,
    deprecate_school_grading_schema,
    map_score_to_school_band,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _bands():
    return [
        {
            "label": "D",
            "descriptor": "Developing",
            "min_percentage": "0.00",
            "max_percentage": "39.99",
        },
        {
            "label": "C",
            "descriptor": "Approaching",
            "min_percentage": "40.00",
            "max_percentage": "59.99",
        },
        {
            "label": "B",
            "descriptor": "Meeting",
            "min_percentage": "60.00",
            "max_percentage": "79.99",
        },
        {
            "label": "A",
            "descriptor": "Exceeding",
            "min_percentage": "80.00",
            "max_percentage": "100.00",
        },
    ]


def test_school_schema_binds_to_internal_assessment_without_overriding_cbe(
    school,
    assessment,
    principal_user,
):
    Assessment.objects.filter(id=assessment.id).update(
        assessment_type=Assessment.AssessmentType.CAT,
        max_score=Decimal("15.00"),
    )
    assessment.refresh_from_db()
    original_curriculum_version = assessment.curriculum_version_id
    original_rubric = assessment.rubric_foundation_id
    schema = create_school_grading_schema(
        actor=principal_user,
        tenant=school,
        payload={
            "name": "CAT 15 point schema",
            "assessment_type": Assessment.AssessmentType.CAT,
            "version_label": "cat-v1",
            "bands": _bands(),
        },
    )
    activate_school_grading_schema(
        actor=principal_user,
        tenant=school,
        schema_id=schema.id,
    )

    assessment = bind_schema_to_assessment(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
        schema_id=schema.id,
    )
    mapping = map_score_to_school_band(
        tenant=school,
        assessment=assessment,
        raw_score=Decimal("12.00"),
    )

    assert mapping["normalized_score"] == "80.00"
    assert mapping["band_label"] == "A"
    assert assessment.school_grading_schema_version == "cat-v1"
    assert assessment.curriculum_version_id == original_curriculum_version
    assert assessment.rubric_foundation_id == original_rubric


def test_same_raw_score_has_different_meaning_under_different_max_scores(
    school,
    assessment,
    principal_user,
):
    Assessment.objects.filter(id=assessment.id).update(
        assessment_type=Assessment.AssessmentType.CAT,
        max_score=Decimal("15.00"),
    )
    assessment.refresh_from_db()
    schema = create_school_grading_schema(
        actor=principal_user,
        tenant=school,
        payload={
            "name": "CAT 15 point schema",
            "assessment_type": Assessment.AssessmentType.CAT,
            "version_label": "cat-v2",
            "bands": _bands(),
        },
    )
    activate_school_grading_schema(
        actor=principal_user,
        tenant=school,
        schema_id=schema.id,
    )
    assessment = bind_schema_to_assessment(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
        schema_id=schema.id,
    )

    school_a_mapping = map_score_to_school_band(
        tenant=school,
        assessment=assessment,
        raw_score=Decimal("12.00"),
    )
    Assessment.objects.filter(id=assessment.id).update(max_score=Decimal("30.00"))
    assessment.refresh_from_db()
    school_b_style_mapping = map_score_to_school_band(
        tenant=school,
        assessment=assessment,
        raw_score=Decimal("12.00"),
    )

    assert school_a_mapping["normalized_score"] == "80.00"
    assert school_b_style_mapping["normalized_score"] == "40.00"


def test_schema_rejects_overlapping_bands_and_deprecated_binding(
    school,
    assessment,
    principal_user,
):
    with pytest.raises(ValidationError):
        create_school_grading_schema(
            actor=principal_user,
            tenant=school,
            payload={
                "name": "Invalid schema",
                "assessment_type": Assessment.AssessmentType.CAT,
                "version_label": "bad-v1",
                "bands": [
                    {"label": "B", "min_percentage": "0.00", "max_percentage": "60.00"},
                    {
                        "label": "A",
                        "min_percentage": "50.00",
                        "max_percentage": "100.00",
                    },
                ],
            },
        )

    Assessment.objects.filter(id=assessment.id).update(
        assessment_type=Assessment.AssessmentType.CAT,
    )
    assessment.refresh_from_db()
    schema = create_school_grading_schema(
        actor=principal_user,
        tenant=school,
        payload={
            "name": "CAT schema",
            "assessment_type": Assessment.AssessmentType.CAT,
            "version_label": "cat-v3",
            "bands": _bands(),
        },
    )
    activate_school_grading_schema(
        actor=principal_user,
        tenant=school,
        schema_id=schema.id,
    )
    deprecate_school_grading_schema(
        actor=principal_user,
        tenant=school,
        schema_id=schema.id,
    )

    with pytest.raises(ValidationError):
        bind_schema_to_assessment(
            actor=principal_user,
            tenant=school,
            assessment_id=assessment.id,
            schema_id=schema.id,
        )


def test_schema_cannot_bind_to_cbe_rubric_assessment(
    school,
    assessment,
    principal_user,
):
    Assessment.objects.filter(id=assessment.id).update(
        assessment_type=Assessment.AssessmentType.CBE_RUBRIC_ASSESSMENT,
    )
    assessment.refresh_from_db()
    schema = create_school_grading_schema(
        actor=principal_user,
        tenant=school,
        payload={
            "name": "CBE override attempt",
            "assessment_type": Assessment.AssessmentType.CBE_RUBRIC_ASSESSMENT,
            "version_label": "cbe-v1",
            "bands": _bands(),
        },
    )
    activate_school_grading_schema(
        actor=principal_user,
        tenant=school,
        schema_id=schema.id,
    )

    with pytest.raises(ValidationError):
        bind_schema_to_assessment(
            actor=principal_user,
            tenant=school,
            assessment_id=assessment.id,
            schema_id=schema.id,
        )
