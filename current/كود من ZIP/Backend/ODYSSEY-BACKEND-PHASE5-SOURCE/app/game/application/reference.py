"""Pinned simulation scenario rows for game missions (synced at startup, idempotent).

Registry scenarios (LUNA-01) are already synced by the v1 reference data. Game-content scenarios
(Earth Command) get a ``missions`` row with ``managed_by='game'`` (hidden from v1 ``/missions``)
and a content-hashed ``mission_scenarios`` row, so their sessions are replayable and verifiable
by the same ledger machinery as v1 sessions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import IntegrityFailure
from app.db import models as m
from app.game.content.loader import LoadedContent
from app.simulation.scenarios.loader import scenario_content_hash
from app.simulation.scenarios.schema import ScenarioDefinition

GAME_MANAGED = "game"
# Scenario rows get name-based (uuid5) ids: the same pinned content always maps to the same row
# id, startup consumes no randomness, and concurrent workers cannot create diverging rows.
_SCENARIO_NAMESPACE = uuid.UUID("6f1d2b7e-0d55-5c3a-9a43-6f6479737365")


def scenario_row_id(scenario: ScenarioDefinition) -> str:
    key = f"{scenario.id}:{scenario.version}:{scenario_content_hash(scenario)}"
    return str(uuid.uuid5(_SCENARIO_NAMESPACE, key))


async def _row(db: AsyncSession, scenario: ScenarioDefinition) -> m.MissionScenario | None:
    return (
        await db.execute(
            select(m.MissionScenario).where(
                m.MissionScenario.scenario_key == scenario.id,
                m.MissionScenario.version == scenario.version,
                m.MissionScenario.content_hash == scenario_content_hash(scenario),
            )
        )
    ).scalar_one_or_none()


async def sync_game_reference_data(db: AsyncSession, content: LoadedContent) -> None:
    for mission in content.content.campaign.missions:
        if mission.scenario.source != "game":
            continue
        scenario = content.scenarios[mission.scenario.id]
        row = await db.get(m.Mission, scenario.mission_id)
        if row is None:
            db.add(
                m.Mission(
                    id=scenario.mission_id,
                    title=scenario.title,
                    description=scenario.description,
                    managed_by=GAME_MANAGED,
                )
            )
        elif row.managed_by != GAME_MANAGED:
            raise IntegrityFailure(
                "game scenario collides with a v1 mission", code="content_conflict"
            )
        await db.flush()
        if await _row(db, scenario) is None:
            db.add(
                m.MissionScenario(
                    id=scenario_row_id(scenario),
                    mission_id=scenario.mission_id,
                    scenario_key=scenario.id,
                    version=scenario.version,
                    content_hash=scenario_content_hash(scenario),
                    provisional=scenario.provisional,
                    definition=scenario.model_dump(mode="json", by_alias=True),
                )
            )
    await db.commit()


async def scenario_row(db: AsyncSession, scenario: ScenarioDefinition) -> m.MissionScenario:
    row = await _row(db, scenario)
    if row is None:
        raise IntegrityFailure("pinned scenario row missing", code="scenario_missing")
    return row
