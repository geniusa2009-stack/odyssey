"""Life support: oxygen, CO2 removal, water recovery, food.

Per-tick crew loads (n = crew with health > 0, Δt in hours):
    O2_req   = n · o2_per_crew_day   · Δt/24
    CO2_prod = n · co2_per_crew_day  · Δt/24
    W_use    = n · water_per_crew_day · Δt/24
    Food     = n · food_per_crew_day · Δt/24 · ration_level

Water recovery:
    f_T      = clamp((T − T_zero) / (T_min − T_zero))          cold degrades the processor
    η        = η_nominal · min(mode,1) · supply · perf(component) · f_T
    W        = W − W_use + η · W_use

Oxygen generation (electrolysis):
    O2_cap   = capacity_kg_h · Δt · mode · supply · perf
    O2_gen   = min(O2_cap, W / w_per_O2, O2_storage_cap − O2 + O2_req)      (≥ 0)
    W       −= O2_gen · w_per_O2
    O2       = O2 + O2_gen − O2_req                              (shortfall → hypoxia, O2 = 0)

CO2 removal:
    removed  = min(removal_cap_kg_h · Δt · mode · supply · perf, max(0, CO2 − floor))
    CO2      = CO2 + CO2_prod − removed
"""

from __future__ import annotations

from app.simulation.engine.context import TickContext
from app.simulation.systems.common import alive_crew, clamp, consumer_output


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    ls_cfg = sc.life_support
    ls = st.life_support
    n = alive_crew(st)
    days = ctx.dt_hours / 24.0

    o2_req = n * ls_cfg.o2_consumption_kg_per_crew_day * days
    co2_prod = n * ls_cfg.co2_production_kg_per_crew_day * days
    water_use = n * ls_cfg.water_use_kg_per_crew_day * days

    # Water use and recovery.
    temp = st.thermal.habitat_temp_c
    f_temp = clamp(
        (temp - ls_cfg.water_recovery_zero_temp_c)
        / (ls_cfg.water_recovery_min_temp_c - ls_cfg.water_recovery_zero_temp_c)
    )
    wrs = consumer_output(sc, st, ls_cfg.water_recovery_consumer, cap_mode_at_nominal=True)
    efficiency = ls_cfg.water_recovery_nominal * wrs * f_temp
    used = min(water_use, ls.water_kg)
    recovered = used * efficiency
    ls.water_kg = ls.water_kg - used + recovered
    ls.water_recovery_efficiency = efficiency
    ls.water_recovered_kg = recovered

    # Oxygen generation.
    o2_out = consumer_output(sc, st, ls_cfg.oxygen_generator_consumer)
    o2_cap = ls_cfg.o2_generation_capacity_kg_per_hour * ctx.dt_hours * o2_out
    o2_gen = max(
        0.0,
        min(
            o2_cap,
            ls.water_kg / ls_cfg.water_per_kg_o2,
            ls_cfg.oxygen_capacity_kg - ls.oxygen_kg + o2_req,
        ),
    )
    ls.water_kg = max(0.0, ls.water_kg - o2_gen * ls_cfg.water_per_kg_o2)
    ls.oxygen_kg = max(0.0, ls.oxygen_kg + o2_gen - o2_req)
    ls.o2_generated_kg = o2_gen
    ls.o2_required_kg = o2_req

    # CO2 removal.
    scrub = consumer_output(sc, st, ls_cfg.co2_scrubber_consumer)
    capacity = ls_cfg.co2_removal_capacity_kg_per_hour * ctx.dt_hours * scrub
    co2 = ls.co2_kg + co2_prod
    removed = min(capacity, max(0.0, co2 - ls_cfg.co2_floor_kg))
    ls.co2_kg = co2 - removed
    ls.co2_removed_kg = removed

    # Food.
    food_need = n * sc.food.consumption_kg_per_crew_day * days * st.food.ration_level
    st.food.food_kg = max(0.0, st.food.food_kg - food_need)
