from __future__ import annotations

import uuid
from typing import Any, ClassVar, cast

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tenant.models import School, TimeStampedModel


class EncryptedCharField(models.CharField):
    """
    Encrypts short text at rest for future PII-bearing fields.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 255)
        super().__init__(*args, **kwargs)

    @staticmethod
    def _fernet() -> Fernet:
        key = cast(str, getattr(settings, "FERNET_ENCRYPTION_KEY", ""))
        return Fernet(key)

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return self._fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None or value == "":
            return value
        try:
            return self._fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ImproperlyConfigured(
                "Encrypted field value could not be decrypted."
            ) from exc


class CustomUserManager(BaseUserManager):
    use_in_migrations: ClassVar[bool] = True

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: Any,
    ) -> CustomUser:
        if not email:
            raise ValueError("Email address is required.")
        normalized_email = self.normalize_email(email).lower()
        user = cast(CustomUser, self.model(email=normalized_email, **extra_fields))
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> CustomUser:
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> CustomUser:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have staff access.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have superuser access.")
        return self._create_user(email, password, **extra_fields)


class CustomUser(AbstractUser, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username: Any = None
    email = models.EmailField(_("email address"), unique=True, db_index=True)

    USERNAME_FIELD: ClassVar[str] = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects: ClassVar[CustomUserManager] = CustomUserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        db_table = "core_user"
        indexes = [
            models.Index(fields=["email", "is_active"], name="core_user_email_idx"),
        ]

    def __str__(self) -> str:
        return f"User {self.pk}"


class Role(TimeStampedModel):
    class RoleCode(models.TextChoices):
        PRINCIPAL = "principal", _("Principal")
        DEPUTY_PRINCIPAL = "deputy_principal", _("Deputy Principal")
        HOD = "hod", _("Head of Department")
        CLASS_TEACHER = "class_teacher", _("Class Teacher")
        SUBJECT_TEACHER = "subject_teacher", _("Subject Teacher")
        SCHOOL_ADMIN = "school_admin", _("School Admin")
        GUARDIAN = "guardian", _("Guardian")
        AUDITOR = "auditor", _("Auditor")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["code"], name="core_role_code_unique"),
        ]
        indexes = [
            models.Index(fields=["code", "is_active"], name="core_role_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.code:
            self.code = self.code.strip().lower().replace("-", "_")

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code


class TenantUserRole(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    user = models.ForeignKey(
        getattr(settings, "AUTH_USER_MODEL", "core.CustomUser"),
        on_delete=models.CASCADE,
        related_name="tenant_roles",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="tenant_user_bindings",
    )
    assigned_by = models.ForeignKey(
        getattr(settings, "AUTH_USER_MODEL", "core.CustomUser"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tenant_roles",
    )
    assigned_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = _("Tenant user role")
        verbose_name_plural = _("Tenant user roles")
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "role"],
                condition=Q(is_active=True),
                name="core_active_tenant_user_role_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="core_tur_tenant_idx"),
            models.Index(fields=["user", "is_active"], name="core_tur_user_idx"),
            models.Index(fields=["role", "is_active"], name="core_tur_role_idx"),
        ]

    def __str__(self) -> str:
        user_id = getattr(self, "user_id", None)
        tenant_id = getattr(self, "tenant_id", None)
        role_id = getattr(self, "role_id", None)
        return f"{user_id}:{tenant_id}:{role_id}"
