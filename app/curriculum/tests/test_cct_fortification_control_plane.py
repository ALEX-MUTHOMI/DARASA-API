from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from academics.models import Term
from core.models import TenantUserRole
from core.policies import PolicyContext
from curriculum.algorithms.dependency_guards import (
    validate_grading_dependency_state,
    validate_historical_dependency_state,
)
from curriculum.algorithms.notice_batch_planning import plan_notice_batch
from curriculum.algorithms.rollback_planning import plan_assessment_rebind_eligibility
from curriculum.algorithms.rollout_planning import plan_rollout_batches
from curriculum.models import (
    AssessmentRubricFoundation,
    CurriculumNoticeBatchRun,
    CurriculumPublication,
    CurriculumRollbackPlan,
    CurriculumVersionWithdrawal,
    SchoolCurriculumAdoption,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)
from curriculum.policies import (
    can_plan_curriculum_rollback,
    can_resolve_dependent_app_context,
    can_schedule_school_adoption,
)
from curriculum.selectors import (
    get_active_school_curriculum_adoption,
    get_curriculum_notice_batch_runs,
    get_curriculum_rollback_plans,
    get_school_adoption_status,
    get_withdrawn_curriculum_versions,
)
from curriculum.services import (
    create_curriculum_publication,
    create_notice_batch_run,
    mark_curriculum_version_withdrawn,
    plan_curriculum_rollback,
    schedule_school_curriculum_adoption,
    validate_curriculum_context_for_compilation_dependency,
    validate_curriculum_context_for_grading_binding,
    validate_curriculum_context_for_reporting_dependency,
)
from events.models import EventOutbox, EventTypeRegistry
from grading.models import Assessment


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def _publish(curriculum_version, principal_user) -> CurriculumPublication:
    return create_curriculum_publication(
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        publication_notes="Reviewed publication for controlled school adoption.",
        approved_by=principal_user,
        workflow_approved=True,
    )


def _rubric(curriculum_learning_area) -> AssessmentRubricFoundation:
    strand = Strand.objects.create(
        curriculum_learning_area=curriculum_learning_area,
        title="Controlled CCT strand",
    )
    sub_strand = SubStrand.objects.create(
        strand=strand,
        title="Controlled CCT sub-strand",
    )
    outcome = SpecificLearningOutcome.objects.create(
        sub_strand=sub_strand,
        text="Demonstrate controlled curriculum dependency.",
    )
    return AssessmentRubricFoundation.objects.create(
        learning_outcome=outcome,
        level_code="meeting",
        level_label="Meeting expectation",
        descriptor="Controlled rubric context.",
        sequence_order=1,
    )


def _term(school, academic_year) -> Term:
    return Term.objects.create(
        tenant=school,
        academic_year=academic_year,
        code=Term.TermCode.TERM_1,
        name="Term 1",
        start_date="2026-01-01",
        end_date="2026-04-01",
    )


def _assessment(
    *,
    school,
    academic_year,
    cohort,
    learning_area,
    curriculum_version,
    rubric,
) -> Assessment:
    return Assessment.objects.create(
        tenant=school,
        academic_year=academic_year,
        term=_term(school, academic_year),
        grade_level=cohort.grade_level,
        cohort=cohort,
        learning_area=learning_area,
        curriculum_version=curriculum_version,
        rubric_foundation=rubric,
        title="CCT-bound operational assessment",
        assessment_type=Assessment.AssessmentType.EXAM,
        max_score=Decimal("100.00"),
        status=Assessment.Status.OPEN,
    )


def test_cct_fortification_migration_and_models_use_uuid_primary_keys(app_root):
    assert (
        app_root
        / "curriculum"
        / "migrations"
        / "0004_cct_fortification_control_plane.py"
    ).exists()

    for model in [
        SchoolCurriculumAdoption,
        CurriculumVersionWithdrawal,
        CurriculumRollbackPlan,
        CurriculumNoticeBatchRun,
    ]:
        assert model._meta.pk.__class__.__name__ == "UUIDField"


