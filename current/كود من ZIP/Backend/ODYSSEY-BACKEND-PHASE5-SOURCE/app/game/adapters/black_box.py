"""Black Box game adapter (``GET /api/game/v1/sessions/{id}/black-box``).

Reuses the established Black Box (``build_black_box`` → the v1 safe read model
``build_black_box_view``) unchanged — including its counterfactual rule: a decision is named a
root cause only when a replay without it makes the failing quantity better. The adapter turns
that report into a node/edge graph Unreal can lay out as a spatial causal timeline:

* ``decision`` nodes are keyed by the game ``command_id`` (ledger decision ids never leave the
  backend) and carry the semantic action/target and the counterfactual status;
* ``trigger``/``effect`` nodes reference the world object bound to the metric when the player
  knows that object (else the public metric id), with its semantic location as ``anchor``;
* ``shortfall``/``outcome``/``moment`` nodes carry objective references and simulation time.

Only the past is described: the report is built from the recorded timeline up to its head.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.game.content.loader import LoadedContent
from app.game.contracts.analysis import (
    BlackBoxOutcome,
    CausalEdge,
    CausalNode,
    CounterfactualStatus,
    DecisionRelation,
    GameBlackBoxView,
)
from app.read_models.analysis import BlackBoxView, DecisionRefView


@dataclass(frozen=True, slots=True)
class CommandRef:
    command_id: str
    action: str
    target: str | None


_VERDICTS: dict[str, CounterfactualStatus] = {
    "decision_worsened_target": "worsened",
    "decision_improved_target": "improved",
    "no_effect": "no_effect",
}


class _Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, CausalNode] = {}
        self.edges: list[CausalEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()

    def node(self, node: CausalNode) -> str:
        self.nodes.setdefault(node.id, node)
        return node.id

    def edge(self, source: str, target: str, relation: str) -> None:
        key = (source, target, relation)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self.edges.append(CausalEdge(source=source, target=target, relation=relation))


def metric_objects(content: LoadedContent, world_id: str, known: set[str]) -> dict[str, str]:
    """Public metric id → known world object bound to it (component health/maintenance,
    consumer supply ratio and mode)."""
    out: dict[str, str] = {}
    for obj in content.index.worlds[world_id].objects:
        if obj.id not in known:
            continue
        b = obj.binding
        if b.component is not None:
            out.setdefault(f"component.{b.component}.health", obj.id)
            out.setdefault(f"component.{b.component}.in_maintenance", obj.id)
        if b.consumer is not None:
            out.setdefault(f"power.supply_ratio.{b.consumer}", obj.id)
            out.setdefault(f"control.mode.{b.consumer}", obj.id)
    return out


def build_game_black_box(
    content: LoadedContent,
    view: BlackBoxView,
    commands: Mapping[str, CommandRef],
    *,
    session_id: str,
    timeline_id: str,
    mission_id: str,
    world_id: str,
    state_version: int,
    tick_hours: float,
    known_objects: set[str],
    mission_status: str,
) -> GameBlackBoxView:
    g = _Graph()
    objs = metric_objects(content, world_id, known_objects)
    index = content.index.objects

    def hours(tick: int | None) -> float | None:
        return None if tick is None else round(tick * tick_hours, 3)

    def anchor_of(object_id: str | None) -> str | None:
        return index[object_id].location if object_id in index else None  # type: ignore[index]

    def decision_node(d: DecisionRefView, status: CounterfactualStatus | None = None) -> str:
        ref = commands.get(d.decision_id)
        cf: CounterfactualStatus = status or _VERDICTS.get(d.verdict, "not_evaluated")
        if not view.counterfactuals_evaluated:
            cf = "not_evaluated"
        nid = f"decision:{ref.command_id}" if ref else f"decision:unattributed:{d.tick}"
        target = ref.target if ref else None
        return g.node(
            CausalNode(
                id=nid,
                type="decision",
                sim_tick=d.tick,
                sim_time_hours=hours(d.tick),
                label=ref.action if ref else (d.decision_type or "decision"),
                system_ref=target if target in known_objects else None,
                anchor=anchor_of(target) if target in known_objects else None,
                decision=DecisionRelation(
                    command_id=ref.command_id if ref else None,
                    action=ref.action if ref else None,
                    target=target,
                    counterfactual=cf,
                ),
            )
        )

    for s in view.shortfalls:
        sid = g.node(
            CausalNode(
                id=f"shortfall:{s.objective}",
                type="shortfall",
                sim_tick=s.resolved_tick if s.resolved_tick is not None else view.final_tick,
                sim_time_hours=hours(
                    s.resolved_tick if s.resolved_tick is not None else view.final_tick
                ),
                label=s.consequence,
                objective_ref=s.objective,
            )
        )
        triggers = []
        for t in s.triggers:
            obj = objs.get(t.metric)
            tid = g.node(
                CausalNode(
                    id=f"trigger:{s.objective}:{t.metric}:{t.tick}",
                    type="trigger",
                    sim_tick=t.tick,
                    sim_time_hours=hours(t.tick),
                    label=f"{t.label} {t.op} {t.threshold:g} {t.unit}".strip(),
                    system_ref=obj or t.metric,
                    objective_ref=s.objective,
                    anchor=anchor_of(obj),
                )
            )
            g.edge(tid, sid, "triggered")
            triggers.append(tid)
        heads = triggers or [sid]
        effects = []
        for e in s.intermediate_effects:
            obj = objs.get(e.metric)
            eid = g.node(
                CausalNode(
                    id=f"effect:{e.metric}",
                    type="effect",
                    sim_tick=None,
                    sim_time_hours=None,
                    label=e.label,
                    system_ref=obj or e.metric,
                    anchor=anchor_of(obj),
                )
            )
            effects.append(eid)
            for h in heads:
                g.edge(eid, h, "contributed")
        entry = effects or heads
        for d in s.root_decisions:
            did = decision_node(d)
            for h in entry:
                g.edge(did, h, "caused")
        for d in s.decisions_on_path_without_effect:
            g.edge(decision_node(d), sid, "on_path_no_effect")
        for c in s.other_causes:
            cid = g.node(
                CausalNode(
                    id=f"cause:{c.id}",
                    type="cause",
                    sim_tick=None,
                    sim_time_hours=None,
                    label=c.label,
                )
            )
            for h in entry:
                g.edge(cid, h, "contributed")

    for km in view.key_moments:
        component = km.data.get("component") if isinstance(km.data, dict) else None
        obj = objs.get(f"component.{component}.health") if isinstance(component, str) else None
        g.node(
            CausalNode(
                id=f"moment:{km.tick}:{km.category}:{km.key}",
                type="moment",
                sim_tick=km.tick,
                sim_time_hours=hours(km.tick),
                label=f"{km.category}.{km.kind}",
                system_ref=obj,
                anchor=anchor_of(obj),
                severity=km.severity,
            )
        )

    outcome = None
    if view.outcome is not None:
        o = view.outcome
        outcome = BlackBoxOutcome(code=o.code, tier=o.tier, sim_tick=o.tick)
        oid = g.node(
            CausalNode(
                id="outcome",
                type="outcome",
                sim_tick=o.tick,
                sim_time_hours=hours(o.tick),
                label=o.message_key,
            )
        )
        for s in view.shortfalls:
            g.edge(f"shortfall:{s.objective}", oid, "led_to")

    nodes = sorted(
        g.nodes.values(),
        key=lambda n: (n.sim_tick if n.sim_tick is not None else -1, n.type, n.id),
    )
    return GameBlackBoxView(
        session_id=session_id,
        timeline_id=timeline_id,
        mission_id=mission_id,
        state_version=state_version,
        mission_status=mission_status,
        simulation_status=view.mission_status,
        final_tick=view.final_tick,
        final_sim_hours=round(view.final_tick * tick_hours, 3),
        outcome=outcome,
        counterfactuals_evaluated=view.counterfactuals_evaluated,
        nodes=nodes,
        edges=g.edges,
        statement=view.statement,
    )
