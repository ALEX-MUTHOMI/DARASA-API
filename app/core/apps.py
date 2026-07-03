from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from django.conf import settings

        from core.tracing import configure_tracing

        configure_tracing(
            traces_exporter=getattr(settings, "OTEL_TRACES_EXPORTER", "none"),
            service_name=getattr(settings, "OTEL_SERVICE_NAME", "darasa-core"),
        )
