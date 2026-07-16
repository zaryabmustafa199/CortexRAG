"""
app/core/logging.py
-------------------
Configures structlog for structured JSON logging across the entire application.

Every log line emits:
  {timestamp, level, event, correlation_id, user_id, workspace_id, ...extra}

Usage anywhere in the codebase:
    from app.core.logging import get_logger
    logger = get_logger()
    logger.info("document_uploaded", document_id=str(doc.id), workspace_id=str(ws_id))

In Celery workers, bind the correlation_id from the task payload:
    logger = get_logger().bind(correlation_id=correlation_id, job_id=job_id)
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Union, cast

import structlog
from structlog.types import EventDict, WrappedLogger


def _add_severity(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Map structlog level names to uppercase for log aggregators (e.g. Grafana Loki)."""
    event_dict["level"] = method_name.upper()
    return event_dict


def _drop_color_message(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove the 'color_message' key injected by uvicorn's logger."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(json_logs: bool = True, log_level: str = "INFO") -> None:
    """
    Call once at application startup.
    json_logs=True  → machine-readable JSON (production)
    json_logs=False → pretty console output (development)
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        _add_severity,
        _drop_color_message,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Union[structlog.processors.JSONRenderer, structlog.dev.ConsoleRenderer]
    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger() -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Call .bind(key=value) to add permanent context fields."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger())
