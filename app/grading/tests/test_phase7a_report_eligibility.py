from __future__ import annotations

import pytest

from grading.models import ReportSnapshotRun
from grading.services import compute_report_eligibility, create_report_snapshot_run


pytestmark = [pytest.mark.django_db, pytest.mark.grading]


def test_missing_compilation_blocks_report_snapshot(
    school,
    academic_year,
    term,
    assessment,
    principal_user,
):
    eligibility = compute_report_eligibility(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )

    assert eligibility["all_eligible"] is False
    assert eligibility["blocked_count"] == 1
    assert "compilation_missing" in eligibility["results"][0]["blocker_codes"]

    snapshot_run = create_report_snapshot_run(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )

    assert snapshot_run.status == ReportSnapshotRun.Status.BLOCKED
    assert snapshot_run.learner_snapshots.count() == 0


def test_cross_tenant_actor_cannot_compute_report_snapshot(
    other_school,
    academic_year,
    term,
    principal_user,
):
    with pytest.raises(Exception):
        compute_report_eligibility(
            actor=principal_user,
            tenant=other_school,
            academic_year=academic_year,
            term=term,
        )
