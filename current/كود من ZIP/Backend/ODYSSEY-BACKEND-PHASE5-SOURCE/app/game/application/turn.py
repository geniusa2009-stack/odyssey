"""One authoritative game turn: clock catch-up, then (optionally) one semantic action.

The turn is the only code path that changes game state, used identically by the production
service (database + MissionService port) and the in-memory harness (tests, fuzzing):

1. **Catch-up**: advance the simulation by the ticks the server clock owes, stopping at the first
   tick where a clock-pausing incident starts; react.
2. **Plan** the command (pure validation; raises :class:`GameRuleError`).
3. **Dry run** on copies: apply the plan's decisions to a copy of the simulation state with the
   engine, finalize and react on copies. Any rejection aborts before an authoritative change.
4. **Apply** for real through the port (ledger), finalize, react.
5. **Mission end**: authorization completes the mission; a concluded simulation completes or
   fails a ``simulation_concluded`` mission.

Callers persist the resulting documents atomically and handle mission transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.errors import INVALID_DECISION_REASONS
from app.game.actions.errors import GameRuleError
from app.game.actions.planner import Command, Outcome, plan
from app.game.application.ports import SimPort, StopWhen
from app.game.campaign.campaign import Completion, complete_mission, fail_mission
from app.game.content.loader import LoadedContent
from app.game.realtime.derive import PublicState
from app.game.runtime import clock as clockmod
from app.game.world.conditions import Ctx, holds
from app.game.world.reactor import Reaction, react
from app.game.world.sim import SimView
from app.game.world.state import CampaignMeta, CompletionRecord, TimelineGameState
from app.game.world.views import (
    campaign_view,
    clock_view,
    discovery_views,
    insight_views,
    mission_view,
    world_view,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine

FAILED_TIERS = frozenset({"mission_failed", "critical_failure"})


@dataclass(slots=True)
class TurnResult:
    doc: TimelineGameState
    meta: CampaignMeta
    state: MissionState
    outcome: Outcome | None = None
    decision_ids: list[str] = field(default_factory=list)
    pre_decision_doc: TimelineGameState | None = None
    pre_decision_tick: int | None = None
    ticks_advanced: int = 0
    completion: Completion | None = None
    failure: CompletionRecord | None = None
    reactions: list[Reaction] = field(default_factory=list)

    @property
    def mission_ended(self) -> bool:
        return self.completion is not None or self.failure is not None


def public_state(
    content: LoadedContent, doc: TimelineGameState, meta: CampaignMeta, sim: SimView
) -> PublicState:
    ctx = Ctx(content, doc, meta, sim)
    return PublicState(
        world=world_view(ctx),
        mission=mission_view(ctx),
        clock=clock_view(ctx),
        campaign=campaign_view(content, meta),
        discoveries=tuple(discovery_views(ctx)),
        insights=tuple(insight_views(content, list(doc.insights), ctx)),
    )


def _tick_observer(
    content: LoadedContent, doc: TimelineGameState, meta: CampaignMeta, port: SimPort
) -> StopWhen:
    """Per-tick observer for clock advancement: records incident facts that hold at any tick
    (transient conditions between turns are not missed) and stops at the first tick where a
    clock-pausing incident would start."""
    world = content.index.worlds[doc.world_id]
    mine = [i for i in world.incidents if i.mission == doc.mission_id]
    pausing = [i for i in mine if i.pause_clock_on_start and i.id not in doc.incidents]

    def observe(state: MissionState) -> bool:
        ctx = Ctx(content, doc, meta, SimView(port.engine, state))
        for inc in mine:
            st = doc.incidents.get(inc.id)
            if st is None or st.resolved_tick is not None:
                continue
            for fact in inc.facts:
                if fact.id not in st.facts and holds(fact.when, ctx):
                    st.facts.append(fact.id)
                    doc.set_flag(f"fact:{inc.id}:{fact.id}")
        return any(holds(i.trigger, ctx) for i in pausing)

    return observe


def settle_new_mission(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    engine: SimulationEngine,
    state: MissionState,
) -> None:
    """Evaluate reactions once on a freshly started mission (cues already eligible at tick 0
    appear in the very first snapshot instead of on whatever the first turn happens to be)."""
    react(Ctx(content, doc, meta, SimView(engine, state)), default_container=_kit(content, doc))


def _kit(content: LoadedContent, doc: TimelineGameState) -> str | None:
    return content.index.missions[doc.mission_id].player_kit


def rule_from_engine(exc: DecisionRejectedError) -> GameRuleError:
    if exc.code == "mission_concluded":
        return GameRuleError("mission_concluded", exc.message, kind="complete")
    kind = "invalid" if exc.code in INVALID_DECISION_REASONS else "unavailable"
    return GameRuleError(exc.code, exc.message, kind=kind)  # type: ignore[arg-type]


async def catch_up(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    port: SimPort,
    now_ms: int,
    result: TurnResult,
) -> MissionState:
    state = await port.state()
    c = doc.clock
    due = clockmod.due_ticks(c, now_ms, state.tick)
    if due <= 0 or doc.status != "active":
        return state
    remaining = port.engine.scenario.time.max_ticks - state.tick
    run = min(due, c.max_catchup_ticks, max(remaining, 0))
    before_tick = state.tick
    if run > 0:
        state = await port.advance(run, _tick_observer(content, doc, meta, port))
    result.ticks_advanced += state.tick - before_tick
    sim = SimView(port.engine, state)
    reaction = react(Ctx(content, doc, meta, sim), default_container=_kit(content, doc))
    result.reactions.append(reaction)
    if reaction.pause_requested:
        clockmod.set_mode(c, "DECISION_PAUSED", now_ms, state.tick, reason="incident")
    elif sim.concluded:
        clockmod.set_mode(c, "PAUSED", now_ms, state.tick, reason="simulation_concluded")
    elif due > c.max_catchup_ticks:
        clockmod.set_mode(c, "PAUSED", now_ms, state.tick, reason="unattended_limit")
    return state


def _end_mission(content: LoadedContent, ctx: Ctx, result: TurnResult, *, authorized: bool) -> None:
    mission = content.index.missions[ctx.doc.mission_id]
    if ctx.doc.status != "active":
        return
    if authorized:
        result.completion = complete_mission(ctx, tier=ctx.sim.outcome_tier())
        return
    if mission.completion.type == "simulation_concluded" and ctx.sim.concluded:
        tier = ctx.sim.outcome_tier()
        if tier in FAILED_TIERS or tier is None:
            result.failure = fail_mission(ctx, tier=tier)
        else:
            result.completion = complete_mission(ctx, tier=tier)


async def run_turn(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    port: SimPort,
    now_ms: int,
    command: Command | None,
    *,
    decision_metadata: dict[str, Any] | None = None,
) -> TurnResult:
    """Run one turn on *copies* of ``doc``/``meta`` (the inputs are never mutated)."""
    doc = doc.model_copy(deep=True)
    meta = meta.model_copy(deep=True)
    result = TurnResult(doc=doc, meta=meta, state=await port.state())
    state = await catch_up(content, doc, meta, port, now_ms, result)
    kit = _kit(content, doc)
    engine = port.engine
    if command is not None:
        ctx = Ctx(content, doc, meta, SimView(engine, state))
        p = plan(ctx, command)
        # ---- dry run on copies: nothing authoritative changes if anything fails
        dry_doc, dry_meta, dry_state = doc.model_copy(deep=True), meta.model_copy(deep=True), state
        try:
            for d in p.decisions:
                dry_state = engine.apply_decision(dry_state, d, "dry-run").state
        except DecisionRejectedError as exc:
            raise rule_from_engine(exc) from None
        dry_ctx = Ctx(content, dry_doc, dry_meta, SimView(engine, dry_state))
        p.finalize(dry_ctx)
        react(dry_ctx, default_container=kit)
        # ---- authoritative application
        if p.decisions:
            result.pre_decision_doc = doc.model_copy(deep=True)
            result.pre_decision_tick = state.tick
        for d in p.decisions:
            state, did = await port.apply(d, decision_metadata or {})
            result.decision_ids.append(did)
        ctx = Ctx(content, doc, meta, SimView(engine, state))
        outcome = p.finalize(ctx)
        reaction = react(ctx, default_container=kit)
        result.reactions.append(reaction)
        c = doc.clock
        if outcome.start_clock:
            clockmod.start(c, now_ms, state.tick)
        if outcome.clock_mode is not None:
            clockmod.set_mode(c, outcome.clock_mode, now_ms, state.tick)
        if reaction.pause_requested:
            clockmod.set_mode(c, "DECISION_PAUSED", now_ms, state.tick, reason="incident")
        result.outcome = outcome
        _end_mission(content, ctx, result, authorized=outcome.complete_mission)
    else:
        _end_mission(
            content, Ctx(content, doc, meta, SimView(engine, state)), result, authorized=False
        )
    if result.mission_ended:
        clockmod.set_mode(doc.clock, "PAUSED", now_ms, state.tick, reason="mission_ended")
    result.state = state
    return result
