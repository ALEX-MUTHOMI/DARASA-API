from __future__ import annotations

import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_tenants.models import DomainMixin, TenantMixin


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-updated_at"]


schema_name_validator = RegexValidator(
    regex=r"^[a-z][a-z0-9_]{1,62}$",
    message=_("Schema names must be lowercase PostgreSQL-safe identifiers."),
)

subdomain_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    message=_("Subdomains must be lowercase and may include hyphens."),
)

school_code_validator = RegexValidator(
    regex=r"^[A-Z0-9]{4,20}$",
    message=_("School codes must be 4-20 uppercase alphanumeric characters."),
)


class School(TenantMixin, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    schema_name = models.CharField(
        max_length=63,
        unique=True,
        db_index=True,
        validators=[schema_name_validator],
        help_text=_("Lowercase PostgreSQL schema identifier."),
    )
    subdomain = models.SlugField(
        max_length=63,
        unique=True,
        db_index=True,
        validators=[subdomain_validator],
        help_text=_("Canonical tenant slug used to derive school domains."),
    )
    school_code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        validators=[school_code_validator],
        help_text=_("Institution code used for external integrations and onboarding."),
    )
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    is_active = models.BooleanField(default=True, db_index=True)
    paid_until = models.DateField(null=True, blank=True)
    on_trial = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    auto_create_schema = True
    auto_drop_schema = False

    class Meta(TimeStampedModel.Meta):
        verbose_name = "School"
        verbose_name_plural = "Schools"
        indexes = [
            models.Index(
                fields=["is_active", "created_at"],
                name="tenant_school_state_idx",
            ),
            models.Index(
                fields=["subdomain", "is_active"],
                name="tenant_school_subdomain_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.schema_name:
            self.schema_name = self.schema_name.lower()
        if self.subdomain:
            self.subdomain = self.subdomain.lower()
        if self.school_code:
            self.school_code = self.school_code.upper()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.schema_name})"


class Domain(TimeStampedModel, DomainMixin):
    class Meta(TimeStampedModel.Meta):
        verbose_name = "Domain"
        verbose_name_plural = "Domains"
        indexes = [
            models.Index(
                fields=["domain", "is_primary"],
                name="tenant_domain_lookup_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.domain:
            self.domain = self.domain.lower().strip()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.domain
