"""OpenTelemetry wiring, disabled by default.

`.env.example` already anticipated this with `OTEL_TRACES_EXPORTER=none`, but
nothing in the codebase ever read that setting. This module makes the
env var real: when the exporter is unset or `"none"` (the safe default for
local dev, CI, and any environment without a collector), tracing stays fully
disabled and no OpenTelemetry instrumentation package is even imported.
Only an explicit non-"none" exporter enables real instrumentation.
"""

from __future__ import annotations

from core.observability import get_logger


logger = get_logger("darasa.tracing")

_INSTRUMENTED = False


def configure_tracing(*, traces_exporter: str, service_name: str) -> bool:
    """Instrument Django/psycopg/Celery for tracing if explicitly enabled.

    Returns True if instrumentation was (or already is) active, False if
    tracing stayed disabled. Never raises: a missing/broken tracing backend
    must not prevent the application from serving traffic.
    """

    global _INSTRUMENTED

    normalized_exporter = (traces_exporter or "none").strip().lower()
    if _INSTRUMENTED:
        return True
    if not normalized_exporter or normalized_exporter == "none":
        logger.info("tracing.disabled", exporter=normalized_exporter or "none")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        logger.warning(
            "tracing.dependencies_missing", exporter=normalized_exporter
        )
        return False

    try:
        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        if not DjangoInstrumentor().is_instrumented_by_opentelemetry:
            DjangoInstrumentor().instrument()
        if not PsycopgInstrumentor().is_instrumented_by_opentelemetry:
            PsycopgInstrumentor().instrument()
    except Exception:  # noqa: BLE001 - tracing must never break request handling
        logger.exception("tracing.setup_failed", exporter=normalized_exporter)
        return False

    _INSTRUMENTED = True
    logger.info(
        "tracing.enabled", exporter=normalized_exporter, service_name=service_name
    )
    return True
