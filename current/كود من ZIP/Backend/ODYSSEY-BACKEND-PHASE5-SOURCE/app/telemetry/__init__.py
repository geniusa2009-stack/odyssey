"""In-process telemetry (simulation run counters and latencies).

Structured logging lives in :mod:`app.core.logging`; this package aggregates numbers. It is
deliberately dependency-free: an exporter (Prometheus, OpenTelemetry) can read
:meth:`RuntimeStats.snapshot` later without touching call sites.
"""

from app.telemetry.stats import RuntimeStats, runtime_stats

__all__ = ["RuntimeStats", "runtime_stats"]
