# Generated manually for Phase 4A CCT governance.

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("curriculum", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CurriculumAuthority",
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
                (
                    "code",
                    models.SlugField(
                        max_length=64,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Codes must be lowercase alphanumeric slugs.",
                                regex="^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
                            ),
                        ],
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("official_website", models.URLField(max_length=500)),
                ("allowed_domains", models.JSONField(default=list)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_approved", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "verbose_name": "Curriculum authority",
                "verbose_name_plural": "Curriculum authorities",
                "ordering": ["-updated_at"],
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["code", "is_active", "is_approved"],
                        name="curr_authority_lookup_idx",
                    ),
                ],
            },
        ),
        migrations.AlterField(
            model_name="curriculumsourcedocument",
            name="source_authority",
            field=models.SlugField(max_length=64),
        ),
        migrations.AddField(
            model_name="curriculumsourcedocument",
            name="authority",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="source_documents",
                to="curriculum.curriculumauthority",
            ),
        ),
        migrations.CreateModel(
            name="SourceArtifact",
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
                ("file_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(max_length=128)),
                ("file_size", models.PositiveIntegerField()),
                ("checksum_algorithm", models.CharField(default="sha256", max_length=32)),
                ("checksum", models.CharField(max_length=96)),
                (
                    "capture_method",
                    models.CharField(
                        choices=[
                            ("manual_upload", "Manual upload"),
                            ("approved_reference", "Approved reference"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "quarantine_status",
                    models.CharField(
                        choices=[
                            ("quarantined", "Quarantined"),
                            ("trusted", "Trusted"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="quarantined",
                        max_length=32,
                    ),
                ),
                (
                    "scan_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("clean", "Clean"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source_document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="artifacts",
                        to="curriculum.curriculumsourcedocument",
                    ),
                ),
            ],
            options={
                "verbose_name": "Source artifact",
                "verbose_name_plural": "Source artifacts",
                "ordering": ["-updated_at"],
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["quarantine_status", "scan_status"],
                        name="curr_artifact_quarantine_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("source_document", "checksum"),
                        name="curr_artifact_source_checksum_unique",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CurriculumChangeSet",
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
                (
                    "change_type",
                    models.CharField(
                        choices=[
                            ("new_version", "New version"),
                            ("source_changed", "Source changed"),
                            ("correction", "Correction"),
                        ],
                        max_length=32,
                    ),
                ),
                ("summary", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("detected", "Detected"),
                            ("quarantined", "Quarantined"),
                            ("under_review", "Under review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("published", "Published"),
                            ("superseded", "Superseded"),
                        ],
                        db_index=True,
                        default="detected",
                        max_length=32,
                    ),
                ),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "old_curriculum_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="old_change_sets",
                        to="curriculum.curriculumversion",
                    ),
                ),
                (
                    "proposed_curriculum_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="proposed_change_sets",
                        to="curriculum.curriculumversion",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_curriculum_change_sets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="change_sets",
                        to="curriculum.curriculumsourcedocument",
                    ),
                ),
            ],
            options={
                "verbose_name": "Curriculum change set",
                "verbose_name_plural": "Curriculum change sets",
                "ordering": ["-updated_at"],
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["status", "detected_at"],
                        name="curr_change_status_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CurriculumPublication",
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
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("publication_notes", models.TextField()),
                ("published_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_curriculum_publications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "curriculum_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="publications",
                        to="curriculum.curriculumversion",
                    ),
                ),
                (
                    "superseded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="superseded_publications",
                        to="curriculum.curriculumpublication",
                    ),
                ),
            ],
            options={
                "verbose_name": "Curriculum publication",
                "verbose_name_plural": "Curriculum publications",
                "ordering": ["-updated_at"],
                "abstract": False,
                "indexes": [
                    models.Index(
                        fields=["is_active", "effective_from"],
                        name="curr_publication_active_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("curriculum_version",),
                        name="curriculum_one_active_publication_per_version",
                    ),
                ],
            },
        ),
    ]
