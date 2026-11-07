"""Root-cause tracing over recorded state transitions.

Given a mission history (effective state per tick) and a target ``(metric, tick)``, the tracer
walks the dependency graph *backwards*:

1. For each parent edge of the current node, look in a lookback window ending at the node's
   anchor tick for a contiguous run where the parent's severity ≥ threshold.
2. If found, the parent is a contributing cause. Evidence recorded: onset tick, value at onset,
   worst value, nominal value. Recurse from the parent's *onset* tick, so causes always precede
   or coincide with their effects. Exception: a parent already degraded when the record starts
   (an initial condition) gets an explicit ``scenario:initial:<metric>`` cause and is searched up
   to its *worst* tick, so a later decision that made it worse is still found.
3. Leaf nodes (controls, environment, components, dust) are resolved through state
   *provenance* to the decision, scenario event, random fault, or natural environment profile
   that set them.
4. Optionally, each root decision is checked by counterfactual replay (same seed, same other
   decisions, this one removed) and the difference in the target metric is attached.

Nothing here is inferred from text or heuristics outside the recorded states and the declared
dependency graph.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.domain.enums import ProvenanceKind
from app.simulation.domain.state import MissionState, Provenance
from app.simulation.engine.conditions import interpolate
from app.simulation.engine.engine import SimulationEngine
from app.simulation.engine.metrics import SeveritySpec

NodeKind = Literal["metric", "decision", "event", "fault", "environment", "scenario", "baseline"]


class TraceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NodeKind
    label: str
    metric: str | None = None
    unit: str | None = None
    ref: str | None = None
    tick: int | None = Field(None, description="Onset tick of the degradation / time of cause")
    value: float | None = Field(None, description="Value at onset")
    nominal: float | None = None
    worst_value: float | None = None
    worst_tick: int | None = None
    severity: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TraceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    mechanism: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RootCauseTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_metric: str
    target_tick: int
    target_value: float
    target_severity: float
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    roots: list[str]
    chains: list[list[str]] = Field(description="Root → … → target paths (node ids)")
    parameters: dict[str, Any]


Counterfactual = Callable[[str], Sequence[MissionState] | None]
"""decision_id → history (indexed like the input history) of a replay without that decision."""


@dataclass(slots=True)
class _Tracer:
    engine: SimulationEngine
    history: Sequence[MissionState]
    start_tick: int
    lookback: int
    threshold: float
    max_depth: int
    decision_info: dict[str, dict[str, Any]]
    nodes: dict[str, TraceNode] = field(default_factory=dict)
    edges: dict[tuple[str, str], TraceEdge] = field(default_factory=dict)
    sev_cache: dict[tuple[str, int], float] = field(default_factory=dict)

    # -------------------------------------------------------------------------- helpers
    def state_at(self, tick: int) -> MissionState:
        idx = min(max(0, tick - self.start_tick), len(self.history) - 1)
        return self.history[idx]

    def sev(self, metric: str, tick: int) -> float:
        key = (metric, tick)
        if key not in self.sev_cache:
            self.sev_cache[key] = self.engine.metrics.severity(metric, self.state_at(tick))
        return self.sev_cache[key]

    def val(self, metric: str, tick: int) -> float:
        return self.engine.metrics.value(metric, self.state_at(tick))

    def degraded_run(self, metric: str, anchor: int) -> tuple[int, int, int] | None:
        """Latest contiguous run with severity ≥ threshold ending at or before ``anchor``.

        Returns (onset, end, worst_tick) or None.
        """
        lo = max(self.start_tick, anchor - self.lookback)
        t = anchor
        while t >= lo and self.sev(metric, t) < self.threshold:
            t -= 1
        if t < lo:
            return None
        end = t
        while t - 1 >= lo and self.sev(metric, t - 1) >= self.threshold:
            t -= 1
        onset = t
        worst = max(range(onset, end + 1), key=lambda k: (self.sev(metric, k), -k))
        return onset, end, worst

    def add_edge(self, source: str, target: str, mechanism: str, **evidence: Any) -> None:
        key = (source, target)
        if key not in self.edges:
            self.edges[key] = TraceEdge(
                source=source, target=target, mechanism=mechanism, evidence=evidence
            )

    def metric_node(self, metric: str, onset: int, worst: int) -> str:
        node_id = f"metric:{metric}"
        if node_id not in self.nodes:
            spec = self.engine.metrics.spec(metric)
            sev: SeveritySpec | None = spec.severity
            self.nodes[node_id] = TraceNode(
                id=node_id,
                kind="metric",
                label=spec.label,
                metric=metric,
                unit=spec.unit,
                tick=onset,
                value=self.val(metric, onset),
                nominal=sev.nominal if sev else None,
                worst_value=self.val(metric, worst),
                worst_tick=worst,
                severity=self.sev(metric, worst),
            )
        return node_id

    # -------------------------------------------------------------------------- provenance
    def provenance_node(self, prov: Provenance, label_hint: str) -> str:
        if prov.kind == ProvenanceKind.DECISION:
            node_id = f"decision:{prov.ref}"
            if node_id not in self.nodes:
                info = self.decision_info.get(prov.ref, {})
                self.nodes[node_id] = TraceNode(
                    id=node_id,
                    kind="decision",
                    ref=prov.ref,
                    tick=prov.tick,
                    label=f"Decision {info.get('decision_type', label_hint)}",
                    details={
                        k: v
                        for k, v in info.items()
                        if k in ("decision_type", "inputs", "phase", "sequence")
                    },
                )
            return node_id
        if prov.kind == ProvenanceKind.EVENT:
            node_id = f"event:{prov.ref}"
            if node_id not in self.nodes:
                self.nodes[node_id] = TraceNode(
                    id=node_id,
                    kind="event",
                    ref=prov.ref,
                    tick=prov.tick,
                    label=f"Event {prov.ref}",
                )
            return node_id
        if prov.kind == ProvenanceKind.ENGINE and prov.ref.startswith("fault:"):
            node_id = f"fault:{prov.ref}"
            if node_id not in self.nodes:
                self.nodes[node_id] = TraceNode(
                    id=node_id,
                    kind="fault",
                    ref=prov.ref,
                    tick=prov.tick,
                    label=f"Random fault {prov.ref.split(':')[1]}",
                )
            return node_id
        node_id = f"scenario:{label_hint}"
        if node_id not in self.nodes:
            self.nodes[node_id] = TraceNode(
                id=node_id,
                kind="scenario",
                ref=prov.ref,
                tick=prov.tick,
                label=f"Scenario initial setting ({label_hint})",
            )
        return node_id

    def resolve_leaf(self, metric: str, onset: int, end: int) -> list[str]:
        """Return node ids of the causes behind a control/env/component/dust node."""
        sc = self.engine.scenario
        st = self.state_at(onset)
        st_end = self.state_at(end)
        out: list[str] = []
        if metric.startswith("control.mode."):
            cid = metric.removeprefix("control.mode.")
            out.append(self.provenance_node(st.power.consumers[cid].mode_set_by, metric))
        elif metric == "control.thermal_setpoint":
            out.append(self.provenance_node(st.thermal.setpoint_set_by, metric))
        elif metric == "control.ration_level":
            out.append(self.provenance_node(st.food.ration_set_by, metric))
        elif metric == "control.boost_load_kw":
            for c in sorted(st.power.consumers.values(), key=lambda c: c.id):
                if c.mode == "boost":
                    out.append(self.provenance_node(c.mode_set_by, metric))
        elif metric == "control.discretionary_load_kw":
            active = st.science.active_opportunity
            if active and st.science.opportunities[active].started_by is not None:
                prov = st.science.opportunities[active].started_by
                assert prov is not None
                out.append(self.provenance_node(prov, metric))
            if st.power.consumers[sc.power.rover_charger_consumer].demand_kw > 0:
                out.append(self.provenance_node(st.rover.status_set_by, metric))
        elif metric.startswith("component.") and metric.endswith(".health"):
            cid = metric.split(".")[1]
            damage = st_end.components[cid].last_damage
            if damage is not None and damage.tick <= end:
                out.append(self.provenance_node(damage, metric))
            else:
                out.append(self._baseline(metric, "Gradual wear (no discrete fault recorded)"))
        elif metric == "power.dust_factor":
            out.append(
                self._environment(
                    "dust_accumulation", "Natural regolith dust accumulation on the array", onset
                )
            )
        elif metric.startswith("env."):
            target = metric
            mods = [m for m in st_end.modifiers if m.target == target and m.start_tick <= end]
            for m in sorted({m.event_id: m for m in mods}.values(), key=lambda m: m.start_tick):
                out.append(
                    self.provenance_node(
                        Provenance(kind=ProvenanceKind.EVENT, ref=m.event_id, tick=m.start_tick),
                        metric,
                    )
                )
            base = self._profile_severity(metric, onset)
            if base >= self.threshold or not out:
                out.append(
                    self._environment(
                        metric.removeprefix("env."),
                        f"Natural environment profile ({self.engine.metrics.spec(metric).label})",
                        onset,
                    )
                )
        return out

    def _profile_severity(self, metric: str, tick: int) -> float:
        env = self.engine.scenario.environment
        env_field = metric.removeprefix("env.")
        frames = getattr(env, env_field, None)
        spec = self.engine.metrics.spec(metric).severity
        if frames is None or spec is None:
            return 0.0
        return spec.severity(interpolate([(f.tick, f.value) for f in frames], tick))

    def _environment(self, key: str, label: str, tick: int) -> str:
        node_id = f"environment:{key}"
        if node_id not in self.nodes:
            self.nodes[node_id] = TraceNode(id=node_id, kind="environment", label=label, tick=tick)
        return node_id

    def _initial_condition(self, metric: str) -> str:
        node_id = f"scenario:initial:{metric}"
        if node_id not in self.nodes:
            self.nodes[node_id] = TraceNode(
                id=node_id,
                kind="scenario",
                label="Initial condition: already degraded at the start of the record",
                metric=metric,
                tick=self.start_tick,
            )
        return node_id

    def _baseline(self, metric: str, label: str) -> str:
        node_id = f"baseline:{metric}"
        if node_id not in self.nodes:
            self.nodes[node_id] = TraceNode(id=node_id, kind="baseline", label=label, metric=metric)
        return node_id

    # -------------------------------------------------------------------------- walk
    def is_leaf(self, metric: str) -> bool:
        return (
            self.engine.graph.is_root_namespace(metric)
            or (metric.startswith("component.") and metric.endswith(".health"))
            or metric == "power.dust_factor"
        )

    def visit(self, metric: str, anchor: int, depth: int, path: frozenset[str]) -> None:
        node_id = f"metric:{metric}"
        if self.is_leaf(metric):
            leaf_run = self.degraded_run(metric, anchor) or (anchor, anchor, anchor)
            for cause in self.resolve_leaf(metric, leaf_run[0], leaf_run[1]):
                self.add_edge(
                    cause,
                    node_id,
                    "set the value of this quantity",
                    cause_tick=self.nodes[cause].tick,
                )
            return
        found = False
        for edge in self.engine.graph.parents(metric):
            if edge.source in path:
                continue
            run = self.degraded_run(edge.source, anchor)
            if run is None:
                continue
            onset, _end, worst = run
            found = True
            parent_id = self.metric_node(edge.source, onset, worst)
            self.add_edge(
                parent_id,
                node_id,
                edge.mechanism,
                source_onset_tick=onset,
                source_worst_tick=worst,
                source_peak_severity=self.sev(edge.source, worst),
                target_anchor_tick=anchor,
            )
            if depth < self.max_depth:
                # A parent degraded since the start of the record (initial conditions) may have
                # been made *worse* later; search its causes up to its worst point (still ≤ this
                # node's anchor, so causes keep preceding effects) and name the starting state.
                next_anchor = onset
                if onset == self.start_tick and not self.is_leaf(edge.source):
                    next_anchor = worst
                    self.add_edge(
                        self._initial_condition(edge.source),
                        parent_id,
                        "already degraded when the record starts",
                    )
                self.visit(edge.source, next_anchor, depth + 1, path | {edge.source})
        if not found:
            baseline = self._baseline(
                metric,
                "No upstream degradation found: driven by this subsystem's own "
                "dynamics (e.g. normal consumption)",
            )
            self.add_edge(baseline, node_id, "intrinsic dynamics")


def trace_root_cause(
    engine: SimulationEngine,
    history: Sequence[MissionState],
    target_metric: str,
    target_tick: int,
    *,
    start_tick: int | None = None,
    lookback_ticks: int = 72,
    threshold: float = 0.2,
    max_depth: int = 8,
    decision_info: dict[str, dict[str, Any]] | None = None,
    counterfactual: Counterfactual | None = None,
    max_counterfactuals: int = 5,
) -> RootCauseTrace:
    """Build a causal trace for ``target_metric`` at ``target_tick``.

    ``history[i]`` must be the effective state at tick ``start_tick + i`` (default: the first
    history entry's tick).
    """
    if not history:
        raise ValueError("history is empty")
    engine.metrics.spec(target_metric)  # raises UnknownMetricError early
    base = history[0].tick if start_tick is None else start_tick
    last = base + len(history) - 1
    if not base <= target_tick <= last:
        raise ValueError(f"target tick {target_tick} outside history [{base}, {last}]")

    tracer = _Tracer(
        engine, history, base, lookback_ticks, threshold, max_depth, decision_info or {}
    )
    target_id = f"metric:{target_metric}"
    tracer.nodes[target_id] = TraceNode(
        id=target_id,
        kind="metric",
        label=engine.metrics.spec(target_metric).label,
        metric=target_metric,
        unit=engine.metrics.spec(target_metric).unit,
        tick=target_tick,
        value=tracer.val(target_metric, target_tick),
        severity=tracer.sev(target_metric, target_tick),
    )
    tracer.visit(target_metric, target_tick, 0, frozenset({target_metric}))

    has_incoming = {e.target for e in tracer.edges.values()}
    roots = sorted(n for n in tracer.nodes if n not in has_incoming and n != target_id)

    if counterfactual is not None:
        _attach_counterfactuals(
            engine,
            tracer,
            target_metric,
            target_tick,
            base,
            roots,
            counterfactual,
            max_counterfactuals,
        )

    return RootCauseTrace(
        target_metric=target_metric,
        target_tick=target_tick,
        target_value=tracer.val(target_metric, target_tick),
        target_severity=tracer.sev(target_metric, target_tick),
        nodes=sorted(
            tracer.nodes.values(), key=lambda n: (n.tick if n.tick is not None else -1, n.id)
        ),
        edges=sorted(tracer.edges.values(), key=lambda e: (e.source, e.target)),
        roots=roots,
        chains=_chains(tracer.edges.values(), roots, target_id),
        parameters={
            "lookback_ticks": lookback_ticks,
            "severity_threshold": threshold,
            "max_depth": max_depth,
            "method": "dependency-graph walk over recorded "
            "state transitions + provenance + optional counterfactual replay",
        },
    )


def _attach_counterfactuals(
    engine: SimulationEngine,
    tracer: _Tracer,
    metric: str,
    tick: int,
    base: int,
    roots: list[str],
    counterfactual: Counterfactual,
    limit: int,
) -> None:
    decisions = [r for r in roots if r.startswith("decision:")][:limit]
    actual = tracer.val(metric, tick)
    actual_sev = tracer.sev(metric, tick)
    for node_id in decisions:
        decision_id = node_id.removeprefix("decision:")
        alt = counterfactual(decision_id)
        if not alt:
            continue
        idx = min(max(0, tick - base), len(alt) - 1)
        alt_value = engine.metrics.value(metric, alt[idx])
        alt_sev = engine.metrics.severity(metric, alt[idx])
        # Compare raw values in the metric's "bad" direction so saturated severities (both 1.0)
        # still yield a verdict.
        spec = engine.metrics.spec(metric).severity
        sign = -1.0 if spec is not None and spec.direction == "below" else 1.0
        badness_delta = sign * (actual - alt_value)  # > 0: worse with the decision
        tolerance = 1e-6 * max(1.0, abs(actual), abs(alt_value))
        verdict = "no_effect"
        if badness_delta > tolerance:
            verdict = "decision_worsened_target"
        elif badness_delta < -tolerance:
            verdict = "decision_improved_target"
        tracer.nodes[node_id].details["counterfactual"] = {
            "target_metric": metric,
            "target_tick": tick,
            "with_decision_value": actual,
            "without_decision_value": alt_value,
            "with_decision_severity": actual_sev,
            "without_decision_severity": alt_sev,
            "verdict": verdict,
        }


def _chains(edges: Any, roots: list[str], target: str, limit: int = 12) -> list[list[str]]:
    children: dict[str, list[str]] = {}
    for e in edges:
        children.setdefault(e.source, []).append(e.target)
    out: list[list[str]] = []

    def walk(node: str, path: list[str]) -> None:
        if len(out) >= limit:
            return
        if node == target:
            out.append(path)
            return
        for nxt in sorted(children.get(node, [])):
            if nxt not in path:
                walk(nxt, [*path, nxt])

    for root in roots:
        walk(root, [root])
    return out