def test_adoption_requires_published_version_and_is_tenant_specific(
    curriculum_version,
    principal_user,
    school,
):
    with pytest.raises(ValidationError):
        schedule_school_curriculum_adoption(
            tenant=school,
            curriculum_version=curriculum_version,
            effective_from=date(2026, 1, 1),
            scheduled_by=principal_user,
        )

    _publish(curriculum_version, principal_user)
    adoption = schedule_school_curriculum_adoption(
        tenant=school,
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        scheduled_by=principal_user,
        notes="School adopts after principal review.",
    )

    assert adoption.status == SchoolCurriculumAdoption.Status.SCHEDULED
    assert get_active_school_curriculum_adoption(
        tenant=school,
        curriculum_version=curriculum_version,
    ) == adoption
    assert list(get_school_adoption_status(tenant=school)) == [adoption]


def test_withdrawn_version_blocks_new_adoption_and_emits_reference_event(
    curriculum_version,
    django_capture_on_commit_callbacks,
    principal_user,
    school,
):
    _publish(curriculum_version, principal_user)
    with django_capture_on_commit_callbacks(execute=True):
        withdrawal = mark_curriculum_version_withdrawn(
            curriculum_version=curriculum_version,
            withdrawn_by=principal_user,
            reason="Official source withdrew this curriculum version.",
        )

    assert list(get_withdrawn_curriculum_versions()) == [withdrawal]
    with pytest.raises(ValidationError):
        schedule_school_curriculum_adoption(
            tenant=school,
            curriculum_version=curriculum_version,
            effective_from=date(2026, 1, 1),
            scheduled_by=principal_user,
        )

    event = EventOutbox.objects.get(event_type="curriculum.version_withdrawn")
    assert event.event_version == 1
    assert event.payload == {
        "curriculum_version_id": str(curriculum_version.id),
        "withdrawal_id": str(withdrawal.id),
        "withdrawn_at": withdrawal.withdrawn_at.isoformat(),
    }


def test_grading_dependency_guard_requires_school_adoption(
    academic_year,
    cohort,
    curriculum_learning_area,
    curriculum_version,
    learning_area,
    principal_user,
    school,
):
    rubric = _rubric(curriculum_learning_area)
    _publish(curriculum_version, principal_user)

    with pytest.raises(ValidationError):
        validate_curriculum_context_for_grading_binding(
            tenant=school,
            curriculum_version=curriculum_version,
            learning_area=learning_area,
            rubric_foundation=rubric,
        )
    with pytest.raises(ValidationError):
        _assessment(
            school=school,
            academic_year=academic_year,
            cohort=cohort,
            learning_area=learning_area,
            curriculum_version=curriculum_version,
            rubric=rubric,
        )

    schedule_school_curriculum_adoption(
        tenant=school,
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        scheduled_by=principal_user,
    )
    validate_curriculum_context_for_grading_binding(
        tenant=school,
        curriculum_version=curriculum_version,
        learning_area=learning_area,
        rubric_foundation=rubric,
    )


def test_withdrawal_does_not_mutate_historical_assessment_context(
    academic_year,
    cohort,
    curriculum_learning_area,
    curriculum_version,
    learning_area,
    principal_user,
    school,
):
    rubric = _rubric(curriculum_learning_area)
    _publish(curriculum_version, principal_user)
    schedule_school_curriculum_adoption(
        tenant=school,
        curriculum_version=curriculum_version,
        effective_from=date(2026, 1, 1),
        scheduled_by=principal_user,
    )
    assessment = _assessment(
        school=school,
        academic_year=academic_year,
        cohort=cohort,
        learning_area=learning_area,
        curriculum_version=curriculum_version,
        rubric=rubric,
    )

    mark_curriculum_version_withdrawn(
        curriculum_version=curriculum_version,
        withdrawn_by=principal_user,
        reason="Withdrawn for controlled rollback planning.",
    )
    assessment.refresh_from_db()

    assert assessment.curriculum_version_id == curriculum_version.id
    assert assessment.rubric_foundation_id == rubric.id
    assessment.title = "Renamed after withdrawal without rebind"
    assessment.save()
    validate_curriculum_context_for_compilation_dependency(assessment=assessment)


def test_rollback_planning_records_intent_without_mutating_history(
    curriculum_version,
    principal_user,
    school,
):
    plan = plan_curriculum_rollback(
        tenant=school,
        withdrawn_version=curriculum_version,
        planned_by=principal_user,
        reason="Plan controlled school rollback.",
        affected_assessment_count=2,
    )

    assert list(get_curriculum_rollback_plans(tenant=school)) == [plan]
    assert plan.status == CurriculumRollbackPlan.Status.PLANNED
    assert plan.affected_assessment_count == 2


