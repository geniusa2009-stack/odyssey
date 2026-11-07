"""System dependency graph.

A static, typed graph of *how* quantities influence each other. Nodes are metric names; edges
carry the physical mechanism. The graph is used for:

* cascade warnings (a degraded upstream node coinciding with a degraded downstream node),
* root-cause tracing (walking edges backwards through recorded state transitions),
* explanations (ORION may only cite edges that exist here).

Wildcard edges (``*``) expand once per consumer/component of the scenario.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.simulation.engine.metrics import MetricRegistry
from app.simulation.scenarios.schema import ScenarioDefinition


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source: str
    target: str
    mechanism: str

    @property
    def key(self) -> str:
        return f"{self.source}->{self.target}"


ROOT_PREFIXES = ("env.", "control.")


class DependencyGraph:
    def __init__(self, scenario: ScenarioDefinition, metrics: MetricRegistry) -> None:
        self.scenario = scenario
        self.metrics = metrics
        self.edges: tuple[DependencyEdge, ...] = tuple(self._build())
        self._parents: dict[str, list[DependencyEdge]] = {}
        self._children: dict[str, list[DependencyEdge]] = {}
        for e in self.edges:
            self._parents.setdefault(e.target, []).append(e)
            self._children.setdefault(e.source, []).append(e)
        unknown = {n for e in self.edges for n in (e.source, e.target) if not metrics.has(n)}
        if unknown:
            raise ValueError(f"dependency graph references unknown metrics: {sorted(unknown)}")

    def _build(self) -> list[DependencyEdge]:
        sc = self.scenario
        ls, pw, dg = sc.life_support, sc.power, sc.degradation
        e: list[DependencyEdge] = []

        def add(src: str, dst: str, mech: str) -> None:
            e.append(DependencyEdge(src, dst, mech))

        # Generation
        add(
            "env.solar_availability",
            "power.generation_ratio",
            "Photovoltaic output scales with available sunlight",
        )
        add(
            "power.dust_factor",
            "power.generation_ratio",
            "Regolith dust on the array blocks incoming light",
        )
        add(
            f"component.{dg.solar_component}.health",
            "power.generation_ratio",
            "A degraded array converts less light to electricity",
        )
        # Demand
        add("env.sink_temp_c", "power.demand_ratio", "A colder environment increases heater demand")
        add(
            "control.boost_load_kw",
            "power.demand_ratio",
            "Boost modes draw more than nominal power",
        )
        add(
            "control.discretionary_load_kw",
            "power.demand_ratio",
            "Science operations and rover charging add electrical load",
        )
        # Battery
        add(
            "power.generation_ratio",
            "power.battery_soc",
            "When generation falls below demand the battery discharges",
        )
        add("power.demand_ratio", "power.battery_soc", "Higher demand drains the battery faster")
        add(
            "control.discretionary_load_kw",
            "power.battery_soc",
            "Science operations and rover charging draw down the battery",
        )
        add(
            f"component.{dg.battery_component}.health",
            "power.battery_soc",
            "A degraded battery holds less energy",
        )
        # Load shedding: every consumer depends on the bus
        for c in pw.consumers:
            add(
                "power.battery_soc",
                f"power.supply_ratio.{c.id}",
                "A depleted battery forces lower-priority loads to be shed",
            )
            add(
                "power.generation_ratio",
                f"power.supply_ratio.{c.id}",
                "Less generation leaves less power to allocate",
            )
        # Forced load shedding: an empty battery with too little generation leaves demand unmet
        add(
            "power.battery_soc",
            "power.unmet_kw",
            "With the battery empty, loads the array cannot cover are shed",
        )
        add(
            "power.generation_ratio",
            "power.unmet_kw",
            "Too little generation leaves demand unmet once the battery is empty",
        )
        # Thermal
        add(
            f"power.supply_ratio.{pw.heater_consumer}",
            "thermal.habitat_temp_c",
            "Unpowered heaters cannot replace heat lost to the environment",
        )
        add(
            f"control.mode.{pw.heater_consumer}",
            "thermal.habitat_temp_c",
            "Heater mode limits the heating power applied",
        )
        add(
            "control.thermal_setpoint",
            "thermal.habitat_temp_c",
            "The thermostat setpoint determines the regulated temperature",
        )
        add(
            "env.sink_temp_c", "thermal.habitat_temp_c", "Heat leaks faster to a colder environment"
        )
        add(
            f"component.{dg.heater_component}.health",
            "thermal.habitat_temp_c",
            "A degraded heater delivers less heat",
        )
        # Oxygen
        og = ls.oxygen_generator_consumer
        og_comp = sc.consumer(og).component
        add(
            f"power.supply_ratio.{og}",
            "life_support.o2_generation_ratio",
            "Electrolysis needs electrical power",
        )
        add(
            f"control.mode.{og}",
            "life_support.o2_generation_ratio",
            "Generator mode sets its production rate",
        )
        if og_comp:
            add(
                f"component.{og_comp}.health",
                "life_support.o2_generation_ratio",
                "A degraded generator produces less oxygen",
            )
        add(
            "life_support.water_days",
            "life_support.o2_generation_ratio",
            "Electrolysis consumes water; no water means no oxygen",
        )
        add(
            "life_support.o2_generation_ratio",
            "life_support.oxygen_days",
            "Generation below crew use draws down oxygen reserves",
        )
        # CO2
        sc_id = ls.co2_scrubber_consumer
        sc_comp = sc.consumer(sc_id).component
        add(
            f"power.supply_ratio.{sc_id}",
            "life_support.co2_ppm",
            "Unpowered scrubbers let exhaled CO2 accumulate",
        )
        add(f"control.mode.{sc_id}", "life_support.co2_ppm", "Scrubber mode sets its removal rate")
        if sc_comp:
            add(
                f"component.{sc_comp}.health",
                "life_support.co2_ppm",
                "A degraded scrubber removes less CO2",
            )
        # Water
        wr = ls.water_recovery_consumer
        wr_comp = sc.consumer(wr).component
        add(
            f"power.supply_ratio.{wr}",
            "life_support.water_recovery_efficiency",
            "Water processing needs electrical power",
        )
        add(
            f"control.mode.{wr}",
            "life_support.water_recovery_efficiency",
            "Recovery mode sets processing throughput",
        )
        add(
            "thermal.habitat_temp_c",
            "life_support.water_recovery_efficiency",
            "Cold degrades water processing (freezing risk below the minimum temperature)",
        )
        if wr_comp:
            add(
                f"component.{wr_comp}.health",
                "life_support.water_recovery_efficiency",
                "A degraded processor recovers less water",
            )
        add(
            "life_support.water_recovery_efficiency",
            "life_support.water_days",
            "Water not recovered is lost from the reserve",
        )
        # Communications
        cm = pw.comms_consumer
        add("env.earth_visible", "comms.link_up", "No line of sight means no link")
        add(f"power.supply_ratio.{cm}", "comms.link_up", "The radio needs power")
        add(
            f"component.{dg.comms_component}.health",
            "comms.link_up",
            "A degraded radio cannot hold the link",
        )
        # Crew
        add("life_support.oxygen_days", "crew.min_health", "Oxygen exhaustion causes hypoxia")
        add("life_support.co2_ppm", "crew.min_health", "High CO2 impairs and harms the crew")
        add("thermal.habitat_temp_c", "crew.min_health", "Cold exposure harms the crew")
        add("life_support.water_days", "crew.min_health", "Water exhaustion causes dehydration")
        add("food.food_days", "crew.min_health", "Food exhaustion causes starvation")
        add("control.ration_level", "crew.min_health", "Reduced rations erode crew health")
        # No edge crew.max_dose_msv → crew.min_health: in this model accumulated dose has no
        # health effect; only the received dose *rate* above the acute threshold harms the crew.
        add(
            "env.radiation_dose_rate_msv_h",
            "crew.received_dose_rate_msv_h",
            "Surface dose rate, reduced by the shielding where the crew is",
        )
        add(
            "crew.received_dose_rate_msv_h",
            "crew.min_health",
            "A received dose rate above the acute threshold harms the crew",
        )
        add(
            "env.radiation_dose_rate_msv_h",
            "crew.max_dose_msv",
            "Higher surface dose rate increases crew dose",
        )
        add(
            "crew.received_dose_rate_msv_h",
            "crew.max_dose_msv",
            "Accumulated dose is the dose rate received where the crew is, over time",
        )
        # Dose budget (only for scenarios that declare a mission dose limit)
        if sc.radiation.dose_limit_msv is not None:
            add(
                "crew.max_dose_msv",
                "crew.dose_margin_msv",
                "Every millisievert received is taken from the mission dose budget",
            )
            add(
                "crew.max_dose_msv",
                "crew.projected_dose_msv",
                "The projection starts from the dose already received",
            )
            add(
                "crew.projected_dose_msv",
                "crew.projected_dose_margin_msv",
                "A higher projected dose leaves less margin to the limit",
            )
        # Science delivery (metrics without severity: used by traces, never by cascade warnings)
        add(
            "comms.link_up",
            "comms.data_downlinked_mb",
            "Science data can only be sent to Earth while the link is up",
        )
        add(
            f"power.supply_ratio.{pw.science_consumer}",
            "science.points",
            "Habitat science instruments need electrical power",
        )
        add(
            "crew.in_shelter",
            "science.points",
            "Crew sheltering from radiation cannot work in the habitat laboratory",
        )
        # Mission risk
        for term in sc.analysis.risk_terms:
            add(term.metric, "risk.mission", "Contributes to the composite mission risk indicator")
        # Dedupe while preserving order
        seen: set[str] = set()
        unique: list[DependencyEdge] = []
        for edge in e:
            if edge.key not in seen:
                seen.add(edge.key)
                unique.append(edge)
        return unique

    def parents(self, node: str) -> list[DependencyEdge]:
        return list(self._parents.get(node, []))

    def children(self, node: str) -> list[DependencyEdge]:
        return list(self._children.get(node, []))

    def nodes(self) -> list[str]:
        return sorted({n for e in self.edges for n in (e.source, e.target)})

    @staticmethod
    def is_root_namespace(node: str) -> bool:
        return node.startswith(ROOT_PREFIXES)

    def system_edges(self) -> list[DependencyEdge]:
        """Edges between engineered systems (used for cascade warnings)."""
        return [
            e
            for e in self.edges
            if not self.is_root_namespace(e.source) and e.target != "risk.mission"
        ]
