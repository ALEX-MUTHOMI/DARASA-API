from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from tenant.models import Domain, School


pytestmark = [pytest.mark.django_db, pytest.mark.core]


def _domain(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}.scan.test"


def test_provisions_school_domain_and_admin_when_debug_enabled(settings):
    settings.DEBUG = True
    domain = _domain("zap")
    out = StringIO()

    call_command(
        "provision_local_tenant",
        domain=domain,
        admin_email="scan@example.test",
        admin_password="test-only-secret",
        stdout=out,
    )

    assert Domain.objects.filter(domain=domain).exists()
    assert School.objects.filter(
        domains__domain=domain
    ).exists() or School.objects.filter(subdomain__isnull=False).exists()
    assert "Provisioned disposable tenant" in out.getvalue()
    assert domain in out.getvalue()


def test_generates_password_when_not_supplied(settings):
    settings.DEBUG = True
    domain = _domain("generated")
    out = StringIO()

    call_command("provision_local_tenant", domain=domain, stdout=out)

    assert "password:" in out.getvalue()


def test_refuses_to_run_outside_debug_and_testing(settings):
    settings.DEBUG = False
    settings.TESTING = False

    with pytest.raises(CommandError):
        call_command("provision_local_tenant", domain=_domain("refused"))

    assert not Domain.objects.filter(domain__startswith="refused-").exists()


def test_skip_if_exists_is_idempotent(settings):
    settings.DEBUG = True
    domain = _domain("idempotent")

    call_command(
        "provision_local_tenant",
        domain=domain,
        admin_email="first@example.test",
    )
    before_count = Domain.objects.count()

    call_command(
        "provision_local_tenant",
        domain=domain,
        admin_email="second@example.test",
        skip_if_exists=True,
    )

    assert Domain.objects.count() == before_count


def test_without_skip_if_exists_duplicate_domain_raises(settings):
    settings.DEBUG = True
    domain = _domain("duplicate")

    call_command(
        "provision_local_tenant", domain=domain, admin_email="first@example.test"
    )

    with pytest.raises(CommandError):
        call_command(
            "provision_local_tenant",
            domain=domain,
            admin_email="second@example.test",
        )
