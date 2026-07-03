"""Provision a disposable school tenant for local dev / DAST scanning.

`TenantMainMiddleware` resolves the active schema from the request's Host
header against the `Domain` table. With none provisioned, every HTTP
request 404s regardless of URL correctness — including for tools like
OWASP ZAP that need a real host to attack. This command exists to remove
that barrier for local development and dynamic security scanning without
ever being usable against a real deployment.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tenant.models import Domain
from tenant.services import TenantProvisioningService


class Command(BaseCommand):
    help = (
        "Provision a school tenant, domain, and principal admin account for "
        "local development or DAST scanning (e.g. OWASP ZAP). Refuses to "
        "run unless DEBUG or TESTING is enabled, so it can never create a "
        "real school with a known admin password against a production "
        "database."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--school-name",
            default="Darasa Local Scan School",
            help="Display name for the disposable tenant.",
        )
        parser.add_argument(
            "--domain",
            required=True,
            help=(
                "Hostname clients will send as the HTTP Host header, e.g. "
                "'localhost' or 'zap-target'. Must match how the scanning "
                "tool or browser addresses this instance."
            ),
        )
        parser.add_argument(
            "--admin-email",
            default="scan-admin@darasa.local",
        )
        parser.add_argument(
            "--admin-password",
            default=None,
            help=(
                "If omitted, a random password is generated and printed "
                "once to stdout. Never reuse a generated password outside "
                "the disposable environment it was created for."
            ),
        )
        parser.add_argument(
            "--skip-if-exists",
            action="store_true",
            help=(
                "Exit successfully without provisioning again if a domain "
                "with this name already exists. Makes repeated CI/DAST runs "
                "idempotent."
            ),
        )

    def handle(self, *args, **options) -> None:
        if not (settings.DEBUG or getattr(settings, "TESTING", False)):
            raise CommandError(
                "provision_local_tenant refuses to run outside DEBUG/TESTING. "
                "This command creates a real tenant with a known admin "
                "password and must never touch a production database."
            )

        domain_string = str(options["domain"]).strip().lower()

        if options["skip_if_exists"] and Domain.objects.filter(
            domain=domain_string
        ).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Domain '{domain_string}' already provisioned; skipping."
                )
            )
            return

        admin_password = options["admin_password"] or secrets.token_urlsafe(18)

        try:
            context = TenantProvisioningService.provision_school_and_admin(
                school_name=options["school_name"],
                domain_string=domain_string,
                admin_email=options["admin_email"],
                admin_password=admin_password,
            )
        except ValueError as exc:
            raise CommandError(f"Could not provision tenant: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Provisioned disposable tenant:\n"
                f"  school:   {context.school.name} ({context.school.schema_name})\n"
                f"  domain:   {context.domain.domain}\n"
                f"  admin:    {context.principal.email}\n"
                f"  password: {admin_password}"
            )
        )
