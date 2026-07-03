from __future__ import annotations

import builtins

import core.tracing as tracing_module
from core.tracing import configure_tracing


def _reset_instrumented_flag():
    tracing_module._INSTRUMENTED = False


class TestConfigureTracing:
    def setup_method(self):
        _reset_instrumented_flag()

    def teardown_method(self):
        _reset_instrumented_flag()

    def test_stays_disabled_when_exporter_is_none(self):
        result = configure_tracing(traces_exporter="none", service_name="darasa-core")

        assert result is False

    def test_stays_disabled_when_exporter_is_blank(self):
        result = configure_tracing(traces_exporter="", service_name="darasa-core")

        assert result is False

    def test_is_idempotent_once_instrumented(self):
        tracing_module._INSTRUMENTED = True

        result = configure_tracing(traces_exporter="otlp", service_name="darasa-core")

        assert result is True

    def test_degrades_safely_when_otel_packages_are_unavailable(self, monkeypatch):
        real_import = builtins.__import__

        def _blocking_import(name, *args, **kwargs):
            if name.startswith("opentelemetry"):
                raise ImportError(f"blocked for test: {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocking_import)

        result = configure_tracing(traces_exporter="otlp", service_name="darasa-core")

        assert result is False
        assert tracing_module._INSTRUMENTED is False