def test_dependency_algorithms_fail_closed_and_are_side_effect_safe():
    assert not validate_grading_dependency_state(
        is_published=True,
        is_school_adopted=False,
        is_withdrawn=False,
        has_learning_area_context=True,
        has_rubric_context=True,
    ).is_allowed
    assert validate_historical_dependency_state(
        has_curriculum_version=True,
        has_learning_area_context=True,
        has_snapshot_context=True,
    ).is_allowed
    assert plan_assessment_rebind_eligibility(
        has_submitted_batches=True,
        has_grade_records=False,
    ).requires_review
    assert plan_rollout_batches(total_items=10000, batch_size=500)[0].end_index == 500
    assert plan_notice_batch(total_count=10000, batch_size=1000).batch_count == 10


def test_notice_batch_is_bounded_and_reference_only(
    django_capture_on_commit_callbacks,
    principal_user,
):
    with django_capture_on_commit_callbacks(execute=True):
        batch = create_notice_batch_run(
            notice_type=CurriculumNoticeBatchRun.NoticeType.PRINCIPAL_EVIDENCE,
            total_count=2500,
            batch_size=500,
            created_by=principal_user,
            notes="Batch principal evidence notices.",
        )

    assert list(get_curriculum_notice_batch_runs()) == [batch]
    event = EventOutbox.objects.get(event_type="curriculum.notice_batch_created")
    assert "raw_circular_text" not in event.payload
    assert event.payload["notice_batch_id"] == str(batch.id)
    assert event.payload["total_count"] == 2500


def test_cct_fortification_event_contracts_are_versioned_and_reference_only():
    forbidden = {
        "raw_circular_text",
        "raw_uploaded_file",
        "student_names",
        "learner_names",
        "raw_marks",
        "report_text",
        "nlp_output",
    }

    for event_type in [
        "curriculum.school_adoption_scheduled",
        "curriculum.version_withdrawn",
        "curriculum.rollback_planned",
        "curriculum.notice_batch_created",
    ]:
        contract = EventTypeRegistry.objects.get(event_type=event_type)
        required = set(contract.payload_schema["required"])
        assert contract.event_version == 1
        assert contract.allowed_producers == ["curriculum"]
        assert not (required & forbidden)


def test_cct_control_plane_policies_fail_closed(
    principal_role,
    principal_user,
    school,
    teacher_role,
    teacher_user,
):
    principal_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.schedule_adoption",
        role=principal_role,
    )
    assert can_schedule_school_adoption(principal_context)
    assert not can_plan_curriculum_rollback(principal_context)

    rollback_context = PolicyContext(
        tenant=school,
        actor=principal_user,
        action="curriculum.cct.plan_rollback",
        role=principal_role,
    )
    assert can_plan_curriculum_rollback(rollback_context)

    teacher_context = PolicyContext(
        tenant=school,
        actor=teacher_user,
        action="curriculum.cct.resolve_dependent_context",
        role=teacher_role,
    )
    assert not can_resolve_dependent_app_context(teacher_context)

    TenantUserRole.objects.filter(
        tenant=school,
        user=principal_user,
        role=principal_role,
    ).update(is_active=False)
    assert not can_schedule_school_adoption(principal_context)


def test_cct_services_do_not_mutate_grading_or_compilation_history():
    import curriculum.services as curriculum_services

    source = inspect.getsource(curriculum_services)

    assert "GradeRecord" not in source
    assert "GradeSubmissionBatch" not in source
    assert "CompilationRun" not in source
    assert "CompiledLearnerSnapshot" not in source
    assert "CompiledCohortSummary" not in source


def test_future_reporting_guard_requires_compiled_snapshots_and_report_phase():
    with pytest.raises(ValidationError):
        validate_curriculum_context_for_reporting_dependency(
            has_compiled_snapshot=True,
            has_preserved_curriculum_context=True,
        )


def test_phase_boundary_no_crawler_ai_reporting_or_finance(app_root, settings):
    forbidden_paths = [
        app_root / "curriculum" / "crawler.py",
        app_root / "curriculum" / "ai_parser.py",
        app_root / "reports",
        app_root / "finance",
    ]
    assert all(not path.exists() for path in forbidden_paths)
    assert "reports" not in settings.INSTALLED_APPS
    assert "finance" not in settings.INSTALLED_APPS
