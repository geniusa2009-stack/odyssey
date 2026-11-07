"""Thread-safe counters and latency summaries per operation kind."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from pydantic import BaseModel, ConfigDict


@dataclass(slots=True)
class _Series:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    ticks: int = 0


class OperationStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    count: int
    mean_ms: float
    max_ms: float
    total_ms: float
    ticks_simulated: int


class RuntimeStats:
    """Aggregates engine invocations (advance, decision, future_lens, black_box, rewind…)."""

    def __init__(self) -> None:
        self._series: dict[str, _Series] = {}
        self._lock = Lock()

    def record(self, kind: str, duration_ms: float, ticks: int = 0) -> None:
        if duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        with self._lock:
            series = self._series.setdefault(kind, _Series())
            series.count += 1
            series.total_ms += duration_ms
            series.max_ms = max(series.max_ms, duration_ms)
            series.ticks += max(0, ticks)

    def snapshot(self) -> list[OperationStats]:
        with self._lock:
            items = sorted(self._series.items())
            return [
                OperationStats(
                    kind=kind,
                    count=s.count,
                    mean_ms=s.total_ms / s.count,
                    max_ms=s.max_ms,
                    total_ms=s.total_ms,
                    ticks_simulated=s.ticks,
                )
                for kind, s in items
            ]

    def reset(self) -> None:
        with self._lock:
            self._series.clear()


runtime_stats = RuntimeStats()
