"""Electrical power system: solar array, battery, rover transfer, load allocation.

Equations (Δt = tick_hours):
    dust(t+1)      = max(dust_floor, dust(t) - deposition · m_dust)        m_dust: event modifiers
    P_gen          = P_rated · solar_availability · dust · perf(solar_array)
    demand_i       = nominal_i · mode_factor_i   (special cases: heater thermostat, science only
                     while an activity runs, rover charger only while docked, not full and not
                     transferring energy to the habitat during this tick,
                     0 while the consumer's component is under maintenance)
    P_batt_max     = min(max_discharge_kw, E_batt · η_dis / Δt)
    P_rover        = min(transfer_kw, E_rover / Δt) · η_transfer   (only when transfer active)
    available      = P_gen + P_rover + P_batt_max
    allocation     = greedy by (priority, id): a_i = min(demand_i, remaining)
    supply_ratio_i = a_i / demand_i   (1 when demand_i = 0)
    surplus  s = P_gen + P_rover - Σa  → charge:    E += min(s, max_charge_kw, headroom) · η_ch · Δt
    deficit  d = Σa - P_gen - P_rover  → discharge: E -= d / η_dis · Δt
    capacity       = capacity_rated · max(0.05, health(battery))
"""

from __future__ import annotations

from app.simulation.domain.enums import RoverStatus, SubsystemMode
from app.simulation.engine.context import TickContext
from app.simulation.systems.common import clamp, component_performance, performance
from app.simulation.systems.environment import apply_modifiers


def battery_capacity_kwh(ctx: TickContext) -> float:
    sc = ctx.scenario
    health = ctx.state.components[sc.degradation.battery_component].health
    return sc.power.battery.capacity_kwh * max(0.05, health)


def _heater_demand(ctx: TickContext, factor: float) -> float:
    sc, st = ctx.scenario, ctx.state
    th = sc.thermal
    required = (
        th.conductance_kw_per_k * (st.thermal.setpoint_c - st.environment.sink_temp_c)
        - st.thermal.internal_heat_kw
        + th.heater_gain_kw_per_k * max(0.0, st.thermal.setpoint_c - st.thermal.habitat_temp_c)
    )
    return clamp(required, 0.0, th.heater_max_kw) * factor


def _demand(ctx: TickContext, consumer_id: str, *, rover_transferring: bool = False) -> float:
    sc, st = ctx.scenario, ctx.state
    spec = sc.consumer(consumer_id)
    cstate = st.power.consumers[consumer_id]
    if spec.component is not None and st.components[spec.component].maintenance_remaining_ticks:
        return 0.0
    factor = spec.mode_factors.get(cstate.mode, 0.0)
    if cstate.mode == SubsystemMode.OFF or factor <= 0:
        return 0.0
    if consumer_id == sc.power.heater_consumer:
        return _heater_demand(ctx, factor)
    if consumer_id == sc.power.science_consumer:
        return spec.nominal_kw * factor if st.science.active_opportunity else 0.0
    if consumer_id == sc.power.rover_charger_consumer:
        rover = st.rover
        headroom_kw = max(0.0, sc.rover.battery_capacity_kwh - rover.battery_kwh) / ctx.dt_hours
        if rover.status != RoverStatus.DOCKED or rover_transferring or headroom_kw <= 0:
            return 0.0
        return min(spec.nominal_kw * factor, headroom_kw)
    return spec.nominal_kw * factor


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    pw, dt = sc.power, ctx.dt_hours
    power = st.power

    # Dust accumulation (event modifiers can scale the deposition rate).
    deposition = apply_modifiers(st, "power.dust_deposition", pw.dust_deposition_per_tick, ctx.tick)
    power.dust_factor = max(pw.dust_floor, power.dust_factor - max(0.0, deposition))

    # Generation.
    solar_perf = component_performance(sc, st, sc.degradation.solar_component)
    generation = pw.solar_rated_kw * st.environment.solar_availability * power.dust_factor
    generation *= solar_perf
    power.generation_kw = generation

    # Rover → habitat energy transfer.
    rover_kw = 0.0
    # Energy flows one way per tick: a rover that fed the bus this tick is not recharged in it.
    rover_transferring = st.rover.transfer_active and st.rover.status == RoverStatus.DOCKED
    if rover_transferring:
        drawn_kw = min(sc.rover.transfer_kw, st.rover.battery_kwh / dt)
        st.rover.battery_kwh = max(0.0, st.rover.battery_kwh - drawn_kw * dt)
        rover_kw = drawn_kw * sc.rover.transfer_efficiency
        if st.rover.battery_kwh <= 1e-9:
            st.rover.transfer_active = False
            st.rover.battery_kwh = 0.0

    # Battery limits.
    batt = pw.battery
    capacity = battery_capacity_kwh(ctx)
    power.battery_charge_kwh = min(power.battery_charge_kwh, capacity)
    batt_perf = performance(
        sc.component(sc.degradation.battery_component),
        st.components[sc.degradation.battery_component].health,
    )
    max_discharge = min(
        batt.max_discharge_kw * batt_perf, power.battery_charge_kwh * batt.discharge_efficiency / dt
    )

    # Demand and priority allocation.
    remaining = generation + rover_kw + max_discharge
    total_demand = 0.0
    total_alloc = 0.0
    order = sorted(pw.consumers, key=lambda c: (c.priority, c.id))
    for spec in order:
        cstate = power.consumers[spec.id]
        demand = _demand(ctx, spec.id, rover_transferring=rover_transferring)
        alloc = min(demand, max(0.0, remaining))
        remaining -= alloc
        cstate.demand_kw = demand
        cstate.allocated_kw = alloc
        cstate.supply_ratio = alloc / demand if demand > 0 else 1.0
        total_demand += demand
        total_alloc += alloc

    # Battery charge / discharge.
    net_source = generation + rover_kw - total_alloc
    if net_source >= 0:
        headroom_kw = max(0.0, capacity - power.battery_charge_kwh) / (dt * batt.charge_efficiency)
        charge_kw = min(net_source, batt.max_charge_kw * batt_perf, headroom_kw)
        power.battery_charge_kwh += charge_kw * batt.charge_efficiency * dt
        power.battery_net_kw = charge_kw
    else:
        draw_kw = -net_source
        power.battery_charge_kwh -= draw_kw / batt.discharge_efficiency * dt
        power.battery_net_kw = -draw_kw / batt.discharge_efficiency
    power.battery_charge_kwh = clamp(power.battery_charge_kwh, 0.0, capacity)

    power.demand_kw = total_demand
    power.allocated_kw = total_alloc
    power.unmet_kw = max(0.0, total_demand - total_alloc)

    # Rover charging from allocated charger power.
    charger = power.consumers[pw.rover_charger_consumer]
    if charger.allocated_kw > 0:
        st.rover.battery_kwh = min(
            sc.rover.battery_capacity_kwh, st.rover.battery_kwh + charger.allocated_kw * dt
        )
