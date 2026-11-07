"""Decision ledger (immutability + hash chain), deterministic replay, timelines and forks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.domain.decisions import parse_decision
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.replay.ledger import (
    GENESIS_HASH,
    LedgerIntegrityError,
    make_decision_id,
    verify_chain,
)
from app.simulation.replay.replay import (
    ReplayDecision,
    ReplayDivergenceError,
    ReplayOrderError,
    replay,
)
from app.simulation.replay.timeline import (
    TimelineError,
    TimelineSpec,
    effective_ledger,
    plan_fork,
)
from tests.helpers import Plan, PlayedMission, play

PLAN: Plan = {
    15: [{"type": "start_science_activity", "opportunity_id": "regolith_survey"}],
    40: [
        {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"},
        {"type": "set_thermal_setpoint", "target_c": 18.0},
    ],
    121: [{"type": "set_crew_location", "location": "shelter"}],
    131: [{"type": "set_crew_location", "location": "habitat"}],
}


@pytest.fixture(scope="module")
def played(engine: SimulationEngine) -> PlayedMission:
    return play(engine, 42, PLAN, 160)


class TestLedger:
    def test_record_fields(self, played: PlayedMission) -> None:
        rec = played.records[1]
        assert rec.sequence == 2 and rec.tick == 40
        assert rec.decision_type == "set_subsystem_mode"
        assert rec.inputs == {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"}
        assert rec.phase == "initial_resource_management"
        assert rec.affected_systems == ("power", "communications")
        assert rec.state_before is not None and rec.state_after is not None
        assert rec.state_before["power"]["consumers"]["comms"]["mode"] == "nominal"
        assert rec.state_after["power"]["consumers"]["comms"]["mode"] == "eco"
        assert rec.prev_record_hash == played.records[0].record_hash
        assert played.records[0].prev_record_hash == GENESIS_HASH

    def test_records_are_immutable(self, played: PlayedMission) -> None:
        with pytest.raises(ValidationError):
            played.records[0].tick = 99  # type: ignore[misc]

    def test_decision_ids_deterministic_and_unique(self, played: PlayedMission) -> None:
        ids = [r.decision_id for r in played.records]
        assert len(set(ids)) == len(ids)
        r = played.records[0]
        assert make_decision_id(r.timeline_id, r.sequence, r.tick, r.inputs) == r.decision_id

    def test_chain_verifies(self, played: PlayedMission) -> None:
        verify_chain(played.records)

    @pytest.mark.parametrize("tamper", ["inputs", "hash", "reorder", "drop", "tick"])
    def test_tampering_is_detected(self, played: PlayedMission, tamper: str) -> None:
        recs = list(played.records)
        if tamper == "inputs":
            recs[1] = recs[1].model_copy(update={"inputs": {**recs[1].inputs, "mode": "off"}})
        elif tamper == "hash":
            recs[2] = recs[2].model_copy(update={"state_after_hash": "f" * 64})
        elif tamper == "reorder":
            recs[1], recs[2] = recs[2], recs[1]
        elif tamper == "drop":
            del recs[1]
        elif tamper == "tick":
            recs[3] = recs[3].model_copy(update={"tick": 1})
        with pytest.raises(LedgerIntegrityError):
            verify_chain(recs)


class TestReplay:
    def test_reconstruct_from_initial_plus_ledger(
        self, engine: SimulationEngine, played: PlayedMission
    ) -> None:
        res = replay(
            engine,
            played.initial,
            [ReplayDecision.from_record(r) for r in played.records],
            played.final.tick,
            verify_hashes=True,
        )
        assert res.state.state_hash() == played.final.state_hash()
        assert [a.decision_id for a in res.applied] == [r.decision_id for r in played.records]

    def test_history_indexes_ticks(self, engine: SimulationEngine, played: PlayedMission) -> None:
        early = [ReplayDecision.from_record(r) for r in played.records if r.tick <= 50]
        res = replay(engine, played.initial, early, 50, record_history=True)
        assert [s.tick for s in res.history] == list(range(51))
        assert res.history[40].power.consumers["comms"].mode == "eco"  # effective state at t
        assert res.history[39].power.consumers["comms"].mode == "nominal"

    def test_divergence_detected(self, engine: SimulationEngine, played: PlayedMission) -> None:
        bad = [ReplayDecision.from_record(r) for r in played.records]
        bad[0] = ReplayDecision(
            bad[0].decision_id,
            bad[0].sequence,
            bad[0].tick,
            bad[0].decision,
            bad[0].expected_before_hash,
            "0" * 64,
        )
        with pytest.raises(ReplayDivergenceError):
            replay(engine, played.initial, bad, played.final.tick, verify_hashes=True)

    def test_order_errors(self, engine: SimulationEngine, played: PlayedMission) -> None:
        decisions = [ReplayDecision.from_record(r) for r in played.records]
        with pytest.raises(ReplayOrderError, match="beyond"):
            replay(engine, played.initial, decisions, 20)
        swapped = [decisions[3], decisions[0]]  # tick 121 then tick 15
        swapped = [
            ReplayDecision(d.decision_id, i + 1, d.tick, d.decision) for i, d in enumerate(swapped)
        ]
        with pytest.raises(ReplayOrderError):
            replay(engine, played.initial, swapped, 200)

    def test_invalid_decision_raises_or_is_skipped(self, engine: SimulationEngine) -> None:
        initial = engine.initial_state(1)
        d = ReplayDecision("x", 1, 3, parse_decision({"type": "stop_science_activity"}))
        with pytest.raises(DecisionRejectedError):
            replay(engine, initial, [d], 10)
        res = replay(engine, initial, [d], 10, skip_invalid=True)
        assert res.skipped == [("x", "no_active_science")]

    def test_replay_does_not_mutate_initial(
        self, engine: SimulationEngine, played: PlayedMission
    ) -> None:
        before = played.initial.state_hash()
        replay(
            engine,
            played.initial,
            [ReplayDecision.from_record(r) for r in played.records],
            played.final.tick,
        )
        assert played.initial.state_hash() == before


class TestTimelines:
    def test_effective_ledger_truncates_parent_at_fork(self, played: PlayedMission) -> None:
        main = TimelineSpec(timeline_id="tl-main")
        fork = TimelineSpec(
            timeline_id="tl-b", parent_timeline_id="tl-main", fork_sequence=2, fork_tick=40
        )
        alt = played.records[2].model_copy(update={"timeline_id": "tl-b", "sequence": 3})
        specs = {"tl-main": main, "tl-b": fork}
        own = {"tl-main": played.records, "tl-b": [alt]}
        eff = effective_ledger(fork, specs.__getitem__, own.__getitem__)
        assert [r.sequence for r in eff] == [1, 2, 3]
        assert eff[-1].timeline_id == "tl-b"
        assert effective_ledger(main, specs.__getitem__, own.__getitem__) == played.records

    def test_cycles_rejected(self) -> None:
        a = TimelineSpec(timeline_id="a", parent_timeline_id="b", fork_sequence=0)
        b = TimelineSpec(timeline_id="b", parent_timeline_id="a", fork_sequence=0)
        specs = {"a": a, "b": b}
        with pytest.raises(TimelineError, match="cycle"):
            effective_ledger(a, specs.__getitem__, lambda _: [])

    def test_plan_fork(self, played: PlayedMission) -> None:
        plan = plan_fork(played.records, played.records[2].decision_id)
        assert plan.fork_sequence == 2 and plan.fork_tick == 40
        assert [r.sequence for r in plan.inherited] == [1, 2]
        assert plan.prev_record_hash == played.records[1].record_hash
        assert plan.next_sequence == 3
        first = plan_fork(played.records, played.records[0].decision_id)
        assert first.inherited == () and first.prev_record_hash == GENESIS_HASH
        with pytest.raises(TimelineError):
            plan_fork(played.records, "dec_missing")

    def test_branch_with_alternative_diverges_and_parent_unchanged(
        self, engine: SimulationEngine, played: PlayedMission
    ) -> None:
        """Rewind one decision: replay to the fork, apply an alternative, continue."""
        parent_hashes = [r.record_hash for r in played.records]
        target = played.records[2]  # set_thermal_setpoint at tick 40
        plan = plan_fork(played.records, target.decision_id)
        fork_state = replay(
            engine,
            played.initial,
            [ReplayDecision.from_record(r) for r in plan.inherited],
            plan.fork_tick,
            verify_hashes=True,
        ).state
        assert fork_state.state_hash() == target.state_before_hash
        alt = engine.apply_decision(
            fork_state, parse_decision({"type": "set_thermal_setpoint", "target_c": 12.0}), "alt"
        ).state
        branch_end = engine.advance(alt, played.final.tick - alt.tick).state
        assert branch_end.state_hash() != played.final.state_hash()
        assert [r.record_hash for r in played.records] == parent_hashes
        verify_chain(played.records)
