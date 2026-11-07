"""Communications and science operations.

Communications:
    link_up   = earth_visible ∧ comms_output ≥ 0.5
    downlink  = min(pending, rate_mb_h · Δt · comms_output)   when link_up
Science (habitat activities; rover activities are handled by the rover system):
    output    = science_consumer_output · crew_factor
    crew_factor = health of the science officer in the habitat (else ½ · best crew in habitat)
    progress += output;  points += points_per_tick · output;  data += data_mb_per_tick · output
    Opportunities that pass their window are MISSED.
"""

from __future__ import annotations

from app.simulation.domain.enums import CrewLocation, CrewRole, EventKind, OpportunityStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import TickContext
from app.simulation.systems.common import consumer_output


def _crew_factor(state: MissionState) -> float:
    """Science needs crew working in the habitat lab (not sheltering or on EVA)."""
    in_lab = [c for c in state.crew if c.health > 0 and c.location == CrewLocation.HABITAT]
    officers = [c.health for c in in_lab if c.role == CrewRole.SCIENCE_OFFICER]
    if officers:
        return max(officers)
    return max((c.health for c in in_lab), default=0.0) * 0.5


def update_comms(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    output = consumer_output(sc, st, sc.power.comms_consumer)
    was_up = st.comms.link_up
    st.comms.link_up = st.environment.earth_visible and output >= 0.5
    if st.comms.link_up:
        sent = min(
            st.science.data_pending_mb, sc.comms.downlink_mb_per_hour * ctx.dt_hours * output
        )
        st.science.data_pending_mb -= sent
        st.comms.data_downlinked_mb += sent
    if was_up != st.comms.link_up:
        ctx.emit(
            EventKind.COMMUNICATION,
            "link_restored" if st.comms.link_up else "link_lost",
            message_key="comms.link_restored" if st.comms.link_up else "comms.link_lost",
            data={"earth_visible": st.environment.earth_visible, "comms_output": output},
        )


def complete_opportunity(ctx: TickContext, opportunity_id: str) -> None:
    opp = ctx.state.science.opportunities[opportunity_id]
    opp.status = OpportunityStatus.COMPLETED
    if ctx.state.science.active_opportunity == opportunity_id:
        ctx.state.science.active_opportunity = None
    ctx.emit(
        EventKind.MILESTONE,
        f"science_completed:{opportunity_id}",
        message_key="science.completed",
        data={"opportunity": opportunity_id},
    )


def update_science(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    sci = st.science
    for opp_id in sorted(sci.opportunities):
        opp = sci.opportunities[opp_id]
        if (
            opp.status in (OpportunityStatus.OPEN, OpportunityStatus.ACTIVE)
            and ctx.tick >= opp.closes_tick
        ):
            opp.status = OpportunityStatus.MISSED
            if sci.active_opportunity == opp_id:
                sci.active_opportunity = None
            ctx.emit(
                EventKind.SCIENCE_OPPORTUNITY,
                f"science_missed:{opp_id}",
                message_key="science.missed",
                data={"opportunity": opp_id},
            )

    active = sci.active_opportunity
    if active is None:
        return
    spec = sc.opportunity(active)
    output = consumer_output(sc, st, sc.power.science_consumer) * _crew_factor(st)
    opp = sci.opportunities[active]
    opp.progress_ticks += output
    sci.points += spec.points_per_tick * output
    sci.data_pending_mb += spec.data_mb_per_tick * output
    if opp.progress_ticks >= spec.work_ticks_required - 1e-9:
        complete_opportunity(ctx, active)
