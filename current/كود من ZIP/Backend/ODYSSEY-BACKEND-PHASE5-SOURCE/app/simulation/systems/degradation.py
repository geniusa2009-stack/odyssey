"""Component wear, random faults and maintenance.

Per component per tick (skipped while under maintenance):
    wear     = wear_per_tick · m_boost · m_deep
               m_boost = boost_wear_multiplier if any consumer using it runs in BOOST
               m_deep  = deep_discharge_wear_multiplier for the battery below deep_discharge_soc
    health  −= wear
    fault   ~ Bernoulli(fault_probability · (1 − health))   (seeded stream "fault:<component>")
              on fault: health −= fault_damage
Maintenance (decision): component offline for maintenance_ticks, then
    health = min(1, health + maintenance_restore)
Battery capacity follows battery health, so after wear/faults the stored energy is clamped to
the new capacity (energy above it is lost) — the state never holds more than the battery can.
"""

from __future__ import annotations

from app.simulation.domain.enums import AlertSeverity, EventKind, ProvenanceKind, SubsystemMode
from app.simulation.domain.state import Provenance
from app.simulation.engine.context import TickContext
from app.simulation.systems.common import clamp
from app.simulation.systems.power import battery_capacity_kwh


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    boosted = {
        spec.component
        for spec in sc.power.consumers
        if spec.component is not None and st.power.consumers[spec.id].mode == SubsystemMode.BOOST
    }
    soc = st.power.battery_charge_kwh / max(1e-9, battery_capacity_kwh(ctx))

    for spec in sc.degradation.components:
        comp = st.components[spec.id]
        if comp.maintenance_remaining_ticks > 0:
            comp.maintenance_remaining_ticks -= 1
            if comp.maintenance_remaining_ticks == 0:
                before = comp.health
                comp.health = clamp(comp.health + spec.maintenance_restore)
                ctx.emit(
                    EventKind.MAINTENANCE,
                    f"maintenance_complete:{spec.id}",
                    message_key="maintenance.complete",
                    data={
                        "component": spec.id,
                        "health_before": before,
                        "health_after": comp.health,
                    },
                )
            continue

        wear = spec.wear_per_tick
        if spec.id in boosted:
            wear *= spec.boost_wear_multiplier
        if (
            spec.id == sc.degradation.battery_component
            and soc < sc.power.battery.deep_discharge_soc
        ):
            wear *= sc.degradation.deep_discharge_wear_multiplier
        comp.health = clamp(comp.health - wear)

        if ctx.chance(f"fault:{spec.id}", spec.fault_probability_per_tick * (1.0 - comp.health)):
            before = comp.health
            comp.health = clamp(comp.health - spec.fault_damage)
            comp.fault_count += 1
            comp.last_damage = Provenance(
                kind=ProvenanceKind.ENGINE, ref=f"fault:{spec.id}:{ctx.tick}", tick=ctx.tick
            )
            ctx.emit(
                EventKind.SYSTEM_FAULT,
                f"fault:{spec.id}",
                severity=AlertSeverity.WARNING,
                message_key="system.fault",
                data={
                    "component": spec.id,
                    "health_before": before,
                    "health_after": comp.health,
                    "random": True,
                },
            )

    # Capacity fade (wear or fault) cannot leave more energy stored than the battery now holds.
    st.power.battery_charge_kwh = min(st.power.battery_charge_kwh, battery_capacity_kwh(ctx))
