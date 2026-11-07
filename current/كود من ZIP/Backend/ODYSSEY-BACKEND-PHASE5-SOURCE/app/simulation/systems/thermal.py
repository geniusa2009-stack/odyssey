"""Habitat thermal model: single lumped thermal mass.

Equations (Δt = tick_hours, C = capacitance, UA = conductance):
    Q_internal = f_internal · (Σ allocated_kw − allocated_heater)      [kW]
    Q_heater   = allocated_heater · perf(heater)                       [kW]
    Q_loss     = UA · (T − T_sink)                                      [kW]
    T'         = T + (Q_heater + Q_internal − Q_loss) · Δt / C
    if T' > setpoint:  T' = max(setpoint, min(T', T) − relax · Δt)     (active thermal control
                                                                        rejects excess heat)
Heater demand (computed in the power system from the previous tick's internal heat):
    demand = clamp(UA·(setpoint − T_sink) − Q_internal_prev + k·max(0, setpoint − T), 0, max)
             · mode_factor
"""

from __future__ import annotations

from app.simulation.engine.context import TickContext
from app.simulation.systems.common import component_performance


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    th = sc.thermal
    heater = st.power.consumers[sc.power.heater_consumer]
    q_internal = th.internal_heat_fraction * max(0.0, st.power.allocated_kw - heater.allocated_kw)
    q_heater = heater.allocated_kw * component_performance(sc, st, sc.degradation.heater_component)
    temp = st.thermal.habitat_temp_c
    q_loss = th.conductance_kw_per_k * (temp - st.environment.sink_temp_c)
    new_temp = temp + (q_heater + q_internal - q_loss) * ctx.dt_hours / th.capacitance_kwh_per_k
    setpoint = st.thermal.setpoint_c
    if new_temp > setpoint:
        new_temp = max(
            setpoint, min(new_temp, temp) - th.overheat_relaxation_k_per_hour * ctx.dt_hours
        )
    st.thermal.habitat_temp_c = new_temp
    st.thermal.heat_loss_kw = q_loss
    st.thermal.internal_heat_kw = q_internal
