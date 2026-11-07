"""Deterministic mission simulation engine.

Contract
--------
* Pure with respect to its inputs: public methods never mutate the ``MissionState`` passed in;
  they return new state objects.
* Deterministic: ``(scenario, seed, decisions, ticks)`` → identical states (and state hashes).
  The only randomness is the counter-based RNG in :mod:`app.simulation.engine.rng`.
* Standalone: depends only on the standard library, Pydantic and the simulation package.

Tick order (tick ``t`` → ``t+1``; events emitted during the step carry ``tick = t``):
  1. scenario events (scheduled / state / random)      6. communications
  2. environment (profile + modifiers)                 7. science
  3. power (dust, generation, demand, allocation)      8. rover
  4. thermal                                           9. crew (radiation, EVA, health)
  5. life support + food                              10. degradation, faults, maintenance
  then tick += 1 and: alerts → cascade warnings → objectives → outcome → phase advance.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.simulation.domain.decisions import (
    CleanSolarArray,
    DecisionInput,
    RoverCommand,
    ScheduleMaintenance,
    SetCrewLocation,
    SetRationLevel,
    SetSubsystemMode,
    SetThermalSetpoint,
    StartScienceActivity,
    StopScienceActivity,
    decision_payload,
)
from app.simulation.domain.enums import (
    CrewLocation,
    EventKind,
    MissionStatus,
    ObjectiveStatus,
    OpportunityStatus,
    ProvenanceKind,
    RoverStatus,
)
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import (
    CommsState,
    ComponentState,
    ConsumerState,
    CrewMemberState,
    EnvironmentState,
    FoodState,
    LifeSupportState,
    MissionState,
    ObjectiveState,
    PhaseTransition,
    PowerState,
    Provenance,
    RoverState,
    ScienceState,
    ThermalState,
)
from app.simulation.engine import mission_logic
from app.simulation.engine.context import RunOptions, TickContext
from app.simulation.engine.dependency_graph import DependencyGraph
from app.simulation.engine.metrics import MetricRegistry
from app.simulation.events.processor import fire_decision_events, process_tick_events
from app.simulation.scenarios.schema import ScenarioDefinition
from app.simulation.systems import (
    comms_science,
    crew,
    degradation,
    environment,
    life_support,
    power,
    rover,
    thermal,
)


def _is_concluded(state: MissionState) -> bool:
    return state.status == MissionStatus.CONCLUDED


class DecisionRejectedError(ValueError):
    """A decision is well-formed but not valid in the current state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MissionConcludedError(RuntimeError):
    """Raised when stepping a mission that has already concluded."""


@dataclass(frozen=True, slots=True)
class TickResult:
    state: MissionState
    events: tuple[MissionEvent, ...]


@dataclass(frozen=True, slots=True)
class DecisionResult:
    state: MissionState
    events: tuple[MissionEvent, ...]
    affected_systems: tuple[str, ...]


@dataclass(slots=True)
class AdvanceResult:
    state: MissionState
    events: list[MissionEvent] = field(default_factory=list)
    ticks_run: int = 0
    history: list[MissionState] | None = None


