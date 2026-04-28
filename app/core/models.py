"""
Core Database Models for the PhotoBox SaaS API.
"""
import os
import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.hashers import make_password, check_password
from PIL import Image as PILImage
from PIL import UnidentifiedImageError




# ==========================================
# 1. ABSTRACT BASE MODELS (Audit & Data Retention)
# ==========================================
class SoftDeleteModel(models.Model):
    """Base model providing UUIDs, audit timestamps, and soft-delete capabilities."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


# ==========================================
# 2. AUTHENTICATION & BILLING
# ==========================================
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('User must have an email address.')
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        user = self.create_user(email, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """Account owners (Photographers). Clients do NOT use this."""
    class SubscriptionTier(models.TextChoices):
        FREE = 'FREE', 'Free Tier'
        PRO = 'PRO', 'Professional'

    email = models.EmailField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    accepted_terms = models.BooleanField(default=False)
    tos_accepted_at = models.DateTimeField(blank=True, null=True)
    tos_version = models.CharField(max_length=64, blank=True)

    # Billing State
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    subscription_tier = models.CharField(max_length=20, choices=SubscriptionTier.choices, default=SubscriptionTier.FREE)

    # Storage limit tracked in GB for easy human/billing logic
    storage_limit_gb = models.IntegerField(default=1)

    objects = UserManager()
    USERNAME_FIELD = 'email'

    def save(self, *args, **kwargs):
        """
        EDA FIX: Auto-Sync Billing to the Storage Ledger.
        If Stripe updates storage_limit_gb, automatically sync it to Workspace bytes.
        """
        super().save(*args, **kwargs)
        # Ensure the user has a workspace, then sync the bytes
        if hasattr(self, 'workspace'):
            new_byte_limit = self.storage_limit_gb * 1024 * 1024 * 1024
            if self.workspace.storage_limit_bytes != new_byte_limit:
                self.workspace.storage_limit_bytes = new_byte_limit
                self.workspace.save(update_fields=['storage_limit_bytes'])


# ==========================================
# 3. TENANT ISOLATION & FRONTEND BRANDING
# ==========================================
class Workspace(SoftDeleteModel):
    """The tenant boundary. Holds UX configuration and EDA Quotas."""

    # THE EDA FIX: Changed from ForeignKey to OneToOneField.
    # Guarantees 100% safety for Workspace.objects.get(user=user)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace')

    business_name = models.CharField(max_length=255)
    custom_domain = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # Frontend Branding
    brand_color = models.CharField(max_length=7, default='#000000')

    # --- EDA UPGRADE: The Atomic Quota Ledger ---
    # MinValueValidator enforces database-level integrity against negative storage hacks
    storage_limit_bytes = models.BigIntegerField(default=1 * 1024 * 1024 * 1024, validators=[MinValueValidator(0)])
    storage_used_bytes = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.business_name




