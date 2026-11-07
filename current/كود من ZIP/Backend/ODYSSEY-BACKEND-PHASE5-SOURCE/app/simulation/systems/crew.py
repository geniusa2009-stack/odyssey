"""Crew state abstraction: radiation dose, EVA, fatigue and an abstract health index.

Per crew member with health > 0 (Δt hours):
    received = dose_rate · shielding(location)                   [mSv/h]
    dose    += received · Δt
    penalty  = radiation:  k_rad · max(0, received − threshold) · Δt
             + hypoxia:    k_hyp · (1 − O2_gen/O2_req)        when O2 reserve is empty
             + CO2:        k_co2 · clamp((ppm − warn)/(crit − warn))
             + cold:       k_cold · max(0, T_cold − T)
             + dehydration k_dehyd                             when water is empty
             + starvation  k_starve                            when food is empty
             + rationing   k_ration · (1 − ration_level)
    health   = clamp(health − penalty + (recovery if penalty == 0))
EVA: crew on EVA receive the EVA shielding factor and gain fatigue; when the EVA completes the
associated task takes effect (array cleaning restores dust transmission).
This is NOT a physiological model; it is an educational abstraction of crew risk.
"""

from __future__ import annotations

from app.simulation.domain.enums import CrewLocation, EventKind, ProvenanceKind
from app.simulation.domain.state import Provenance
from app.simulation.engine.context import TickContext
from app.simulation.systems.common import clamp


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    rad, ch, ls = sc.radiation, sc.crew_health, st.life_support
    shield = {
        CrewLocation.HABITAT: rad.habitat_shielding_factor,
        CrewLocation.SHELTER: rad.shelter_shielding_factor,
        CrewLocation.EVA: rad.eva_shielding_factor,
    }
    ppm = ls.co2_kg * sc.life_support.co2_ppm_per_kg
    hypoxia = (
        ls.oxygen_kg <= 1e-9 and ls.o2_required_kg > 0 and ls.o2_generated_kg < ls.o2_required_kg
    )
    hypoxia_frac = 1.0 - ls.o2_generated_kg / ls.o2_required_kg if hypoxia else 0.0
    dt = ctx.dt_hours

    for member in st.crew:
        if member.health <= 0:
            continue
        received = st.environment.radiation_dose_rate_msv_h * shield[member.location]
        member.dose_msv += received * dt
        penalty = (
            rad.health_penalty_per_msv * max(0.0, received - rad.health_threshold_msv_per_hour) * dt
        )
        penalty += ch.hypoxia_penalty_per_tick * hypoxia_frac
        if ppm > ch.co2_warning_ppm:
            penalty += ch.co2_penalty_per_tick * clamp(
                (ppm - ch.co2_warning_ppm) / (ch.co2_critical_ppm - ch.co2_warning_ppm)
            )
        penalty += ch.cold_penalty_per_k_tick * max(
            0.0, ch.cold_threshold_c - st.thermal.habitat_temp_c
        )
        if ls.water_kg <= 1e-9:
            penalty += ch.dehydration_penalty_per_tick
        if st.food.food_kg <= 1e-9:
            penalty += ch.starvation_penalty_per_tick
        penalty += ch.ration_penalty_per_tick * (1.0 - st.food.ration_level)

        if member.location == CrewLocation.EVA:
            member.fatigue = clamp(member.fatigue + ch.eva_fatigue_per_tick)
            member.eva_remaining_ticks -= 1
            if member.eva_remaining_ticks <= 0:
                _complete_eva(ctx, member.id)
        else:
            member.fatigue = clamp(member.fatigue - ch.fatigue_recovery_per_tick)

        if penalty > 0:
            member.health = clamp(member.health - penalty)
        else:
            member.health = clamp(member.health + ch.recovery_per_tick)
        if member.health <= 0:
            member.health = 0.0
            ctx.emit(
                EventKind.MILESTONE,
                f"crew_incapacitated:{member.id}",
                message_key="crew.incapacitated",
                data={"crew_id": member.id},
            )


def _complete_eva(ctx: TickContext, crew_id: str) -> None:
    st, sc = ctx.state, ctx.scenario
    member = next(c for c in st.crew if c.id == crew_id)
    ref = member.eva_task_ref
    member.location = CrewLocation.HABITAT
    member.eva_remaining_ticks = 0
    member.eva_task_ref = None
    restored = max(st.power.dust_factor, sc.decisions.dust_after_cleaning)
    st.power.dust_factor = restored
    st.power.dust_set_by = Provenance(
        kind=ProvenanceKind.DECISION, ref=ref or "unknown", tick=ctx.tick
    )
    ctx.emit(
        EventKind.MAINTENANCE,
        "solar_array_cleaned",
        message_key="power.array_cleaned",
        data={"crew_id": crew_id, "dust_factor": restored, "decision_id": ref},
    )
