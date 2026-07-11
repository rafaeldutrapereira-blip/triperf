"""
LabX Observability — Prometheus metrics + trace_id context variable.

Prometheus is optional: if prometheus-client is not installed, all metric
operations are no-ops and /metrics returns an empty body.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

logger = logging.getLogger("labx.metrics")

# ── Trace ID — propagated through every request ───────────────────────────────
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def current_trace_id() -> str:
    return trace_id_ctx.get("")


# ── Prometheus (optional) ─────────────────────────────────────────────────────
_PROM_AVAILABLE = False

try:
    from prometheus_client import (  # type: ignore[import]
        Counter, Histogram, Gauge,
        generate_latest, CONTENT_TYPE_LATEST,
    )
    _PROM_AVAILABLE = True
except ImportError:
    logger.debug("prometheus-client not installed — metrics disabled. pip install prometheus-client")

    class _Noop:  # type: ignore[no-redef]
        def labels(self, **kwargs):  return self
        def inc(self,     *a, **kw): pass
        def dec(self,     *a, **kw): pass
        def observe(self, *a, **kw): pass
        def set(self,     *a, **kw): pass
        def __call__(self, *a, **kw): return self

    def Counter(*a, **kw):   return _Noop()   # type: ignore[misc]
    def Histogram(*a, **kw): return _Noop()   # type: ignore[misc]
    def Gauge(*a, **kw):     return _Noop()   # type: ignore[misc]

    def generate_latest():  return b""                    # type: ignore[misc]
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"    # type: ignore[assignment]


# ── Counters ──────────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "labx_http_requests_total",
    "Total HTTP requests by method, path, and status",
    ["method", "path", "status"],
)

auth_failures_total = Counter(
    "labx_auth_failures_total",
    "Authentication failures (wrong password, expired token, etc.)",
    ["reason"],
)

# ── Histograms ────────────────────────────────────────────────────────────────
http_request_duration_seconds = Histogram(
    "labx_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── Gauges ────────────────────────────────────────────────────────────────────
active_requests_gauge = Gauge(
    "labx_active_requests",
    "Number of HTTP requests currently being processed",
)


def is_available() -> bool:
    return _PROM_AVAILABLE


def get_metrics_output() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
