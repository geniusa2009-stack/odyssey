"""Mission DNA: a compact, deterministic, privacy-safe fingerprint of how a mission was played.

Genes are coarse, bucketed characteristics. The DNA never includes session/timeline/decision
ids, participant data, wall-clock timestamps or the random seed — two players who make the same
kind of choices with the same result get the same DNA.

Code format: ``<SCENARIO>-<OUTCOME>-<10-char base32 hash of genes>``, e.g. ``LUNA01-MC-k2x8…``.
Visual representation is intentionally out of scope.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.simulation.analysis.profile import EngineeringProfile
from app.simulation.analysis.reconstruct import MissionRecord
from app.simulation.canonical import short_hash
from app.simulation.engine.engine import SimulationEngine

DNA_VERSION = 1
MAJOR_DECISION_TYPES = {
    "set_crew_location": "SH",
    "rover_command": "RV",
    "start_science_activity": "SC",
    "schedule_maintenance": "MT",
    "clean_solar_array": "CL",
    "set_ration_level": "RA",
}
OUTCOME_CODES = {
    "mission_complete_exceptional": "MX",  # LUNA-01 v0.2.0
    "mission_complete": "MC",
    "mission_complete_partial": "MP",
    "mission_failed": "MF",
    "mission_failed_crew_loss": "CL",
}
MAX_MAJOR_GENES = 16


class MissionDNA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = DNA_VERSION
    code: str
    genes: dict[str, Any]


def _bucket(value: float, labels: tuple[str, ...]) -> str:
    idx = min(len(labels) - 1, int(max(0.0, min(1.0, value)) * len(labels)))
    return labels[idx]


def _arg(decision_type: str, inputs: dict[str, Any]) -> str:
    if decision_type == "set_crew_location":
        return str(inputs.get("location", ""))[:2]
    if decision_type == "rover_command":
        return str(inputs.get("action", ""))[:2]
    if decision_type == "schedule_maintenance":
        return str(inputs.get("component", ""))[:3]
    return ""


def build_mission_dna(
    engine: SimulationEngine, record: MissionRecord, profile: EngineeringProfile
) -> MissionDNA:
    sc = engine.scenario
    final = record.final_state
    phase_index = {p.id: i for i, p in enumerate(sc.phases)}
    dims = {d.dimension: d.score for d in profile.dimensions}

    major = [
        f"P{phase_index.get(r.phase, 99):02d}:{MAJOR_DECISION_TYPES[r.decision_type]}"
        f"{_arg(r.decision_type, r.inputs)}"
        for r in record.records
        if r.decision_type in MAJOR_DECISION_TYPES
    ][:MAX_MAJOR_GENES]
    outcome = final.outcome.code if final.outcome else "in_progress"
    genes: dict[str, Any] = {
        "scenario": f"{sc.id}@{sc.version}",
        "outcome": outcome,
        "duration": _bucket(final.tick / sc.time.max_ticks, ("q1", "q2", "q3", "q4")),
        "science": _bucket(profile.features["science_return"], ("none", "low", "mid", "high")),
        "efficiency": _bucket(dims.get("resource_efficiency", 0.0), ("low", "mid", "high")),
        "risk_style": _bucket(dims.get("risk_preference", 0.0), ("cautious", "balanced", "bold")),
        "decisions": _bucket(min(1.0, len(record.records) / 40.0), ("few", "some", "many")),
        "major": major,
        "objectives": sorted(final.outcome.objectives_achieved) if final.outcome else [],
    }
    scenario_tag = sc.id.replace("-", "").upper()[:8]
    outcome_tag = OUTCOME_CODES.get(outcome, "IP")
    code = f"{scenario_tag}-{outcome_tag}-{short_hash({'v': DNA_VERSION, 'g': genes}, 10)}"
    return MissionDNA(code=code, genes=genes)


def dna_similarity(a: MissionDNA, b: MissionDNA) -> float:
    """0..1 similarity: scalar gene agreement averaged with Jaccard of list genes."""
    scalar = [k for k, v in a.genes.items() if not isinstance(v, list)]
    lists = [k for k, v in a.genes.items() if isinstance(v, list)]
    scores = [1.0 if a.genes.get(k) == b.genes.get(k) else 0.0 for k in scalar]
    for k in lists:
        sa, sb = set(a.genes.get(k, [])), set(b.genes.get(k, []))
        scores.append(1.0 if not sa and not sb else len(sa & sb) / len(sa | sb))
    return sum(scores) / len(scores) if scores else 0.0
