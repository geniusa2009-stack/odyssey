"""Cross-reference validation of game content.

Every reference must resolve: ids, stages, metrics, simulation events/alerts, engine decisions
(type-checked against the mission scenario for every parameter combination), container limits,
module compatibility, provenance evidence and acyclic prerequisites. Returns a list of problems
(empty = valid) so a content author sees every issue at once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import ValidationError

from app.game.content.loader import LoadedContent
from app.game.content.rendering import (
    all_param_assignments,
    param_effects,
    rendered_decisions,
)
from app.game.content.schema import (
    CapReq,
    Effects,
    GameCondition,
    Interaction,
    Prerequisites,
    Provenance,
    WorldObject,
)
from app.game.content.vocabulary import ACTION_TYPES, CAMPAIGN_PHASES, INTERACTION_ACTIONS
from app.science.evidence import default_registry
from app.simulation.domain.decisions import parse_decision
from app.simulation.engine.metrics import MetricRegistry
from app.simulation.scenarios.schema import ScenarioDefinition

_VERIFIED = {"verified_primary", "verified_secondary"}
_ACCESS = {"open", "locked", "restricted", "inspection_ready"}


class _V:
    def __init__(self, loaded: LoadedContent) -> None:
        self.c = loaded.content
        self.ix = loaded.index
        self.scenarios = loaded.scenarios
        self.metrics = {sid: MetricRegistry(s) for sid, s in loaded.scenarios.items()}
        self.problems: list[str] = []
        registry = default_registry()
        self.science = {e.id: e.verification_status for e in registry.all()}

    def err(self, where: str, msg: str) -> None:
        self.problems.append(f"{where}: {msg}")

    # ------------------------------------------------------------------ helpers
    def world_scenarios(self, world_id: str) -> list[ScenarioDefinition]:
        ids = {m.scenario.id for m in self.c.campaign.missions if m.world == world_id}
        return [self.scenarios[i] for i in sorted(ids) if i in self.scenarios]

    def cap_req(self, where: str, req: CapReq) -> None:
        cap = self.ix.capabilities.get(req.capability)
        if cap is None:
            self.err(where, f"unknown capability {req.capability}")
        elif req.stage not in cap.stages:
            self.err(where, f"capability {req.capability} has no stage {req.stage}")

    def provenance(self, where: str, p: Provenance) -> None:
        for ref in p.evidence_refs:
            if ref not in self.science:
                self.err(where, f"unknown science evidence {ref}")
        if p.classification == "verified_evidence":
            if not p.evidence_refs:
                self.err(where, "verified_evidence must cite science evidence")
            for ref in p.evidence_refs:
                if ref in self.science and self.science[ref] not in _VERIFIED:
                    self.err(where, f"verified_evidence cites unverified evidence {ref}")
        elif p.classification != "unverified":
            for ref in p.evidence_refs:
                if ref in self.science and self.science[ref] not in _VERIFIED:
                    self.err(where, f"cites unverified evidence {ref}; classify as unverified")

    def walk(self, cond: GameCondition) -> Iterator[GameCondition]:
        yield cond
        for child in (cond.all or []) + (cond.any or []):
            yield from self.walk(child)
        if cond.not_ is not None:
            yield from self.walk(cond.not_)

    def condition(
        self, where: str, cond: GameCondition | None, scenarios: list[ScenarioDefinition]
    ) -> None:
        if cond is None:
            return
        for c in self.walk(cond):
            if c.location is not None and c.location not in self.ix.locations:
                self.err(where, f"unknown location {c.location}")
            if c.incident is not None:
                inc = self.ix.incidents.get(c.incident.id)
                if inc is None:
                    self.err(where, f"unknown incident {c.incident.id}")
                else:
                    stages = {s.id for s in inc.stages}
                    for s in c.incident.stages:
                        if s not in stages:
                            self.err(where, f"incident {inc.id} has no stage {s}")
            if c.sim is not None:
                if not scenarios:
                    self.err(where, "simulation condition outside any mission scenario")
                for metric in c.sim.metrics():
                    missing = [s.id for s in scenarios if not self.metrics[s.id].has(metric)]
                    if missing and len(missing) == len(scenarios):
                        self.err(where, f"unknown simulation metric {metric}")
            if c.sim_event is not None and not any(
                c.sim_event in {e.id for e in s.events} for s in scenarios
            ):
                self.err(where, f"unknown simulation event {c.sim_event}")
            if c.alert is not None and not any(
                c.alert in {a.id for a in s.alerts} for s in scenarios
            ):
                self.err(where, f"unknown simulation alert {c.alert}")
            if c.item is not None:
                if c.item.item not in self.ix.items:
                    self.err(where, f"unknown item {c.item.item}")
                if c.item.container is not None:
                    self.container_ref(where, c.item.container)
            if c.module_installed is not None:
                self.slot_ref(where, c.module_installed.host, c.module_installed.slot)
                mod = c.module_installed.module
                if mod is not None and mod not in self.ix.items:
                    self.err(where, f"unknown module {mod}")
            if c.capability is not None:
                self.cap_req(where, c.capability)
            if c.object_state is not None and c.object_state.object not in self.ix.objects:
                self.err(where, f"unknown object {c.object_state.object}")
            if c.mission is not None and c.mission.mission not in self.ix.missions:
                self.err(where, f"unknown mission {c.mission.mission}")

    def container_ref(self, where: str, object_id: str) -> None:
        obj = self.ix.objects.get(object_id)
        if obj is None:
            self.err(where, f"unknown container {object_id}")
        elif obj.container is None:
            self.err(where, f"object {object_id} is not a container")

    def slot_ref(self, where: str, host_id: str, slot_id: str) -> None:
        host = self.ix.objects.get(host_id)
        if host is None:
            self.err(where, f"unknown module host {host_id}")
            return
        if host.vehicle_class is not None:
            vc = self.ix.vehicle_classes.get(host.vehicle_class)
            if vc is not None and slot_id not in {s.id for s in vc.slots}:
                self.err(where, f"vehicle class {vc.id} has no slot {slot_id}")
        elif host.infrastructure_type is None:
            self.err(where, f"object {host_id} cannot host modules")

    def effects(self, where: str, e: Effects) -> None:
        for upd in e.object_updates:
            if upd.object not in self.ix.objects:
                self.err(where, f"unknown object {upd.object}")
            if upd.field == "access" and upd.value not in _ACCESS:
                self.err(where, f"invalid access value {upd.value}")
            if upd.field in {"operational", "known"} and not isinstance(upd.value, bool):
                self.err(where, f"{upd.field} must be a boolean")
        for loc in e.location_access:
            if loc not in self.ix.locations:
                self.err(where, f"unknown location {loc}")
        for i in e.insights:
            if i not in self.ix.insights:
                self.err(where, f"unknown insight {i}")
        for d in e.discoveries:
            if d not in self.ix.discoveries:
                self.err(where, f"unknown discovery {d}")
        for ev in e.evidence:
            if ev not in self.ix.evidence:
                self.err(where, f"unknown capability evidence {ev}")
        for iq in e.add_items:
            if iq.item not in self.ix.items:
                self.err(where, f"unknown item {iq.item}")
        if e.add_items_to is not None:
            self.container_ref(where, e.add_items_to)
        for ci in e.crew_intents:
            if ci.crew not in self.ix.crew:
                self.err(where, f"unknown crew {ci.crew}")

    def prerequisites(self, where: str, p: Prerequisites, before_order: int | None = None) -> None:
        for ph in p.phases_completed:
            phase = self.ix.phases.get(ph)
            if phase is None:
                self.err(where, f"unknown phase {ph}")
            elif before_order is not None and phase.order >= before_order:
                self.err(where, f"phase prerequisite {ph} must come earlier")
        for m in p.missions_completed:
            if m not in self.ix.missions:
                self.err(where, f"unknown mission {m}")
        for req in p.capabilities:
            self.cap_req(where, req)
        for d in p.discoveries:
            if d not in self.ix.discoveries:
                self.err(where, f"unknown discovery {d}")
        for cert in p.certifications:
            if cert not in self.ix.certifications:
                self.err(where, f"unknown certification {cert}")
        if p.readiness_profile is not None and p.readiness_profile not in self.ix.profiles:
            self.err(where, f"unknown readiness profile {p.readiness_profile}")

    # ------------------------------------------------------------------ sections
    def unique(self, kind: str, ids: Iterable[str]) -> None:
        for value, n in Counter(ids).items():
            if n > 1:
                self.err(kind, f"duplicate id {value}")

    def run(self) -> list[str]:
        c = self.c
        worlds = c.worlds
        self.unique("worlds", (w.id for w in worlds))
        self.unique("locations", (loc.id for w in worlds for loc in w.locations))
        self.unique("objects", (o.id for w in worlds for o in w.objects))
        self.unique("incidents", (i.id for w in worlds for i in w.incidents))
        self.unique("discoveries", (d.id for w in worlds for d in w.discoveries))
        self.unique("regions", (r.id for w in worlds for r in w.regions))
        self.unique("phases", (p.id for p in c.campaign.phases))
        self.unique("missions", (m.id for m in c.campaign.missions))
        self.unique("capabilities", (x.id for x in c.progression.capabilities))
        self.unique("certifications", (x.id for x in c.progression.certifications))
        self.unique("evidence", (x.id for x in c.progression.evidence))
        self.unique("stages", (x.id for x in c.progression.stages))
        self.unique("items", (x.id for x in c.catalog.items))
        self.unique("vehicle_classes", (x.id for x in c.catalog.vehicle_classes))
        self.unique("infrastructure_types", (x.id for x in c.catalog.infrastructure_types))
        self.unique("insights", (x.id for x in c.knowledge.insights))
        self.unique("crew", (x.id for x in c.narrative.crew))
        self.unique("cues", (x.id for x in c.narrative.cues))
        self.unique("readiness", (x.id for x in c.readiness.profiles))
        self.campaign()
        self.progression()
        self.catalog()
        for world in worlds:
            self.world(world.id)
        self.knowledge_and_narrative()
        self.readiness()
        return self.problems

    def campaign(self) -> None:
        phases = self.c.campaign.phases
        if tuple(p.id for p in sorted(phases, key=lambda p: p.order)) != CAMPAIGN_PHASES:
            self.err("campaign", f"phases must be exactly {list(CAMPAIGN_PHASES)} in order")
        if sorted(p.order for p in phases) != list(range(1, len(phases) + 1)):
            self.err("campaign", "phase orders must be 1..N without gaps")
        for p in phases:
            where = f"phase {p.id}"
            if p.authored and not p.missions:
                self.err(where, "an authored phase needs at least one mission")
            if not p.authored and p.missions:
                self.err(where, "an unauthored phase cannot list missions")
            for mid in p.missions:
                mission = self.ix.missions.get(mid)
                if mission is None:
                    self.err(where, f"unknown mission {mid}")
                elif mission.phase != p.id:
                    self.err(where, f"mission {mid} belongs to phase {mission.phase}")
            self.prerequisites(where, p.prerequisites, p.order)
        for m in self.c.campaign.missions:
            where = f"mission {m.id}"
            if m.phase not in self.ix.phases:
                self.err(where, f"unknown phase {m.phase}")
            elif m.id not in self.ix.phases[m.phase].missions:
                self.err(where, f"phase {m.phase} does not list this mission")
            if m.world not in self.ix.worlds:
                self.err(where, f"unknown world {m.world}")
                continue
            if self.ix.location_world.get(m.start_location) != m.world:
                self.err(where, f"start location {m.start_location} is not in world {m.world}")
            if m.player_kit is not None:
                self.container_ref(where, m.player_kit)
                if self.ix.object_world.get(m.player_kit) != m.world:
                    self.err(where, f"player kit {m.player_kit} is not in world {m.world}")
            scenarios = [self.scenarios[m.scenario.id]] if m.scenario.id in self.scenarios else []
            if m.completion.gate is not None:
                gate = m.completion.gate
                if gate.target not in self.ix.objects:
                    self.err(where, f"unknown gate target {gate.target}")
                self.unique(f"{where} gate", (r.id for r in gate.requirements))
                for r in gate.requirements:
                    self.condition(f"{where} gate {r.id}", r.when, scenarios)
            for rule in m.completion_evidence:
                if rule.evidence not in self.ix.evidence:
                    self.err(where, f"unknown capability evidence {rule.evidence}")
                self.condition(f"{where} evidence {rule.evidence}", rule.when, scenarios)
            self.prerequisites(where, m.prerequisites)
            nxt = m.next
            if nxt is not None:
                if nxt.phase not in self.ix.phases:
                    self.err(where, f"unknown next phase {nxt.phase}")
                if nxt.mission is not None and nxt.mission not in self.ix.missions:
                    self.err(where, f"unknown next mission {nxt.mission}")
            for carry in m.carry:
                self.container_ref(where, carry.from_object)
                self.container_ref(where, carry.to_object)
                if self.ix.object_world.get(carry.from_object) != m.world:
                    self.err(where, f"carry source {carry.from_object} is not in world {m.world}")
                nm = self.ix.missions.get(nxt.mission) if nxt and nxt.mission else None
                if nm is None:
                    self.err(where, "carry rules need a next mission")
                elif self.ix.object_world.get(carry.to_object) != nm.world:
                    self.err(where, f"carry target {carry.to_object} is not in world {nm.world}")
                else:
                    src = self.ix.objects.get(carry.from_object)
                    dst = self.ix.objects.get(carry.to_object)
                    if src and dst and src.container and dst.container:
                        sl, dl = src.container.mass_limit_kg, dst.container.mass_limit_kg
                        if dl is not None and (sl is None or sl > dl):
                            self.err(where, f"carry target {dst.id} is smaller than {src.id}")

    def progression(self) -> None:
        order = self.ix.stage_order
        for cap in self.c.progression.capabilities:
            where = f"capability {cap.id}"
            if not cap.id.startswith(f"{cap.domain}."):
                self.err(where, f"id must start with its domain '{cap.domain}.'")
            for s in cap.stages:
                if s not in order:
                    self.err(where, f"unknown stage {s}")
            ranks = [order.get(s, 0) for s in cap.stages]
            if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
                self.err(where, "stages must be distinct and in ascending order")
            for stage, evs in cap.evidence.items():
                if stage not in cap.stages:
                    self.err(where, f"evidence for stage {stage} not in its stages")
                for ev in evs:
                    if ev not in self.ix.evidence:
                        self.err(where, f"unknown capability evidence {ev}")
            for req in cap.prerequisites:
                self.cap_req(where, req)
            for unlock in cap.unlocks:
                if unlock not in self.ix.phases:
                    self.err(where, f"unknown unlocked phase {unlock}")
            self.provenance(where, cap.provenance)
        # acyclic capability prerequisites
        graph = {
            c.id: [r.capability for r in c.prerequisites] for c in self.c.progression.capabilities
        }
        state: dict[str, int] = {}

        def visit(node: str, path: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                self.err("capabilities", f"prerequisite cycle: {' -> '.join([*path, node])}")
                return
            state[node] = 1
            for nxt in graph.get(node, []):
                visit(nxt, [*path, node])
            state[node] = 2

        for node in sorted(graph):
            visit(node, [])
        for cert in self.c.progression.certifications:
            where = f"certification {cert.id}"
            for req in cert.requires:
                self.cap_req(where, req)
            for m in cert.granted_on_completion_of:
                if m not in self.ix.missions:
                    self.err(where, f"unknown mission {m}")
            self.provenance(where, cert.provenance)

    def catalog(self) -> None:
        for item in self.c.catalog.items:
            where = f"item {item.id}"
            if not item.id.startswith(f"{item.category}."):
                self.err(where, f"id must start with its category '{item.category}.'")
            if not item.stackable and item.max_stack != 1:
                self.err(where, "non-stackable items need max_stack 1")
            self.provenance(where, item.provenance)
            if item.module is not None and item.module.qualification is not None:
                self.cap_req(where, item.module.qualification)
        for vc in self.c.catalog.vehicle_classes:
            where = f"vehicle class {vc.id}"
            self.unique(f"{where} slots", (s.id for s in vc.slots))
            for req in vc.qualification:
                self.cap_req(where, req)
            self.provenance(where, vc.provenance)
        for it in self.c.catalog.infrastructure_types:
            where = f"infrastructure type {it.id}"
            for req in it.requires_capabilities:
                self.cap_req(where, req)
            self.provenance(where, it.provenance)

    def world(self, world_id: str) -> None:
        world = self.ix.worlds[world_id]
        scenarios = self.world_scenarios(world_id)
        if not scenarios:
            self.err(f"world {world_id}", "no mission uses this world")
        regions = {r.id for r in world.regions}
        locations = {loc.id for loc in world.locations}
        for loc in world.locations:
            where = f"location {loc.id}"
            if loc.region not in regions:
                self.err(where, f"unknown region {loc.region}")
            self.condition(where, loc.unlock_when, scenarios)
        unique_seen: Counter[str] = Counter()
        for obj in world.objects:
            self.world_object(obj, locations, scenarios, unique_seen)
        for item_id, n in unique_seen.items():
            if n > 1:
                self.err(f"world {world_id}", f"unique item {item_id} placed {n} times")
        for inc in world.incidents:
            where = f"incident {inc.id}"
            mission = self.ix.missions.get(inc.mission)
            if mission is None:
                self.err(where, f"unknown mission {inc.mission}")
            elif mission.world != world_id:
                self.err(where, f"mission {inc.mission} is not played in world {world_id}")
            self.condition(f"{where} trigger", inc.trigger, scenarios)
            for o in inc.involved_objects:
                if self.ix.object_world.get(o) != world_id:
                    self.err(where, f"involved object {o} not in world {world_id}")
            for crew in inc.involved_crew:
                if crew not in self.ix.crew:
                    self.err(where, f"unknown crew {crew}")
            self.effects(f"{where} start", inc.start_effects)
            self.unique(f"{where} stages", (s.id for s in inc.stages))
            for st in inc.stages:
                self.condition(f"{where} stage {st.id}", st.when, scenarios)
                self.effects(f"{where} stage {st.id}", st.effects)
            if inc.stages[-1].when is not None:
                self.err(where, "the last (lowest-priority) stage must be unconditional")
            if not any(s.terminal for s in inc.stages):
                self.err(where, "an incident needs a terminal (resolved) stage")
            for fact in inc.facts:
                self.condition(f"{where} fact {fact.id}", fact.when, scenarios)
        for disc in world.discoveries:
            where = f"discovery {disc.id}"
            if disc.location not in locations:
                self.err(where, f"location {disc.location} not in world {world_id}")
            for i in disc.insights:
                if i not in self.ix.insights:
                    self.err(where, f"unknown insight {i}")
            for ev in disc.capability_evidence:
                if ev not in self.ix.evidence:
                    self.err(where, f"unknown capability evidence {ev}")
            self.provenance(where, disc.provenance)

    def world_object(
        self,
        obj: WorldObject,
        locations: set[str],
        scenarios: list[ScenarioDefinition],
        unique_seen: Counter[str],
    ) -> None:
        where = f"object {obj.id}"
        if obj.location not in locations:
            self.err(where, f"location {obj.location} not in its world")
        if obj.parent is not None:
            parent = self.ix.objects.get(obj.parent)
            if parent is None:
                self.err(where, f"unknown parent {obj.parent}")
            elif not obj.id.startswith(f"{obj.parent}."):
                self.err(where, f"id must extend its parent id {obj.parent}")
        if obj.vehicle_class is not None and obj.vehicle_class not in self.ix.vehicle_classes:
            self.err(where, f"unknown vehicle class {obj.vehicle_class}")
        if (
            obj.infrastructure_type is not None
            and obj.infrastructure_type not in self.ix.infrastructure_types
        ):
            self.err(where, f"unknown infrastructure type {obj.infrastructure_type}")
        b = obj.binding
        for s in scenarios:
            consumers = {cs.id for cs in s.power.consumers}
            components = {cp.id for cp in s.degradation.components}
            opportunities = {op.id for op in s.science.opportunities}
            if b.consumer is not None and b.consumer not in consumers:
                self.err(where, f"scenario {s.id} has no consumer {b.consumer}")
            if b.component is not None and b.component not in components:
                self.err(where, f"scenario {s.id} has no component {b.component}")
            if b.opportunity is not None and b.opportunity not in opportunities:
                self.err(where, f"scenario {s.id} has no opportunity {b.opportunity}")
        # containers
        if obj.container is not None:
            spec = obj.container
            mass = 0.0
            volume = 0.0
            for iq in spec.initial:
                item = self.ix.items.get(iq.item)
                if item is None:
                    self.err(where, f"unknown item {iq.item}")
                    continue
                if spec.accepts and item.category not in spec.accepts:
                    self.err(where, f"does not accept {item.category} item {item.id}")
                if item.stackable and iq.quantity > item.max_stack:
                    self.err(where, f"{item.id} exceeds max stack {item.max_stack}")
                if item.unique:
                    unique_seen[item.id] += iq.quantity
                mass += item.mass_kg * iq.quantity
                volume += (item.volume_l or 0.0) * iq.quantity
            if spec.mass_limit_kg is not None and mass > spec.mass_limit_kg:
                self.err(where, f"initial mass {mass} kg exceeds limit {spec.mass_limit_kg}")
            if spec.volume_limit_l is not None and volume > spec.volume_limit_l:
                self.err(where, f"initial volume {volume} L exceeds limit {spec.volume_limit_l}")
        # installed modules
        for slot_id, module_id in obj.installed_modules.items():
            item = self.ix.items.get(module_id)
            if item is None or item.module is None:
                self.err(where, f"{module_id} is not a module item")
                continue
            if item.unique:
                unique_seen[item.id] += 1
            if obj.vehicle_class is not None:
                vc = self.ix.vehicle_classes.get(obj.vehicle_class)
                slot = next((s for s in vc.slots if s.id == slot_id), None) if vc else None
                if slot is None:
                    self.err(where, f"vehicle class has no slot {slot_id}")
                elif item.module.category not in slot.accepts or item.module.mount != slot.mount:
                    self.err(where, f"module {module_id} is incompatible with slot {slot_id}")
            elif obj.infrastructure_type is not None:
                it = self.ix.infrastructure_types.get(obj.infrastructure_type)
                if it is not None and item.module.category not in it.requires_modules:
                    self.err(where, f"module {module_id} is not used by {it.id}")
            else:
                self.err(where, "only vehicles and infrastructure have installed modules")
        # interactions
        actions = Counter(i.action for i in obj.interactions)
        for action, n in actions.items():
            if n > 1:
                self.err(where, f"action {action} defined {n} times")
        for inter in obj.interactions:
            self.interaction(f"{where} {inter.action}", inter, scenarios)

    def interaction(
        self, where: str, inter: Interaction, scenarios: list[ScenarioDefinition]
    ) -> None:
        if inter.action not in ACTION_TYPES:
            self.err(where, "unknown action type")
        elif inter.action not in INTERACTION_ACTIONS:
            self.err(where, "this action has a generic handler and cannot be content-defined")
        for name in list(inter.engine_by_param) + list(inter.effects_by_param):
            if name not in inter.params:
                self.err(where, f"unknown parameter {name}")
        for name, by_value in list(inter.engine_by_param.items()) + list(
            inter.effects_by_param.items()
        ):
            if name in inter.params:
                extra = set(by_value) - set(inter.params[name].enum)
                if extra:
                    self.err(where, f"parameter {name} has no values {sorted(extra)}")
        self.unique(f"{where} requirements", (r.id for r in inter.requirements))
        for r in inter.requirements:
            self.condition(f"{where} requirement {r.id}", r.when, scenarios)
        for iq in inter.consumes:
            if iq.item not in self.ix.items:
                self.err(where, f"unknown consumed item {iq.item}")
        if inter.consumes_from is not None:
            self.container_ref(where, inter.consumes_from)
        for ce in inter.conditional_effects:
            self.condition(f"{where} conditional effect", ce.when, scenarios)
            self.effects(f"{where} conditional effect", ce.effects)
        for params in all_param_assignments(inter):
            for eff in param_effects(inter, params):
                self.effects(where, eff)
            for raw in rendered_decisions(inter, params):
                for s in scenarios:
                    self.decision(f"{where} {params or ''}".rstrip(), raw, s)

    def decision(self, where: str, raw: dict[str, Any], s: ScenarioDefinition) -> None:
        try:
            d = parse_decision(raw)
        except (ValidationError, KeyError) as exc:
            self.err(where, f"invalid engine decision {raw}: {exc}")
            return
        payload = d.model_dump(mode="json")
        kind = payload["type"]
        consumers = {cs.id: cs for cs in s.power.consumers}
        if kind == "set_subsystem_mode":
            cs = consumers.get(payload["subsystem"])
            if cs is None:
                self.err(where, f"scenario {s.id} has no consumer {payload['subsystem']}")
            elif payload["mode"] not in {str(m) for m in cs.mode_factors}:
                self.err(where, f"consumer {cs.id} has no mode {payload['mode']}")
        elif kind == "schedule_maintenance":
            if payload["component"] not in {c.id for c in s.degradation.components}:
                self.err(where, f"scenario {s.id} has no component {payload['component']}")
        elif kind == "start_science_activity":
            if payload["opportunity_id"] not in {o.id for o in s.science.opportunities}:
                self.err(where, f"scenario {s.id} has no opportunity {payload['opportunity_id']}")
        elif kind == "rover_command" and payload["action"] == "traverse":
            ops = {o.id: o for o in s.science.opportunities}
            op = ops.get(payload.get("opportunity_id") or "")
            if op is None or not op.requires_rover:
                self.err(where, f"traverse needs a rover opportunity of scenario {s.id}")
        elif kind == "clean_solar_array":
            if payload["crew_id"] not in {c.id for c in s.crew}:
                self.err(where, f"scenario {s.id} has no crew {payload['crew_id']}")

    def knowledge_and_narrative(self) -> None:
        all_scenarios = list(self.scenarios.values())
        for ins in self.c.knowledge.insights:
            where = f"insight {ins.id}"
            self.provenance(where, ins.provenance)
            self.condition(where, ins.unlock, all_scenarios)
            for o in ins.related_objects:
                if o not in self.ix.objects:
                    self.err(where, f"unknown object {o}")
            if ins.why_metric is not None and not any(
                m.has(ins.why_metric) for m in self.metrics.values()
            ):
                self.err(where, f"unknown WHY? metric {ins.why_metric}")
        for crew in self.c.narrative.crew:
            for sid, member in crew.sim_crew.items():
                s = self.scenarios.get(sid)
                if s is None:
                    self.err(f"crew {crew.id}", f"unknown scenario {sid}")
                elif member not in {c.id for c in s.crew}:
                    self.err(f"crew {crew.id}", f"scenario {sid} has no crew {member}")
        for cue in self.c.narrative.cues:
            where = f"cue {cue.id}"
            if cue.speaker not in self.ix.crew:
                self.err(where, f"unknown speaker {cue.speaker}")
            self.condition(where, cue.when, all_scenarios)

    def readiness(self) -> None:
        for profile in self.c.readiness.profiles:
            where = f"readiness {profile.id}"
            self.unique(f"{where} gates", (g.id for g in profile.gates))
            if not any(g.critical for g in profile.gates):
                self.err(where, "a readiness profile needs at least one critical gate")
            for g in profile.gates:
                if not g.requires and not g.requires_certifications:
                    self.err(f"{where} {g.id}", "a gate must require something")
                for req in g.requires:
                    self.cap_req(f"{where} {g.id}", req)
                for cert in g.requires_certifications:
                    if cert not in self.ix.certifications:
                        self.err(f"{where} {g.id}", f"unknown certification {cert}")


def validate_content(loaded: LoadedContent) -> list[str]:
    return _V(loaded).run()
