import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="School",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                (
                    "schema_name",
                    models.CharField(
                        db_index=True,
                        help_text="Lowercase PostgreSQL schema identifier.",
                        max_length=63,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=(
                                    "Schema names must be lowercase PostgreSQL-safe "
                                    "identifiers."
                                ),
                                regex="^[a-z][a-z0-9_]{1,62}$",
                            )
                        ],
                    ),
                ),
                (
                    "subdomain",
                    models.SlugField(
                        db_index=True,
                        help_text=(
                            "Canonical tenant slug used to derive school domains."
                        ),
                        max_length=63,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=(
                                    "Subdomains must be lowercase and may include "
                                    "hyphens."
                                ),
                                regex="^[a-z0-9]+(?:-[a-z0-9]+)*$",
                            )
                        ],
                    ),
                ),
                (
                    "school_code",
                    models.CharField(
                        db_index=True,
                        help_text=(
                            "Institution code used for external integrations and "
                            "onboarding."
                        ),
                        max_length=20,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=(
                                    "School codes must be 4-20 uppercase "
                                    "alphanumeric characters."
                                ),
                                regex="^[A-Z0-9]{4,20}$",
                            )
                        ],
                    ),
                ),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=32)),
                ("timezone", models.CharField(default="Africa/Nairobi", max_length=64)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("paid_until", models.DateField(blank=True, null=True)),
                ("on_trial", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "School",
                "verbose_name_plural": "Schools",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="Domain",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("domain", models.CharField(db_index=True, max_length=253, unique=True)),
                ("is_primary", models.BooleanField(db_index=True, default=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="tenant.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Domain",
                "verbose_name_plural": "Domains",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="school",
            index=models.Index(
                fields=["is_active", "created_at"],
                name="tenant_school_state_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="school",
            index=models.Index(
                fields=["subdomain", "is_active"],
                name="tenant_school_subdomain_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="domain",
            index=models.Index(
                fields=["domain", "is_primary"],
                name="tenant_domain_lookup_idx",
            ),
        ),
    ]
