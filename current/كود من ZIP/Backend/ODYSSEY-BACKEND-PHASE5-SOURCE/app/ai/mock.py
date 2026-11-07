"""Deterministic, offline ORION provider.

It composes explanations *only* from context facts and cites every number it uses, so it is
both the development default and the fallback when a real model's answer fails validation.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import Any

from app.ai.context import ContextFact, MissionContext
from app.ai.provider import AIProvider, AIRequest


def _fmt(fact: ContextFact) -> str:
    value = fact.value
    text = f"{value:g}" if isinstance(value, float) else str(value)
    return f"{text} {fact.unit}".strip() if fact.unit and fact.unit != "bool" else text


def _seg(text: str, *cites: str) -> dict[str, Any]:
    return {"text": text, "citations": list(cites)}


class MockAIProvider(AIProvider):
    name = "mock"

    async def complete(self, request: AIRequest) -> str:
        ctx = request.context
        builders = {
            "state_summary": self._summary,
            "why": self._why,
            "decision_impact": self._decision_impact,
            "free_question": self._free,
        }
        segments, unavailable = builders[request.topic](ctx)
        return json.dumps({"segments": segments, "unavailable": unavailable})

    # ------------------------------------------------------------------------------------
    def _summary(self, ctx: MissionContext) -> tuple[list[dict[str, Any]], list[str]]:
        phase = ctx.fact("mission.phase")
        segs = [
            _seg(
                f"The mission is in phase {phase.value if phase else 'unknown'} "
                f"at tick {ctx.tick}.",
                "mission.phase",
                "metric:time.tick",
            )
        ]
        worst = sorted(
            ((sev, name) for name, sev in ctx.severities.items() if sev > 0), reverse=True
        )[:3]
        for _, name in worst:
            fact = ctx.fact(f"metric:{name}")
            if fact is not None:
                segs.append(_seg(f"{fact.label} is {_fmt(fact)}.", fact.id))
        alerts = [f for f in ctx.facts if f.source == "alert"]
        if alerts:
            segs.append(
                _seg(
                    "Active alerts: "
                    + ", ".join(a.id.removeprefix("alert:") for a in alerts)
                    + ".",
                    *[a.id for a in alerts],
                )
            )
        else:
            segs.append(_seg("No alerts are active."))
        return segs, []

    def _why(self, ctx: MissionContext) -> tuple[list[dict[str, Any]], list[str]]:
        trace = ctx.trace
        if trace is None:
            return [], ["causal trace (no target metric was traced)"]
        target = ctx.fact(f"trace:metric:{trace.target_metric}")
        segs: list[dict[str, Any]] = []
        if target is not None:
            segs.append(
                _seg(
                    f"{target.label.split(': ', 1)[-1]} is {_fmt(target)} "
                    f"at tick {trace.target_tick}.",
                    target.id,
                )
            )
        if not trace.chains:
            segs.append(_seg("No upstream cause was found in the recorded state transitions."))
        for chain in trace.chains[:3]:
            labels = []
            cites = []
            for a, b in pairwise(chain):
                edge = ctx.fact(f"trace:{a}->{b}")
                if edge is not None:
                    cites.append(edge.id)
            for node_id in chain:
                fact = ctx.fact(f"trace:{node_id}")
                if fact is not None:
                    labels.append(fact.label.split(": ", 1)[-1])
                    cites.append(fact.id)
            segs.append(_seg("Causal chain: " + " → ".join(labels) + ".", *cites))
        for node in trace.nodes:
            cf = node.details.get("counterfactual")
            if node.kind == "decision" and cf:
                verdict = str(cf["verdict"]).replace("_", " ")
                segs.append(
                    _seg(f"Counterfactual replay for {node.label}: {verdict}.", f"trace:{node.id}")
                )
        return segs, []

    def _decision_impact(self, ctx: MissionContext) -> tuple[list[dict[str, Any]], list[str]]:
        decisions = [f for f in ctx.facts if f.source == "ledger"]
        if not decisions:
            return [], ["decision history (no decisions recorded yet)"]
        last = decisions[-1]
        return [
            _seg(f"The most recent decision was {last.label} at tick {last.value}.", last.id)
        ], []

    def _free(self, ctx: MissionContext) -> tuple[list[dict[str, Any]], list[str]]:
        segs, _ = self._summary(ctx)
        return segs, ["free-form answers beyond recorded mission data"]
