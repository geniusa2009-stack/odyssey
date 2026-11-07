"""Rover operations (tele-operated, uncrewed).

States: DOCKED ⇄ STOWED, DOCKED → TRAVERSING → (site work) → RETURNING → DOCKED, any → LOST.
    TRAVERSING/RETURNING:  E_rover −= traverse_kw · Δt   (¼ of that while halted for lack of link)
    loss chance per tick:  p_loss · (1 − health)   (seeded stream "rover_loss")
    battery exhausted away from base → LOST (stranded)
    at site: works the target opportunity at rate perf(rover) (points/data as habitat science)
"""

from __future__ import annotations

from app.simulation.domain.enums import EventKind, OpportunityStatus, ProvenanceKind, RoverStatus
from app.simulation.domain.state import Provenance
from app.simulation.engine.context import TickContext
from app.simulation.systems.common import component_performance
from app.simulation.systems.comms_science import complete_opportunity

HALTED_DRAW_FRACTION = 0.25


def _lose(ctx: TickContext, cause: str) -> None:
    rover = ctx.state.rover
    rover.status = RoverStatus.LOST
    rover.status_set_by = Provenance(
        kind=ProvenanceKind.ENGINE, ref=f"rover_lost:{cause}", tick=ctx.tick
    )
    if rover.target_opportunity:
        opp = ctx.state.science.opportunities.get(rover.target_opportunity)
        if opp is not None and opp.status == OpportunityStatus.ACTIVE:
            opp.status = OpportunityStatus.OPEN
    ctx.emit(
        EventKind.ROVER,
        "rover_lost",
        message_key=f"rover.lost.{cause}",
        data={"cause": cause, "battery_kwh": rover.battery_kwh},
    )


def update(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    rover, cfg = st.rover, sc.rover
    if rover.status not in (RoverStatus.TRAVERSING, RoverStatus.RETURNING):
        return

    halted = cfg.teleop_requires_link and not st.comms.link_up
    draw = cfg.traverse_kw * ctx.dt_hours * (HALTED_DRAW_FRACTION if halted else 1.0)
    rover.battery_kwh = max(0.0, rover.battery_kwh - draw)
    if rover.battery_kwh <= 0.0:
        _lose(ctx, "battery_depleted")
        return

    health = st.components[cfg.component].health
    if ctx.chance("rover_loss", cfg.loss_probability_per_tick * (1.0 - health)):
        _lose(ctx, "mobility_fault")
        return
    if halted:
        return

    if rover.status == RoverStatus.RETURNING:
        rover.progress_ticks -= 1
        if rover.progress_ticks <= 0:
            rover.progress_ticks = 0
            rover.status = RoverStatus.DOCKED
            rover.target_opportunity = None
            rover.status_set_by = Provenance(
                kind=ProvenanceKind.ENGINE, ref="rover_docked", tick=ctx.tick
            )
            ctx.emit(EventKind.ROVER, "rover_docked", message_key="rover.docked")
        return

    if rover.progress_ticks < cfg.outbound_ticks:
        rover.progress_ticks += 1
        if rover.progress_ticks == cfg.outbound_ticks:
            ctx.emit(
                EventKind.ROVER,
                "rover_on_site",
                message_key="rover.on_site",
                data={"opportunity": rover.target_opportunity},
            )
        return

    target = rover.target_opportunity
    opp = st.science.opportunities.get(target) if target else None
    if opp is None or opp.status not in (OpportunityStatus.OPEN, OpportunityStatus.ACTIVE):
        rover.status = RoverStatus.RETURNING
        rover.status_set_by = Provenance(
            kind=ProvenanceKind.ENGINE, ref="rover_auto_return", tick=ctx.tick
        )
        return
    spec = sc.opportunity(opp.id)
    opp.status = OpportunityStatus.ACTIVE
    output = component_performance(sc, st, cfg.component)
    opp.progress_ticks += output
    st.science.points += spec.points_per_tick * output
    st.science.data_pending_mb += spec.data_mb_per_tick * output
    if opp.progress_ticks >= spec.work_ticks_required - 1e-9:
        complete_opportunity(ctx, opp.id)
        rover.status = RoverStatus.RETURNING
        rover.status_set_by = Provenance(
            kind=ProvenanceKind.ENGINE, ref="rover_auto_return", tick=ctx.tick
        )
