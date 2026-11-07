"""Crew read models: role, health band, fatigue, dose, location, shelter and EVA state.

Only quantities the engine models are exposed (no psychological or invented state).
"""

from __future__ import annotations

from typing import Literal

from app.read_models.common import StatusBand, View, rnd
from app.simulation.domain.enums import CrewLocation
from app.simulation.domain.state import CrewMemberState, MissionState
from app.simulation.engine.engine import SimulationEngine

CrewCondition = Literal["healthy", "impaired", "critical", "incapacitated"]


class CrewMemberStatus(View):
    id: str
    role: str
    status: CrewCondition
    health: float
    health_band: StatusBand
    fatigue: float
    dose_msv: float
    location: str
    in_shelter: bool
    on_eva: bool
    eva_remaining_ticks: int


class CrewOverview(View):
    members: list[CrewMemberStatus]
    active_count: int
    in_shelter: int
    on_eva: int
    min_health: float


def _condition(health: float) -> tuple[CrewCondition, StatusBand]:
    if health <= 0:
        return "incapacitated", "critical"
    if health < 0.3:
        return "critical", "critical"
    if health < 0.9:
        return "impaired", "degraded"
    return "healthy", "nominal"


def build_member(engine: SimulationEngine, member: CrewMemberState) -> CrewMemberStatus:
    status, health_band = _condition(member.health)
    return CrewMemberStatus(
        id=member.id,
        role=member.role.value,
        status=status,
        health=rnd(member.health, 3),
        health_band=health_band,
        fatigue=rnd(member.fatigue, 3),
        dose_msv=rnd(member.dose_msv, 2),
        location=member.location.value,
        in_shelter=member.location == CrewLocation.SHELTER,
        on_eva=member.location == CrewLocation.EVA,
        eva_remaining_ticks=member.eva_remaining_ticks,
    )


def build_crew(engine: SimulationEngine, state: MissionState) -> CrewOverview:
    members = [build_member(engine, m) for m in state.crew]
    return CrewOverview(
        members=members,
        active_count=sum(1 for m in state.crew if m.health > 0),
        in_shelter=sum(1 for m in members if m.in_shelter),
        on_eva=sum(1 for m in members if m.on_eva),
        min_health=min((m.health for m in members), default=0.0),
    )
