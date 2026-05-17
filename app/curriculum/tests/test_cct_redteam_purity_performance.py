from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction

from curriculum.algorithms.notice_batch_planning import plan_notice_batch
from curriculum.algorithms.rollout_planning import plan_rollout_batches
from curriculum.models import CurriculumNoticeBatchRun
from curriculum.services import create_notice_batch_run
from events.models import EventOutbox


pytestmark = [pytest.mark.django_db, pytest.mark.phase4]


def test_notice_batch_creation_is_single_event_and_rolls_back_cleanly(
    django_capture_on_commit_callbacks,
    principal_user,
):
    with django_capture_on_commit_callbacks(execute=True):
        batch = create_notice_batch_run(
            notice_type=CurriculumNoticeBatchRun.NoticeType.PRINCIPAL_EVIDENCE,
            total_count=10000,
            batch_size=500,
            created_by=principal_user,
            notes="Batch planned for many schools.",
        )

    assert EventOutbox.objects.filter(
        event_type="curriculum.notice_batch_created",
    ).count() == 1
    assert EventOutbox.objects.get().payload["notice_batch_id"] == str(batch.id)

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            create_notice_batch_run(
                notice_type=CurriculumNoticeBatchRun.NoticeType.TEACHER_READINESS,
                total_count=10000,
                batch_size=500,
                created_by=principal_user,
                notes="Rollback this batch.",
            )
            raise RuntimeError("force rollback")

    assert EventOutbox.objects.filter(
        event_type="curriculum.notice_batch_created",
    ).count() == 1


def test_notice_and_rollout_plans_bound_workload_without_materializing_schools():
    notice_plan = plan_notice_batch(total_count=10000, batch_size=500)
    rollout_batches = plan_rollout_batches(total_items=10000, batch_size=500)

    assert notice_plan.batch_count == 20
    assert len(rollout_batches) == 20
    assert rollout_batches[-1].end_index == 10000

    with pytest.raises(ValidationError):
        plan_notice_batch(total_count=1, batch_size=0)
    with pytest.raises(ValidationError):
        plan_rollout_batches(total_items=-1, batch_size=100)


def test_cct_algorithms_do_not_write_emit_events_or_call_network(app_root):
    algorithm_root = app_root / "curriculum" / "algorithms"
    forbidden = [
        ".save(",
        ".create(",
        ".update(",
        "write_outbox_event",
        "EventOutbox",
        "requests.",
        "httpx.",
        "urllib.request",
        "aiohttp",
        "socket.",
        "GradeRecord",
        "GradeSubmissionBatch",
        "CompilationRun",
        "CompiledLearnerSnapshot",
        "CompiledCohortSummary",
        "mark_safe",
    ]

    for path in Path(algorithm_root).glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token}"


def test_cct_services_do_not_use_all_students_or_all_schools_hot_paths():
    import curriculum.services as curriculum_services
    import curriculum.selectors as curriculum_selectors

    source = "\n".join(
        [
            inspect.getsource(curriculum_services),
            inspect.getsource(curriculum_selectors),
        ]
    )

    assert ".all()" not in source
    assert "Student.objects" not in source
    assert "School.objects.all" not in source
