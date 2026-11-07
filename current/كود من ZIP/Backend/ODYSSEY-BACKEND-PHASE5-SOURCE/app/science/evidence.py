"""Science evidence registry: traceability from simulation constants to sources."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.simulation.scenarios.loader import load_yaml

EVIDENCE_FILE = Path(__file__).parent / "data" / "evidence.yaml"


class ScienceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    concept: str
    claim: str
    value: float | None = None
    unit: str | None = None
    source_name: str
    source_citation: str | None = None
    source_url: HttpUrl | None = None
    retrieved_date: str
    verification_status: Literal["verified_primary", "verified_secondary", "unverified"]
    simulation_usage: list[str]
    simplification: str
    confidence: Literal["high", "medium", "low"]
    notes: str | None = None


class EvidenceNotFoundError(KeyError):
    pass


class EvidenceRegistry:
    def __init__(self, items: list[ScienceEvidence]) -> None:
        self._items = {e.id: e for e in items}
        if len(self._items) != len(items):
            raise ValueError("duplicate evidence ids")

    @classmethod
    def from_file(cls, path: Path = EVIDENCE_FILE) -> EvidenceRegistry:
        raw = load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("evidence file must contain a list")
        return cls([ScienceEvidence.model_validate(item) for item in raw])

    def get(self, evidence_id: str) -> ScienceEvidence:
        try:
            return self._items[evidence_id]
        except KeyError as exc:
            raise EvidenceNotFoundError(evidence_id) from exc

    def all(self) -> list[ScienceEvidence]:
        return [self._items[k] for k in sorted(self._items)]

    def for_usage(self, config_path: str) -> list[ScienceEvidence]:
        return [e for e in self.all() if config_path in e.simulation_usage]

    def ids(self) -> set[str]:
        return set(self._items)


@lru_cache(maxsize=1)
def default_registry() -> EvidenceRegistry:
    return EvidenceRegistry.from_file()
