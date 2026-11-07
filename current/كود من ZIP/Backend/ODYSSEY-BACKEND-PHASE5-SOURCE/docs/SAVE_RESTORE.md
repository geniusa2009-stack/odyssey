# Saves, Restore, Rewind and Timeline Ownership

The backend owns authoritative mission/campaign state. Unreal's local state is never the
source of truth, and no render state is persisted.

## What is saved, continuously

Every accepted turn commits, in one transaction: the timeline document, campaign meta, the
session's `state_version`/`event_seq`, the command log, a rewind anchor (when the command
recorded simulation decisions), checkpoints, retained events and the idempotency record. The
simulation's own ledger (decisions, snapshots, events) is written in the same transaction. A
crash between requests loses nothing that was acknowledged; a crash mid-request loses nothing
partially.

## Checkpoints (`GET /checkpoints`)

| Kind | Written when |
|---|---|
| `mission_transition` | session created, mission started, mission ended (result), next mission started |
| `critical_decision` | an accepted critical action that changed the simulation (`repair.perform`, `mission.authorize`, `crew.assign_location`, `module.install`, `module.remove`, `vehicle.dispatch`) and every rewind |
| `incident_resolved` | a turn resolved an incident |
| `manual` | `checkpoint.save` (optional label) |
| `auto` | every 25th state version; the newest 10 are kept |

Each checkpoint stores the timeline document and campaign meta at that version, the mission,
timeline, simulation tick and the player's semantic `location` (Unreal restores the exact spawn
from its own anchor configuration). Checkpoints are save records; play always resumes from the
head of the active timeline, and going *back* in a mission is Rewind.

## The single restore path: `POST /sessions/{id}/restore {"last_seq": N}`

After a restart or a dropped connection Unreal asks once and gets everything:

1. The server settles the mission clock (time continued while disconnected if the mission was
   running; capped at `max_catchup_ticks`, then paused with `unattended_limit`).
2. It returns the authoritative **snapshot** — campaign, phase, mission, timeline, clock,
   semantic location, world state, unlocked areas, active incidents, discoveries, insights,
   resume metadata (`last_seq`, WebSocket/events/restore paths).
3. `events`: every retained event after `last_seq`, or `resync_required: true` with
   `reason: events_expired` when they are gone, or `backlog_too_large` when more than one page
   (500) was missed — the snapshot is then the truth.
4. `while_disconnected`: ticks advanced, from/to tick and a count of event types — what happened
   while the player was away.

Restoring twice at the same instant advances nothing. The Phase 1 end-to-end test restarts the
server process on the same database and asserts the restored snapshot equals the one taken
before the disconnect, field for field.

## Rewind (`GET /rewind-points`, `POST /rewind`)

Rewind reuses the existing timeline branching: `MissionService.branch` forks the simulation
timeline at the recorded decision (ledger replay, hash-verified); the game forks the timeline
document from the **pre-decision anchor** captured when that command was accepted. The old
timeline is kept (`rewound`, still inspectable through the Black Box); the new one becomes
active, its clock paused (`rewound`); the client receives `timeline.changed` with
`snapshot_required`. Rewind requires `expected_state_version` (stale → `STALE_STATE`), works
only on the active timeline of an active mission, and only to commands that recorded simulation
decisions (`command_not_rewindable` otherwise).

## Timeline ownership

The conservative rule that makes rewind safe:

| Timeline-local (forked/discarded by rewind) | Campaign-global (never touched by rewind) |
|---|---|
| mission resources and simulation state | player profile |
| mission decisions (simulation ledger branch) | completed-mission history and attempts |
| temporary damage, repairs, system states | committed capability evidence and stages |
| temporary cargo state, inventories, installed modules | certifications |
| objectives, incidents, facts, flags | committed discoveries |
| crew intents, cue cooldowns | knowledge (insights) |
| player semantic location, the clock | carried cargo between missions |
| **pending** discoveries and evidence | persistent infrastructure records |

* Campaign meta changes only at **mission completion** (atomic commit of the completing
  timeline's pending items) and on **knowledge unlock**. Knowledge has no gameplay power, so
  keeping an insight learned on an abandoned timeline cannot be exploited; everything with
  gameplay power (evidence → capability stages → certifications, discoveries, infrastructure,
  carried cargo) is committed only from the timeline that actually completes.
* A completed mission's timeline is no longer active: its commands cannot be rewound, and a
  non-replayable completed mission cannot be started again. Replaying a replayable mission
  (LUNA-01) starts a fresh attempt on a fresh simulation; completing it again re-derives stages
  from the same evidence set and cannot duplicate certifications or discoveries.
* Tests: `tests/test_game_rewind_and_saves.py` (rewind restores timeline-local state and leaves
  the campaign byte-identical; pending discoveries are dropped and committed once; completed
  missions cannot be rewound or farmed), the API fuzzer (random rewinds never change campaign
  state), `tests/test_game_infrastructure.py` (failure commits nothing; replay).

## Idempotency and concurrency

See [UNREAL_BACKEND_CONTRACT.md](UNREAL_BACKEND_CONTRACT.md#state-versions). Repeated sample
collection, cargo transfers, certification, mission authorization, module installation,
discovery and repairs never duplicate effects (one idempotency key → one mutation; `once`
interactions; completion commits once; race tests on SQLite and PostgreSQL).

## Content versions

Every session stores `content_id`, `content_version` and `content_hash`.

* A server loads a save only if `compatible_from ≤ save version ≤ content_version` (semver
  from `manifest.yaml`); otherwise `422 INVALID_REQUEST` `content_version_mismatch`
  (non-recoverable, with both versions). Content is never silently swapped under a save.
* **Strategy for content changes.** Patch/minor versions are additive (new missions, objects,
  insights; ids never removed or renamed) and keep `compatible_from` — existing saves load and
  simply see the new content. A breaking content change (removing/renaming ids, changing the
  meaning of a stored field) bumps the major version and raises `compatible_from`; it ships with
  a migration that rewrites stored `TimelineGameState`/`CampaignMeta` documents (both carry
  `schema_version`) in an Alembic data migration, so old saves are upgraded explicitly or
  rejected — never misread.
* The simulation scenario of each timeline is pinned by content hash (`mission_scenarios`), so a
  scenario change never alters an existing timeline's physics (the v1 replay guarantee).
