"""Structured logging configuration.

Darasa already declared `structlog`, `opentelemetry-*`, and `prometheus-client`
as dependencies (see `pyproject.toml`) but never wired them into the runtime.
This module turns those declared dependencies into a working, testable
observability foundation:

- Every log line is structured (JSON in production, readable console output
  in development) instead of free-text string interpolation.
- Request-scoped fields (request id, tenant schema, HTTP method/path) are
  bound once per request via context variables so every log line emitted
  while handling that request carries the same correlation fields without
  every call site having to pass them explicitly.

This module intentionally has no Django app-registry or ORM dependency so it
can be imported directly from `settings.py` before Django finishes setup.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog


SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
]
# `format_exc_info` deliberately is NOT in the shared chain: it eagerly
# renders `exc_info` into a plain string, which both defeats
# `ConsoleRenderer`'s own pretty-exception rendering in development and
# triggers a structlog UserWarning. It is applied only in the JSON formatter
# branch below, where a plain rendered string is exactly what is wanted.


def configure_structlog(*, debug: bool) -> None:
    """Configure structlog once at settings import time.

    Safe to call multiple times (e.g. across repeated test-suite imports);
    `structlog.configure` simply replaces the previous global configuration.
    """

    structlog.configure(
        processors=SHARED_PROCESSORS
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def build_structlog_formatters(*, debug: bool) -> dict[str, dict[str, Any]]:
    """Return Django `LOGGING["formatters"]` entries backed by structlog.

    `debug=True` renders human-friendly console output for local development;
    otherwise renders single-line JSON suitable for log aggregation.
    """

    if debug:
        final_processors: list[Any] = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ]
    else:
        final_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    return {
        "structlog": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": final_processors,
        }
    }


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def reset_context() -> None:
    """Clear request-scoped structlog context variables.

    Exposed as a standalone helper (rather than inlined in middleware) so
    tests can assert context does not leak between requests.
    """

    structlog.contextvars.clear_contextvars()


def silence_noisy_third_party_loggers() -> None:
    """Keep chatty third-party libraries below WARNING by default."""

    for logger_name in ("botocore", "urllib3", "asyncio"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
