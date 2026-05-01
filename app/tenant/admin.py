from django.contrib import admin

from tenant.models import Domain, School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "schema_name", "subdomain", "is_active", "created_at")
    list_filter = ("is_active", "on_trial")
    search_fields = ("name", "schema_name", "subdomain", "school_code")
    ordering = ("name",)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__name", "tenant__schema_name")