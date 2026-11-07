"""In-memory game runtime (no database): the same turn logic as production.

Used by domain tests, property tests and the fuzzer. Mission transitions create a fresh
in-memory simulation; rewind is not modelled here (it is a persistence feature, tested through
the service).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.game.actions.planner import Command
from app.game.application.ports import InMemorySimPort
from app.game.application.turn import TurnResult, public_state, run_turn, settle_new_mission
from app.game.campaign.campaign import first_mission, new_campaign, start_mission
from app.game.content.loader import LoadedContent
from app.game.realtime.derive import DerivedEvent, PublicState, campaign_events, derive
from app.game.runtime.clock import FakeClock
from app.game.world.sim import SimView
from app.game.world.state import CampaignMeta, TimelineGameState
from app.simulation.canonical import sha256_hex
from app.simulation.engine.engine import SimulationEngine


def mission_seed(session_seed: int, mission_id: str, attempt: int) -> int:
    """Deterministic per-mission seed derived from the (secret) session seed."""
    digest = sha256_hex({"seed": session_seed, "mission": mission_id, "attempt": attempt})
    return int(digest[:12], 16) % (2**31 - 1)


@dataclass
class InMemoryGame:
    content: LoadedContent
    seed: int = 7
    clock: FakeClock = field(default_factory=FakeClock)
    meta: CampaignMeta = field(init=False)
    doc: TimelineGameState = field(init=False)
    port: InMemorySimPort = field(init=False)
    events: list[DerivedEvent] = field(default_factory=list)
    version: int = 0
    _engines: dict[str, SimulationEngine] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.meta = new_campaign(self.content)
        self._start(first_mission(self.content).id)

    def _engine(self, mission_id: str) -> SimulationEngine:
        scenario = self.content.mission_scenario(mission_id)
        if scenario.id not in self._engines:
            self._engines[scenario.id] = SimulationEngine(scenario)
        return self._engines[scenario.id]

    def start(self, mission_id: str) -> None:
        """Start (or replay) a mission explicitly."""
        self._start(mission_id)
        self.version += 1

    def _start(self, mission_id: str) -> None:
        meta = self.meta.model_copy(deep=True)
        doc = start_mission(self.content, meta, mission_id)
        attempt = meta.missions[mission_id].attempts
        self.port = InMemorySimPort(
            self._engine(mission_id),
            mission_seed(self.seed, mission_id, attempt),
            timeline_id=f"{mission_id}:{attempt}",
        )
        settle_new_mission(self.content, doc, meta, self.port.engine, self.port._state)
        self.meta, self.doc = meta, doc

    @property
    def sim(self) -> SimView:
        return SimView(self.port.engine, self.port._state)

    def snapshot(self) -> PublicState:
        return public_state(self.content, self.doc, self.meta, self.sim)

    async def _turn(self, command: Command | None) -> TurnResult:
        before = self.snapshot()
        saved = self.port.checkpoint()
        try:
            result = await run_turn(
                self.content, self.doc, self.meta, self.port, self.clock.now_ms(), command
            )
        except Exception:
            self.port.restore(saved)  # a rejected turn changes nothing (like a DB rollback)
            raise
        changed = (
            result.doc.state_hash() != self.doc.state_hash()
            or result.meta.state_hash() != self.meta.state_hash()
            or result.decision_ids
            or result.ticks_advanced
        )
        self.doc, self.meta = result.doc, result.meta
        if result.completion is not None and result.completion.next_mission is not None:
            after_campaign = self.snapshot().campaign
            self._start(result.completion.next_mission)
            self.events += campaign_events(before.campaign, after_campaign)
            self.events.append(
                DerivedEvent(
                    "mission.transitioned", "campaign", {"to": result.completion.next_mission}
                )
            )
        else:
            self.events += derive(before, self.snapshot())
        if changed:
            self.version += 1
        return result

    async def act(self, action: str, target: str | None = None, **params: object) -> TurnResult:
        return await self._turn(Command(action=action, target=target, params=params))

    async def sync(self) -> TurnResult:
        return await self._turn(None)

    async def wait(self, seconds: float) -> TurnResult:
        self.clock.advance(seconds)
        return await self.sync()
