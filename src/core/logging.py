"""
ECHO OS Barebone: Structured logging with trace support

JSON format logs for CloudWatch Logs with trace_id/tenant_id/client_id filtering.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from contextvars import ContextVar

# Request-scoped context variables
_tenant_id: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
_client_id: ContextVar[Optional[str]] = ContextVar("client_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_route_trace: ContextVar[List[str]] = ContextVar("route_trace", default=[])
_layers_accessed: ContextVar[List[str]] = ContextVar("layers_accessed", default=[])
_request_start_time: ContextVar[Optional[float]] = ContextVar("request_start_time", default=None)


def set_context(
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    start_time: Optional[float] = None
) -> None:
    """Set request context."""
    if tenant_id is not None:
        _tenant_id.set(tenant_id)
    if client_id is not None:
        _client_id.set(client_id)
    if request_id is not None:
        _request_id.set(request_id)
    if trace_id is not None:
        _trace_id.set(trace_id)
        _request_id.set(trace_id)
    if start_time is not None:
        _request_start_time.set(start_time)


def clear_context() -> None:
    """Clear request context."""
    _tenant_id.set(None)
    _client_id.set(None)
    _request_id.set(None)
    _trace_id.set(None)
    _route_trace.set([])
    _layers_accessed.set([])
    _request_start_time.set(None)


def get_context() -> Dict[str, Any]:
    """Get current context."""
    return {
        "tenant_id": _tenant_id.get(),
        "client_id": _client_id.get(),
        "request_id": _request_id.get(),
        "trace_id": _trace_id.get(),
        "route_trace": _route_trace.get() or [],
        "layers_accessed": _layers_accessed.get() or [],
        "request_start_time": _request_start_time.get(),
    }


def get_trace_id() -> Optional[str]:
    """Get current trace_id."""
    return _trace_id.get() or _request_id.get()


def add_route_trace(component: str) -> None:
    """Add component to request route trace."""
    current = _route_trace.get() or []
    if component not in current:
        current.append(component)
        _route_trace.set(current)


def add_layer_accessed(layer: str) -> None:
    """Record accessed layer."""
    current = _layers_accessed.get() or []
    if layer not in current:
        current.append(layer)
        _layers_accessed.set(current)


class JSONFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        ctx = get_context()

        trace_id = ctx.get("trace_id") or ctx.get("request_id")
        if trace_id:
            log_entry["trace_id"] = trace_id

        if ctx.get("tenant_id"):
            log_entry["tenant_id"] = ctx["tenant_id"]
        if ctx.get("client_id"):
            log_entry["client_id"] = ctx["client_id"]

        if ctx.get("route_trace"):
            log_entry["route_trace"] = ctx["route_trace"]
        if ctx.get("layers_accessed"):
            log_entry["layers_accessed"] = ctx["layers_accessed"]

        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class TenantAwareLogger:
    """Tenant/Client aware logger wrapper."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **kwargs) -> None:
        """Log with extra fields."""
        extra_fields = kwargs.copy()

        if "start_time" in extra_fields:
            extra_fields["latency_ms"] = int((time.time() - extra_fields.pop("start_time")) * 1000)

        record = self.logger.makeRecord(
            self.logger.name,
            level,
            "(unknown)",
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def rag_search(
        self,
        layer: str,
        chunks_found: int,
        start_time: float,
        query_preview: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log RAG search result."""
        self.info(
            "rag_search_completed",
            layer=layer,
            chunks_found=chunks_found,
            start_time=start_time,
            query_preview=query_preview[:50] if query_preview else None,
            **kwargs
        )

    def api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        start_time: float,
        **kwargs
    ) -> None:
        """Log API request."""
        self.info(
            "api_request",
            method=method,
            path=path,
            status_code=status_code,
            start_time=start_time,
            **kwargs
        )


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Initialize logging configuration."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    root_logger.addHandler(handler)


def get_logger(name: str) -> TenantAwareLogger:
    """Get TenantAwareLogger."""
    return TenantAwareLogger(name)
