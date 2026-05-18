from datetime import timedelta

from django.utils import timezone


def calculate_verification_sla_due_at(*, submitted_at=None, hours: int = 24):
    baseline = submitted_at or timezone.now()
    return baseline + timedelta(hours=hours)
