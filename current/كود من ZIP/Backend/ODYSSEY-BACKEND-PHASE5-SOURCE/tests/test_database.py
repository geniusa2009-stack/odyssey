"""Persistence: ORM models, append-only ledger guarantees, Alembic migrations (SQLite + PG)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import models as m
from app.db.session import create_engine, create_session_factory
from app.services.reference_data import sync_reference_data
from app.simulation.domain.decisions import parse_decision
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.ledger import GENESIS_HASH, record_decision

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "missions",
    "mission_scenarios",
    "mission_sessions",
    "mission_participants",
    "mission_decisions",
    "mission_events",
    "mission_snapshots",
    "mission_timelines",
    "mission_timeline_branches",
    "mission_outcomes",
    "mission_profiles",
    "mission_dna",
    "science_evidence",
    "nasa_sources",
    "simulation_runs",
    # Phase 4: retained realtime events (resume) and idempotency records
    "mission_realtime_events",
    "idempotency_records",
    # Phase 5: open-world game backend (odyssey.game.v1), migration 0003
    "game_profiles",
    "game_sessions",
    "game_timelines",
    "game_state_snapshots",
    "game_checkpoints",
    "game_commands",
    "game_events",
}


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


async def _seed_ledger_row(engine: AsyncEngine, sim: SimulationEngine) -> str:
    factory = create_session_factory(engine)
    async with factory() as db:
        await sync_reference_data(db)
        scenario = (await db.execute(select(m.MissionScenario))).scalars().first()
        assert scenario is not None
        sid, tid = str(uuid.uuid4()), str(uuid.uuid4())
        state = sim.initial_state(1)
        db.add(
            m.MissionSession(
                id=sid, scenario_id=scenario.id, seed=1, status="active", active_timeline_id=tid
            )
        )
        await db.flush()
        db.add(
            m.MissionTimeline(
                id=tid,
                session_id=sid,
                head_state_hash=state.state_hash(),
                head_record_hash=GENESIS_HASH,
            )
        )
        await db.flush()
        rec, _ = record_decision(
            sim,
            state,
            parse_decision({"type": "set_ration_level", "level": 0.9}),
            session_id=sid,
            timeline_id=tid,
            sequence=1,
            prev_record_hash=GENESIS_HASH,
        )
        assert rec.state_before is not None and rec.state_after is not None
        db.add(
            m.MissionDecision(
                decision_id=rec.decision_id,
                session_id=sid,
                timeline_id=tid,
                sequence=1,
                tick=0,
                decision_type=rec.decision_type,
                inputs=rec.inputs,
                phase=rec.phase,
                affected_systems=list(rec.affected_systems),
                state_before=rec.state_before,
                state_after=rec.state_after,
                state_before_hash=rec.state_before_hash,
                state_after_hash=rec.state_after_hash,
                prev_record_hash=rec.prev_record_hash,
                record_hash=rec.record_hash,
                meta={},
            )
        )
        await db.commit()
        return rec.decision_id


async def _assert_ledger_guarded(url: str, sim: SimulationEngine, *, postgres: bool) -> None:
    engine = create_engine(url)
    try:
        decision_id = await _seed_ledger_row(engine, sim)
        factory = create_session_factory(engine)
        # 1. ORM guard
        async with factory() as db:
            row = await db.get(m.MissionDecision, decision_id)
            assert row is not None
            row.tick = 5
            with pytest.raises(m.LedgerImmutableError):
                await db.flush()
            await db.rollback()
        async with factory() as db:
            row = await db.get(m.MissionDecision, decision_id)
            await db.delete(row)
            with pytest.raises(m.LedgerImmutableError):
                await db.flush()
            await db.rollback()
        # 2. Database triggers (raw SQL bypassing the ORM)
        for stmt in ("UPDATE mission_decisions SET tick = 9", "DELETE FROM mission_decisions"):
            async with engine.begin() as conn:
                with pytest.raises(DBAPIError, match="append-only"):
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            count = (await conn.execute(text("SELECT count(*) FROM mission_decisions"))).scalar()
            assert count == 1
        # 3. PostgreSQL only: explicit, transaction-scoped retention override
        if postgres:
            async with engine.begin() as conn:
                await conn.execute(text("SET LOCAL odyssey.allow_ledger_delete = 'on'"))
                await conn.execute(text("DELETE FROM mission_decisions"))
            async with engine.connect() as conn:
                count = (
                    await conn.execute(text("SELECT count(*) FROM mission_decisions"))
                ).scalar()
                assert count == 0
    finally:
        await engine.dispose()


class TestSqlite:
    async def test_create_all_and_reference_sync_is_idempotent(self, sqlite_url: str) -> None:
        engine = create_engine(sqlite_url)
        async with engine.begin() as conn:
            await conn.run_sync(m.Base.metadata.create_all)
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert tables == EXPECTED_TABLES
        factory = create_session_factory(engine)
        async with factory() as db:
            await sync_reference_data(db)
            await sync_reference_data(db)
            assert len((await db.execute(select(m.MissionScenario))).scalars().all()) == 1
            assert len((await db.execute(select(m.ScienceEvidenceRecord))).scalars().all()) >= 8
        await engine.dispose()

    async def test_ledger_is_append_only(self, sqlite_url: str, engine: SimulationEngine) -> None:
        db_engine = create_engine(sqlite_url)
        async with db_engine.begin() as conn:
            await conn.run_sync(m.Base.metadata.create_all)
        await db_engine.dispose()
        await _assert_ledger_guarded(sqlite_url, engine, postgres=False)

    def test_migrations_upgrade_check_downgrade(self, tmp_path: Path) -> None:
        url = f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"
        for args in (("upgrade", "head"), ("check",), ("downgrade", "base"), ("upgrade", "head")):
            result = _alembic(url, *args)
            assert result.returncode == 0, result.stderr

        async def tables() -> set[str]:
            eng = create_engine(url)
            async with eng.connect() as conn:
                names = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            await eng.dispose()
            return names

        assert asyncio.run(tables()) == EXPECTED_TABLES | {"alembic_version"}

    def test_migrated_schema_has_ledger_triggers(
        self, tmp_path: Path, engine: SimulationEngine
    ) -> None:
        url = f"sqlite+aiosqlite:///{tmp_path / 'mig2.db'}"
        assert _alembic(url, "upgrade", "head").returncode == 0
        asyncio.run(_assert_ledger_guarded(url, engine, postgres=False))

    def test_offline_sql_generation(self) -> None:
        result = _alembic("postgresql+asyncpg://u:p@localhost/x", "upgrade", "head", "--sql")
        assert result.returncode == 0, result.stderr
        assert "CREATE TABLE mission_decisions" in result.stdout
        assert "trg_mission_decisions_append_only" in result.stdout


@pytest.mark.postgres
class TestPostgres:
    @pytest.fixture
    def fresh_pg(self, postgres_url: str) -> str:
        async def reset() -> None:
            eng = create_engine(postgres_url)
            async with eng.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
            await eng.dispose()

        asyncio.run(reset())
        return postgres_url

    def test_migrations_upgrade_check_downgrade(self, fresh_pg: str) -> None:
        for args in (("upgrade", "head"), ("check",), ("downgrade", "base"), ("upgrade", "head")):
            result = _alembic(fresh_pg, *args)
            assert result.returncode == 0, result.stderr

    def test_ledger_is_append_only_with_retention_override(
        self, fresh_pg: str, engine: SimulationEngine
    ) -> None:
        assert _alembic(fresh_pg, "upgrade", "head").returncode == 0
        asyncio.run(_assert_ledger_guarded(fresh_pg, engine, postgres=True))
