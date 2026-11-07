"""``odyssey.game.v1`` read shapes for the Future Lens, Black Box and WHY adapters.

They are *adapters* over the established, hidden-information-safe v1 analysis read models
(``app/read_models/analysis.py``): the Future Lens prediction runs with the ``known_only``
knowledge policy and the Black Box keeps its counterfactual causal rules. These shapes only
re-key the results onto semantic world ids and command ids so Unreal can render a projected
future or a spatial causal timeline. They never contain hidden event names or timings,
excluded events, secret phase transitions, the seed, ledger decision ids, simulation session
ids or engine internals, and they carry no presentation directives (colours, animations, VFX).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.game.contracts.protocol import GAME_PROTOCOL
from app.game.contracts.views import GameView

WarningLevel = Literal["none", "caution", "warning", "critical"]


# ============================================================================ Future Lens
class LensRejection(GameView):
    reason: str
    message: str


class LensResourceDelta(GameView):
    metric: str
    label: str
    unit: str
    start: float
    end: float
    delta: float
    worst: float
    vs_baseline: float | None = None
    warning_level: WarningLevel


class LensObjectiveDelta(GameView):
    objective: str
    status_now: str
    projected_status: str


class LensWarning(GameView):
    alert: str
    severity: str
    metric: str
    hours_from_now: float
    introduced_by_candidate: bool


class WorldStateHint(GameView):
    """A semantic world fact the candidate changes *immediately* (applying the action, before
    any time passes): enough for Unreal to show e.g. a powered-down lab, never art direction."""

    object: str
    field: Literal["status", "power", "mode", "infrastructure_state", "access"]
    now: str | None
    after: str | None


class LensRisk(GameView):
    end_index: float
    peak_index: float


class LensConfidence(GameView):
    level: str
    score: float


class LensBranch(GameView):
    id: str
    is_baseline: bool
    action: str | None = None
    target: str | None = None
    valid: bool
    rejection: LensRejection | None = None
    affects_simulation: bool
    affected_objects: list[str] = Field(default_factory=list)
    world_hints: list[WorldStateHint] = Field(default_factory=list)
    resources: list[LensResourceDelta] = Field(default_factory=list)
    objectives: list[LensObjectiveDelta] = Field(default_factory=list)
    warnings: list[LensWarning] = Field(default_factory=list)
    risk: LensRisk | None = None
    confidence: LensConfidence | None = None
    concludes_within_horizon: bool = False
    projected_outcome_tier: str | None = None


class LensHorizon(GameView):
    requested_ticks: int
    projected_ticks: int
    hours: float
    clipped_to_mission_end: bool


class LensKnowledgeBoundary(GameView):
    prediction_mode: Literal["known_only"]
    anticipates_unforeseeable_events: bool
    statement: str


class GameFutureLensView(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    timeline_id: str
    mission_id: str
    state_version: int
    base_tick: int
    base_sim_hours: float
    horizon: LensHorizon
    knowledge_boundary: LensKnowledgeBoundary
    branches: list[LensBranch]


# ============================================================================ Black Box
CausalNodeType = Literal["decision", "trigger", "effect", "shortfall", "cause", "moment", "outcome"]
CausalRelation = Literal["caused", "contributed", "triggered", "on_path_no_effect", "led_to"]
CounterfactualStatus = Literal["worsened", "improved", "no_effect", "not_evaluated"]


class DecisionRelation(GameView):
    command_id: str | None
    action: str | None
    target: str | None
    counterfactual: CounterfactualStatus


class CausalNode(GameView):
    id: str
    type: CausalNodeType
    sim_tick: int | None
    sim_time_hours: float | None
    label: str
    system_ref: str | None = None
    objective_ref: str | None = None
    anchor: str | None = Field(None, description="semantic world location, when meaningful")
    severity: str | None = None
    decision: DecisionRelation | None = None


class CausalEdge(GameView):
    source: str
    target: str
    relation: CausalRelation


class BlackBoxOutcome(GameView):
    code: str
    tier: str | None
    sim_tick: int


class GameBlackBoxView(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    timeline_id: str
    mission_id: str
    state_version: int
    mission_status: str = Field(
        description="Game timeline status (active/completed/failed/rewound)"
    )
    simulation_status: str = Field(
        description="Status of the underlying simulation run (an authorization-completed "
        "mission such as Earth Command ends the game mission without concluding the simulation)"
    )
    final_tick: int
    final_sim_hours: float
    outcome: BlackBoxOutcome | None
    counterfactuals_evaluated: bool
    nodes: list[CausalNode]
    edges: list[CausalEdge]
    statement: str


# ============================================================================ profile / DNA
class ProfileDimension(GameView):
    id: str
    value: float
    contributions: dict[str, float]


class GameEngineeringProfileView(GameView):
    """The existing Engineering Profile (gameplay decisions, not personality), re-keyed to
    game ids."""

    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    timeline_id: str
    mission_id: str
    weights_version: str
    provisional: bool
    dimensions: list[ProfileDimension]
    coverage: dict[str, int | bool]
    notes: list[str]


class GameMissionDNAView(GameView):
    """The existing share-safe Mission DNA (mission behaviour/outcome), re-keyed to game ids."""

    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    timeline_id: str
    mission_id: str
    code: str
    dna_version: int
    scenario_id: str
    scenario_version: str
    outcome_code: str | None
    outcome_tier: str | None
    concluded: bool
    genes: dict[str, object]
