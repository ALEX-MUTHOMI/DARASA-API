import uuid

import core.models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("tenant", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
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
                ("code", models.SlugField(db_index=True, max_length=64, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "verbose_name": "Role",
                "verbose_name_plural": "Roles",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomUser",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="last login",
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates that this user has all permissions without "
                            "explicitly assigning them."
                        ),
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="first name",
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="last name",
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates whether the user can log into this admin site."
                        ),
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Designates whether this user should be treated as active. "
                            "Unselect this instead of deleting accounts."
                        ),
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="date joined",
                    ),
                ),
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
                    "email",
                    models.EmailField(
                        db_index=True,
                        max_length=254,
                        unique=True,
                        verbose_name="email address",
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "The groups this user belongs to. A user will get all "
                            "permissions granted to each of their groups."
                        ),
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
                "db_table": "core_user",
            },
            managers=[
                ("objects", core.models.CustomUserManager()),
            ],
        ),
        migrations.CreateModel(
            name="TenantUserRole",
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
                    "assigned_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_tenant_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tenant_user_bindings",
                        to="core.role",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_roles",
                        to="tenant.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tenant_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant user role",
                "verbose_name_plural": "Tenant user roles",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="role",
            index=models.Index(fields=["code", "is_active"], name="core_role_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(
                fields=("code",),
                name="core_role_code_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="customuser",
            index=models.Index(fields=["email", "is_active"], name="core_user_email_idx"),
        ),
        migrations.AddIndex(
            model_name="tenantuserrole",
            index=models.Index(
                fields=["tenant", "is_active"],
                name="core_tur_tenant_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="tenantuserrole",
            index=models.Index(fields=["user", "is_active"], name="core_tur_user_idx"),
        ),
        migrations.AddIndex(
            model_name="tenantuserrole",
            index=models.Index(fields=["role", "is_active"], name="core_tur_role_idx"),
        ),
        migrations.AddConstraint(
            model_name="tenantuserrole",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("tenant", "user", "role"),
                name="core_active_tenant_user_role_unique",
            ),
        ),
    ]
