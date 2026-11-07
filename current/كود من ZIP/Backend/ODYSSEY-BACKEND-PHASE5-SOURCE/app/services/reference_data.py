"""Idempotent sync of packaged reference data (missions, scenarios, evidence, sources)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.nasa.providers import all_sources
from app.science.evidence import default_registry
from app.simulation.scenarios.loader import list_scenarios, scenario_content_hash


async def sync_reference_data(db: AsyncSession) -> None:
    for scenario in list_scenarios():
        mission = await db.get(m.Mission, scenario.mission_id)
        if mission is None:
            db.add(
                m.Mission(
                    id=scenario.mission_id, title=scenario.title, description=scenario.description
                )
            )
        else:
            mission.title, mission.description = scenario.title, scenario.description
        content_hash = scenario_content_hash(scenario)
        existing = (
            await db.execute(
                select(m.MissionScenario).where(
                    m.MissionScenario.scenario_key == scenario.id,
                    m.MissionScenario.version == scenario.version,
                    m.MissionScenario.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            await db.flush()
            db.add(
                m.MissionScenario(
                    id=str(uuid.uuid4()),
                    mission_id=scenario.mission_id,
                    scenario_key=scenario.id,
                    version=scenario.version,
                    content_hash=content_hash,
                    provisional=scenario.provisional,
                    definition=scenario.model_dump(mode="json", by_alias=True),
                )
            )

    for ev in default_registry().all():
        values: dict[str, Any] = {
            "concept": ev.concept,
            "claim": ev.claim,
            "value": ev.value,
            "unit": ev.unit,
            "source_name": ev.source_name,
            "source_citation": ev.source_citation,
            "source_url": str(ev.source_url) if ev.source_url else None,
            "retrieved_date": ev.retrieved_date,
            "verification_status": ev.verification_status,
            "simulation_usage": list(ev.simulation_usage),
            "simplification": ev.simplification,
            "confidence": ev.confidence,
            "notes": ev.notes,
        }
        row = await db.get(m.ScienceEvidenceRecord, ev.id)
        if row is None:
            db.add(m.ScienceEvidenceRecord(id=ev.id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)

    for src in all_sources():
        src_values: dict[str, Any] = {
            "source_name": src.source_name,
            "dataset": src.dataset,
            "url": src.url,
            "retrieved_at": src.retrieved_at,
            "license_notes": src.license_notes,
            "variables_used": list(src.variables_used),
            "transformation_notes": src.transformation_notes,
            "origin": src.origin,
            "is_real_data": src.is_real_data,
        }
        srow = await db.get(m.NASASourceRecord, src.id)
        if srow is None:
            db.add(m.NASASourceRecord(id=src.id, **src_values))
        else:
            for key, value in src_values.items():
                setattr(srow, key, value)
    await db.commit()
