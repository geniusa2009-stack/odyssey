"""Engines keyed by pinned scenario content hash (sessions replay with *their* scenario)."""

from __future__ import annotations

from threading import Lock

from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.schema import ScenarioDefinition


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, SimulationEngine] = {}
        self._lock = Lock()

    def get(self, content_hash: str, definition: dict[str, object]) -> SimulationEngine:
        engine = self._engines.get(content_hash)
        if engine is None:
            with self._lock:
                engine = self._engines.get(content_hash)
                if engine is None:
                    engine = SimulationEngine(ScenarioDefinition.model_validate(definition))
                    self._engines[content_hash] = engine
        return engine
