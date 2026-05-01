from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.models import CustomUser, Role, TenantUserRole


@admin.register(CustomUser)
class CustomUserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "created_at",
    )
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined", "created_at", "updated_at")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "is_system_role", "created_at")
    list_filter = ("is_system_role", "name")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(TenantUserRole)
class TenantUserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "school")
    search_fields = ("user__email", "school__name", "role__name")
    autocomplete_fields = ("user", "school", "role", "granted_by")
