"""
core/models.py
==============
Global Identity & Shared Base Utilities — Darasa-Core ERP
Back To Front Development

SECURITY:
    - Primary keys are strictly UUIDv4 to prevent IDOR traversal.
    - EncryptedCharField uses Fernet symmetric encryption to armor PII.
"""

import uuid
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from tenant.models import TimeStampedModel


class EncryptedCharField(models.CharField):
    """
    Transparently encrypts data at the database layer.
    Requires FERNET_ENCRYPTION_KEY in settings.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        fernet = Fernet(settings.FERNET_ENCRYPTION_KEY)
        return fernet.encrypt(str(value).encode('utf-8')).decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        fernet = Fernet(settings.FERNET_ENCRYPTION_KEY)
        try:
            return fernet.decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value  # Return raw if decryption fails (e.g. key rotation mismatch)


class CustomUserManager(UserManager):
    pass


class CustomUser(AbstractUser, TimeStampedModel):
    """
    Global Identity Model.
    Lives in the PUBLIC schema. Tenant access is resolved via RBAC matrices.
    """
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        help_text=_("UUIDv4 to prevent Insecure Direct Object Reference (IDOR)")
    )
    # We remove standard first/last name to encourage encrypted PII usage if needed, 
    # but keep it simple for now as requested.
    
    objects = CustomUserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        db_table = "core_user"

    def __str__(self):
        return self.username
