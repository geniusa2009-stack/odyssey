"""Future Lens game adapter (``POST /api/game/v1/sessions/{id}/future-lens``).

The Future Lens *engine* is untouched. The adapter:

1. plans each semantic candidate exactly like a command (same legality rules) on copies of the
   timeline document, turning it into the simulation decisions it would record;
2. applies those decisions and the action's direct game-side consequences on copies to report
   the **immediate** semantic world changes (status/power/mode/infrastructure/access of objects
   the player already knows) — no time passes, so nothing hidden can surface;
3. runs the established Future Lens projection with the ``known_only`` knowledge policy (hidden
   unforeseeable events are excluded from the projection and never named) through the existing
   ``MissionService`` path, and maps the v1 safe read model (``build_future_lens_view``) onto
   semantic ids.

Withheld facts stay withheld: v1 already withholds unentered phase identities and keeps the
knowledge factor constant so the confidence does not reveal whether hidden events remain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.game.actions.errors import GameRuleError
from app.game.actions.planner import Command, plan
from app.game.application.turn import rule_from_engine
from app.game.content.loader import LoadedContent
from app.game.contracts.analysis import (
    GameFutureLensView,
    LensBranch,
    LensConfidence,
    LensHorizon,
    LensKnowledgeBoundary,
    LensObjectiveDelta,
    LensRejection,
    LensResourceDelta,
    LensRisk,
    LensWarning,
    WarningLevel,
    WorldStateHint,
)
from app.game.contracts.protocol import GameCandidate
from app.game.contracts.views import ObjectView
from app.game.world.conditions import Ctx
from app.game.world.sim import SimView
from app.game.world.state import CampaignMeta, TimelineGameState
from app.game.world.views import object_view
from app.read_models.analysis import BranchView, FutureLensView
from app.simulation.domain.decisions import DecisionInput
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine

BASELINE = "baseline"
_HINT_FIELDS = ("status", "power", "mode", "infrastructure_state", "access")
_LEVEL_RANK: dict[str, int] = {"none": 0, "caution": 1, "warning": 2, "critical": 3}


@dataclass(slots=True)
class PlannedCandidate:
    id: str
    action: str
    target: str | None
    decisions: list[DecisionInput] = field(default_factory=list)
    rejection: LensRejection | None = None
    hints: list[WorldStateHint] = field(default_factory=list)


def _known_views(ctx: Ctx, ids: Sequence[str]) -> dict[str, ObjectView]:
    idx = ctx.content.index.objects
    return {oid: object_view(ctx, idx[oid]) for oid in ids}


def plan_candidates(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    engine: SimulationEngine,
    state: MissionState,
    candidates: Sequence[GameCandidate],
    actor: str = "commander",
) -> list[PlannedCandidate]:
    """Validate and plan every candidate on copies; never mutates ``doc``/``meta``/``state``."""
    world = content.index.worlds[doc.world_id]
    known = [o.id for o in world.objects if doc.objects[o.id].known]
    now = _known_views(Ctx(content, doc, meta, SimView(engine, state)), known)
    out: list[PlannedCandidate] = []
    for cand in candidates:
        pc = PlannedCandidate(id=cand.id, action=cand.action, target=cand.target)
        out.append(pc)
        d2, m2 = doc.model_copy(deep=True), meta.model_copy(deep=True)
        try:
            p = plan(
                Ctx(content, d2, m2, SimView(engine, state)),
                Command(
                    action=cand.action, target=cand.target, params=dict(cand.params), actor=actor
                ),
            )
            s2 = state
            for d in p.decisions:
                s2 = engine.apply_decision(s2, d, f"lens:{cand.id}").state
            after_ctx = Ctx(content, d2, m2, SimView(engine, s2))
            p.finalize(after_ctx)
        except GameRuleError as exc:
            pc.rejection = LensRejection(reason=exc.reason, message=exc.message)
            continue
        except DecisionRejectedError as exc:
            rule = rule_from_engine(exc)
            pc.rejection = LensRejection(reason=rule.reason, message=rule.message)
            continue
        pc.decisions = list(p.decisions)
        after = _known_views(after_ctx, known)
        for oid in known:
            a, b = now[oid], after[oid]
            for f in _HINT_FIELDS:
                va, vb = getattr(a, f), getattr(b, f)
                if va != vb:
                    pc.hints.append(
                        WorldStateHint(
                            object=oid,
                            field=f,
                            now=None if va is None else str(va),
                            after=None if vb is None else str(vb),
                        )
                    )
    return out


def _level(severity: str) -> WarningLevel:
    """Simulation alert severities are caution < warning < critical."""
    return severity if severity in {"caution", "warning", "critical"} else "caution"  # type: ignore[return-value]


def _branch(
    planned: PlannedCandidate | None, v: BranchView | None, tick_hours: float
) -> LensBranch:
    is_baseline = planned is None
    if planned is not None and planned.rejection is not None:
        return LensBranch(
            id=planned.id,
            is_baseline=False,
            action=planned.action,
            target=planned.target,
            valid=False,
            rejection=planned.rejection,
            affects_simulation=False,
        )
    assert v is not None
    if not v.valid:
        rej = v.rejection
        return LensBranch(
            id=BASELINE if is_baseline else planned.id,  # type: ignore[union-attr]
            is_baseline=is_baseline,
            action=None if planned is None else planned.action,
            target=None if planned is None else planned.target,
            valid=False,
            rejection=LensRejection(reason=rej.reason, message=rej.message) if rej else None,
            affects_simulation=bool(planned and planned.decisions),
        )
    levels: dict[str, WarningLevel] = {}
    for w in v.warnings:
        lvl = _level(w.severity)
        if _LEVEL_RANK[lvl] > _LEVEL_RANK[levels.get(w.metric, "none")]:
            levels[w.metric] = lvl
    hints = planned.hints if planned is not None else []
    return LensBranch(
        id=BASELINE if planned is None else planned.id,
        is_baseline=is_baseline,
        action=None if planned is None else planned.action,
        target=None if planned is None else planned.target,
        valid=True,
        affects_simulation=bool(planned and planned.decisions),
        affected_objects=sorted({h.object for h in hints}),
        world_hints=hints,
        resources=[
            LensResourceDelta(
                metric=r.metric,
                label=r.label,
                unit=r.unit,
                start=r.start,
                end=r.end,
                delta=r.delta,
                worst=r.worst,
                vs_baseline=r.vs_baseline,
                warning_level=levels.get(r.metric, "none"),
            )
            for r in v.resources
        ],
        objectives=[
            LensObjectiveDelta(
                objective=o.objective, status_now=o.status_now, projected_status=o.projected_status
            )
            for o in v.objectives
        ],
        warnings=[
            LensWarning(
                alert=w.alert_id,
                severity=w.severity,
                metric=w.metric,
                hours_from_now=w.hours_from_now,
                introduced_by_candidate=w.introduced_by_candidate,
            )
            for w in v.warnings
        ],
        risk=LensRisk(end_index=v.risk.end_index, peak_index=v.risk.peak_index) if v.risk else None,
        confidence=(
            LensConfidence(level=v.confidence.level, score=v.confidence.score)
            if v.confidence
            else None
        ),
        concludes_within_horizon=v.concludes_within_horizon,
        projected_outcome_tier=v.projected_outcome.tier if v.projected_outcome else None,
    )


def build_game_future_lens(
    view: FutureLensView,
    planned: Sequence[PlannedCandidate],
    *,
    session_id: str,
    timeline_id: str,
    mission_id: str,
    state_version: int,
    tick_hours: float,
) -> GameFutureLensView:
    by_label = {b.label: b for b in view.branches}
    branches = [_branch(None, by_label.get(BASELINE), tick_hours)]
    for pc in planned:
        branches.append(_branch(pc, by_label.get(pc.id), tick_hours))
    kb = view.knowledge_boundary
    return GameFutureLensView(
        session_id=session_id,
        timeline_id=timeline_id,
        mission_id=mission_id,
        state_version=state_version,
        base_tick=view.base_tick,
        base_sim_hours=round(view.base_tick * tick_hours, 3),
        horizon=LensHorizon(
            requested_ticks=view.horizon.requested_ticks,
            projected_ticks=view.horizon.projected_ticks,
            hours=view.horizon.hours,
            clipped_to_mission_end=view.horizon.clipped_to_mission_end,
        ),
        knowledge_boundary=LensKnowledgeBoundary(
            prediction_mode="known_only",
            anticipates_unforeseeable_events=kb.anticipates_unforeseeable_events,
            statement=kb.statement,
        ),
        branches=branches,
    )