class SimulationEngine:
    def __init__(self, scenario: ScenarioDefinition) -> None:
        self.scenario = scenario
        self.metrics = MetricRegistry(scenario)
        self.graph = DependencyGraph(scenario, self.metrics)
        self._validate_metric_references()

    # ------------------------------------------------------------------------------ setup
    def _validate_metric_references(self) -> None:
        sc = self.scenario
        referenced: set[str] = set()
        for cond in sc.all_conditions():
            referenced |= cond.metrics()
        referenced |= {a.metric for a in sc.alerts}
        referenced |= {t.metric for t in sc.analysis.risk_terms}
        unknown = sorted(m for m in referenced if not self.metrics.has(m))
        if unknown:
            raise ValueError(f"scenario {sc.id} references unknown metrics: {unknown}")

    def initial_state(self, seed: int) -> MissionState:
        sc = self.scenario
        scenario_prov = Provenance(
            kind=ProvenanceKind.SCENARIO, ref=f"{sc.id}@{sc.version}", tick=0
        )
        consumers = {
            c.id: ConsumerState(id=c.id, mode=c.initial_mode, mode_set_by=scenario_prov)
            for c in sc.power.consumers
        }
        first_phase = sc.phases[0].id
        state = MissionState(
            scenario_id=sc.id,
            scenario_version=sc.version,
            seed=seed,
            phase=first_phase,
            phase_history=[PhaseTransition(phase=first_phase, tick=0)],
            environment=EnvironmentState(
                solar_availability=0.0,
                sink_temp_c=0.0,
                radiation_dose_rate_msv_h=0.0,
                earth_visible=True,
            ),
            power=PowerState(
                battery_charge_kwh=sc.power.battery.capacity_kwh * sc.power.battery.initial_soc,
                dust_set_by=scenario_prov,
                consumers=consumers,
            ),
            thermal=ThermalState(
                habitat_temp_c=sc.thermal.initial_temp_c,
                setpoint_c=sc.thermal.initial_setpoint_c,
                setpoint_set_by=scenario_prov,
            ),
            life_support=LifeSupportState(
                oxygen_kg=sc.life_support.initial_oxygen_kg,
                co2_kg=sc.life_support.initial_co2_kg,
                water_kg=sc.life_support.initial_water_kg,
                water_recovery_efficiency=sc.life_support.water_recovery_nominal,
            ),
            food=FoodState(food_kg=sc.food.initial_food_kg, ration_set_by=scenario_prov),
            comms=CommsState(),
            science=ScienceState(),
            crew=[CrewMemberState(id=c.id, role=c.role) for c in sc.crew],
            rover=RoverState(
                status=RoverStatus.DOCKED,
                battery_kwh=sc.rover.initial_battery_kwh,
                status_set_by=scenario_prov,
            ),
            components={c.id: ComponentState(id=c.id) for c in sc.degradation.components},
            objectives={o.id: ObjectiveState(id=o.id) for o in sc.objectives},
        )
        environment.compute_environment(sc, state, 0)
        state.comms.link_up = state.environment.earth_visible
        return state

    # ------------------------------------------------------------------------------ stepping
    def step(self, state: MissionState, options: RunOptions | None = None) -> TickResult:
        """Advance one tick. Never mutates ``state``."""
        working = state.clone()
        events = self._step_in_place(working, options or RunOptions())
        return TickResult(state=working, events=tuple(events))

    def advance(
        self,
        state: MissionState,
        ticks: int,
        options: RunOptions | None = None,
        *,
        record_history: bool = False,
        on_tick: Callable[[MissionState, list[MissionEvent]], None] | None = None,
        stop_when: Callable[[MissionState], bool] | None = None,
    ) -> AdvanceResult:
        """Advance up to ``ticks`` ticks, stopping early if the mission concludes.

        The input state is not mutated. ``history`` (if requested) holds a copy of the state
        after every tick. ``stop_when`` (optional) is checked after every tick; advancement stops
        after the first tick where it returns true. It only observes state, so advancing in
        several stopped chunks yields exactly the same states as one uninterrupted advance.
        """
        if ticks < 0:
            raise ValueError("ticks must be >= 0")
        opts = options or RunOptions()
        working = state.clone()
        result = AdvanceResult(state=working, history=[] if record_history else None)
        for _ in range(ticks):
            if working.status == MissionStatus.CONCLUDED:
                break
            events = self._step_in_place(working, opts)
            result.events.extend(events)
            result.ticks_run += 1
            if result.history is not None:
                result.history.append(working.clone())
            if on_tick is not None:
                on_tick(working, events)
            if stop_when is not None and stop_when(working):
                break
        return result

    def _step_in_place(self, st: MissionState, options: RunOptions) -> list[MissionEvent]:
        if st.status == MissionStatus.CONCLUDED:
            raise MissionConcludedError("mission has concluded; it cannot be advanced")
        ctx = TickContext(
            scenario=self.scenario, metrics=self.metrics, state=st, options=options, tick=st.tick
        )
        process_tick_events(ctx)
        environment.update(ctx)
        power.update(ctx)
        thermal.update(ctx)
        life_support.update(ctx)
        comms_science.update_comms(ctx)
        comms_science.update_science(ctx)
        rover.update(ctx)
        crew.update(ctx)
        degradation.update(ctx)
        st.tick += 1
        mission_logic.evaluate_alerts(ctx)
        mission_logic.evaluate_cascades(ctx, self.graph)
        mission_logic.evaluate_objectives(ctx, final=False)
        mission_logic.evaluate_outcome(ctx)
        if not _is_concluded(st):  # evaluate_outcome may have concluded the mission
            mission_logic.advance_phase(ctx)
        return ctx.events

    # ------------------------------------------------------------------------------ decisions
    def apply_decision(
        self, state: MissionState, decision: DecisionInput, decision_id: str
    ) -> DecisionResult:
        """Validate and immediately apply a decision. Never mutates ``state``."""
        if state.status == MissionStatus.CONCLUDED:
            raise DecisionRejectedError("mission_concluded", "the mission has concluded")
        st = state.clone()
        ctx = TickContext(
            scenario=self.scenario,
            metrics=self.metrics,
            state=st,
            options=RunOptions(),
            tick=st.tick,
            id_prefix=f"{decision_id}/",
        )
        prov = Provenance(kind=ProvenanceKind.DECISION, ref=decision_id, tick=st.tick)
        affected = self._apply(ctx, decision, prov)
        st.decisions_applied += 1
        payload = decision_payload(decision)
        ctx.emit(
            EventKind.DECISION_APPLIED,
            decision.type,
            message_key=f"decision.{decision.type}",
            data={
                "decision_id": decision_id,
                "inputs": payload,
                "affected_systems": list(affected),
            },
        )
        fire_decision_events(ctx, decision.type, payload, decision_id)
        return DecisionResult(state=st, events=tuple(ctx.events), affected_systems=affected)

    def validate_decision(self, state: MissionState, decision: DecisionInput) -> None:
        """Raise DecisionRejectedError if the decision is not valid now (no side effects)."""
        self.apply_decision(state, decision, "validation")

    def _apply(self, ctx: TickContext, d: DecisionInput, prov: Provenance) -> tuple[str, ...]:
        sc, st = self.scenario, ctx.state
        if isinstance(d, SetSubsystemMode):
            try:
                spec = sc.consumer(d.subsystem)
            except KeyError:
                raise DecisionRejectedError(
                    "unknown_subsystem", f"unknown subsystem '{d.subsystem}'"
                ) from None
            if d.mode not in spec.mode_factors:
                raise DecisionRejectedError(
                    "mode_not_supported", f"{d.subsystem} does not support mode '{d.mode}'"
                )
            cs = st.power.consumers[d.subsystem]
            cs.mode = d.mode
            cs.mode_set_by = prov
            return tuple(dict.fromkeys(("power", spec.system)))
        if isinstance(d, SetThermalSetpoint):
            th = sc.thermal
            if not th.setpoint_min_c <= d.target_c <= th.setpoint_max_c:
                raise DecisionRejectedError(
                    "setpoint_out_of_range",
                    f"setpoint must be within [{th.setpoint_min_c}, {th.setpoint_max_c}] °C",
                )
            st.thermal.setpoint_c = d.target_c
            st.thermal.setpoint_set_by = prov
            return ("thermal", "power")
        if isinstance(d, SetRationLevel):
            if d.level < sc.food.ration_min:
                raise DecisionRejectedError(
                    "ration_out_of_range", f"ration level must be >= {sc.food.ration_min}"
                )
            st.food.ration_level = d.level
            st.food.ration_set_by = prov
            return ("food", "crew")
        if isinstance(d, ScheduleMaintenance):
            comp = st.components.get(d.component)
            if comp is None:
                raise DecisionRejectedError(
                    "unknown_component", f"unknown component '{d.component}'"
                )
            if comp.maintenance_remaining_ticks > 0:
                raise DecisionRejectedError(
                    "maintenance_in_progress", f"{d.component} is already under maintenance"
                )
            comp.maintenance_remaining_ticks = sc.component(d.component).maintenance_ticks
            return ("maintenance", d.component)
        if isinstance(d, SetCrewLocation):
            moved = 0
            for member in st.crew:
                if member.health > 0 and member.location != CrewLocation.EVA:
                    member.location = CrewLocation(d.location)
                    moved += 1
            if moved == 0:
                raise DecisionRejectedError("no_crew_available", "no crew available to move")
            return ("crew", "radiation")
        if isinstance(d, StartScienceActivity):
            opp = st.science.opportunities.get(d.opportunity_id)
            if opp is None or opp.status != OpportunityStatus.OPEN:
                raise DecisionRejectedError(
                    "opportunity_unavailable", f"opportunity '{d.opportunity_id}' is not open"
                )
            if sc.opportunity(d.opportunity_id).requires_rover:
                raise DecisionRejectedError(
                    "requires_rover", "this opportunity requires a rover traverse"
                )
            if st.science.active_opportunity is not None:
                raise DecisionRejectedError("science_busy", "another activity is running")
            opp.status = OpportunityStatus.ACTIVE
            opp.started_by = prov
            st.science.active_opportunity = d.opportunity_id
            return ("science", "power")
        if isinstance(d, StopScienceActivity):
            active = st.science.active_opportunity
            if active is None:
                raise DecisionRejectedError("no_active_science", "no science activity is running")
            st.science.opportunities[active].status = OpportunityStatus.OPEN
            st.science.active_opportunity = None
            return ("science", "power")
        if isinstance(d, RoverCommand):
            return self._apply_rover(ctx, d, prov)
        if isinstance(d, CleanSolarArray):
            eva_member = next((c for c in st.crew if c.id == d.crew_id), None)
            if eva_member is None or eva_member.health <= 0:
                raise DecisionRejectedError(
                    "crew_unavailable", f"crew member '{d.crew_id}' is unavailable"
                )
            if any(c.location == CrewLocation.EVA for c in st.crew):
                raise DecisionRejectedError("eva_in_progress", "an EVA is already in progress")
            eva_member.location = CrewLocation.EVA
            eva_member.eva_remaining_ticks = sc.decisions.eva_ticks
            eva_member.eva_task_ref = prov.ref
            return ("power", "crew", "radiation")
        raise DecisionRejectedError("unsupported_decision", "unsupported decision type")

    def _apply_rover(self, ctx: TickContext, d: RoverCommand, prov: Provenance) -> tuple[str, ...]:
        sc, st = self.scenario, ctx.state
        rv = st.rover

        def reject(code: str, msg: str) -> DecisionRejectedError:
            return DecisionRejectedError(code, msg)

        if rv.status == RoverStatus.LOST:
            raise reject("rover_lost", "the rover has been lost")
        if d.action == "traverse":
            if rv.status != RoverStatus.DOCKED:
                raise reject("rover_not_docked", "the rover must be docked to start a traverse")
            opp = st.science.opportunities.get(d.opportunity_id or "")
            if (
                opp is None
                or opp.status != OpportunityStatus.OPEN
                or not sc.opportunity(opp.id).requires_rover
            ):
                raise reject("opportunity_unavailable", "no open rover opportunity with that id")
            if sc.rover.teleop_requires_link and not st.comms.link_up:
                raise reject("no_link", "tele-operation requires a communication link")
            rv.status = RoverStatus.TRAVERSING
            rv.progress_ticks = 0
            rv.target_opportunity = opp.id
            opp.started_by = prov
            rv.transfer_active = False
        elif d.action == "recall":
            if rv.status != RoverStatus.TRAVERSING:
                raise reject("rover_not_traversing", "the rover is not on a traverse")
            rv.status = RoverStatus.RETURNING
            if rv.target_opportunity:
                opp = st.science.opportunities.get(rv.target_opportunity)
                if opp is not None and opp.status == OpportunityStatus.ACTIVE:
                    opp.status = OpportunityStatus.OPEN
        elif d.action == "transfer_energy":
            if rv.status != RoverStatus.DOCKED:
                raise reject("rover_not_docked", "the rover must be docked to transfer energy")
            if rv.battery_kwh <= 0:
                raise reject("rover_battery_empty", "the rover battery is empty")
            rv.transfer_active = True
        elif d.action == "stow":
            if rv.status != RoverStatus.DOCKED:
                raise reject("rover_not_docked", "the rover must be docked to stow")
            rv.status = RoverStatus.STOWED
            rv.transfer_active = False
        elif d.action == "unstow":
            if rv.status != RoverStatus.STOWED:
                raise reject("rover_not_stowed", "the rover is not stowed")
            rv.status = RoverStatus.DOCKED
        rv.status_set_by = prov
        return ("rover", "power", "science")

    # ------------------------------------------------------------------------------ helpers
    def required_objectives_met(self, state: MissionState) -> bool:
        return all(
            state.objectives[o.id].status == ObjectiveStatus.ACHIEVED
            for o in self.scenario.objectives
            if o.required
        )

    def metric_frame(self, state: MissionState) -> Mapping[str, float]:
        return self.metrics.frame(state)
