# Unreal Handoff

For the Unreal Engine 5.8 team integrating the ODYSSEY backend. The protocol reference is
[UNREAL_BACKEND_CONTRACT.md](UNREAL_BACKEND_CONTRACT.md); recorded example payloads are in
`tests/fixtures/game/examples/` (real server output, validated against the schemas — start
with `index.json`).

## 1. Who owns what

**Unreal owns** everything you can see, hear or touch: movement, camera, animation, collision,
physics, rover driving, VFX, audio, locomotion, pathfinding, Smart Objects, StateTrees,
rendering, transitions, cinematics, spawn transforms, how and when crew cues are performed.

**The backend owns** what is *true*: the mission, the simulation, time, consequences,
objectives, incidents, inventories and cargo mass, modules and compatibility, infrastructure,
discoveries, knowledge, capabilities and certifications, campaign progression, Mars readiness,
Future Lens, Black Box, Rewind, saves.

Never compute a consequence locally and tell the backend. Ask for the action; render what the
backend answers.

## 2. Bootstrap

```
POST /api/game/v1/sessions {"display_name": "Commander"}
→ 201 {"session_token": "gst_…", "bootstrap": {"features": …, "snapshot": …}}
```

Store the token securely (it is shown once; it is the only credential for the session). Build
the world from `snapshot`: map every semantic id (`world.locations[].id`,
`world.objects[].id`, containers, crew) to your actors/anchors; spawn the player at the anchor
for `world.player_location`. `features.actions` tells you every action and parameter the server
understands; each object's `interactions[]` says which apply to it right now and why not.

Returning player: `POST /sessions/{id}/restore {"last_seq": <last applied>}` — never rebuild from
local state.

## 3. Sending semantic actions

Send an action when something *meaningful* happens — the player walks into the engineering bay
(`world.zone_entered`), presses the breaker panel (`repair.perform`), drags a water tank into the
cargo hold (`cargo.transfer`), flips the training simulator off (`system.set_mode` + `mode`).

```json
{"protocol": "odyssey.game.v1", "command_id": "<uuid>", "session_id": "gs_…",
 "expected_state_version": 17, "idempotency_key": "<uuid>",
 "action": "cargo.transfer", "target": "earth.command.hangar.luna01.cargo_hold",
 "params": {"item": "cargo.water_tank", "quantity": 1, "from": "earth.command.hangar.storage"}}
```

Play the *intent* animation optimistically if you like, but treat the response as the truth:
`applied` → show the consequence (it is in `events` and the next snapshot), `no_change` → nothing
happened (`reason`), error → roll back the presentation and show the safe `reason`
(`not_at_location`, `container_mass_limit_exceeded`, `fault_not_diagnosed`, …).

## 4. State versions

Every response carries `state_version`. Send the version your decision was based on as
`expected_state_version`. If the world changed in between (the server clock advanced, an
incident started, another device acted) you get **409 STALE_STATE** with the current version.

## 5. Idempotency

Generate a new `command_id` and `idempotency_key` per *intent*. If the network fails and you do
not know whether the command applied, resend the **identical** body: you get the original
response (`Idempotent-Replayed: true`) and nothing happens twice. Never reuse a key for a
different body (`IDEMPOTENCY_KEY_REUSED`).

## 6. Realtime and resume

Open `wss://…/api/game/v1/ws/sessions/{id}?token=…&last_seq=<last applied seq>`. Apply events
in `seq` order; ignore `seq ≤` what you applied. `RESUMED` is followed by the backlog;
`RESYNC_REQUIRED` means call `/restore`. Events with `payload.snapshot_required`
(`mission.transitioned`, `timeline.changed`) mean "reload the snapshot". Send
`{"type":"ping"}` to keep the connection alive. Details:
[GAME_REALTIME_PROTOCOL.md](GAME_REALTIME_PROTOCOL.md).

## 7. Recovering from stale state

1. `GET /snapshot` (or apply the events you were missing).
2. Re-evaluate whether the action still makes sense (the breaker may already be repaired).
3. Resend with the new `expected_state_version`, a **new** `command_id` and a **new**
   `idempotency_key`.

## 8. Restoring a session

`POST /restore {"last_seq": N}` answers: campaign and phase, mission, timeline, semantic
location (and checkpoints), mission and world state, unlocked areas, active incidents, what
happened while disconnected (`while_disconnected`) and the events to replay or
`resync_required`. Then reconnect the socket from `snapshot.session.last_seq`.

## 9. Time

The server owns time. Show `clock.mode`; let the player *request* `PAUSED`, `REALTIME` or
`ACCELERATED` with `mission.clock_set`. `DECISION_PAUSED` means an incident needs the player.
Call `POST /sync` when you need the world to catch up without an action (e.g. while the player
watches a gauge); the server settles the elapsed time.

## 10. Never send every frame

Positions, rotations, velocities, camera, animation state, physics, input — never. No endpoint
accepts them. A typical play session sends a handful of commands per minute.

## 11. Future Lens, Black Box, WHY?

* `POST /future-lens` with up to three candidate actions → per branch: valid/rejection,
  immediate semantic world hints (`object`, `field`, `now` → `after`), resource deltas with
  warning levels, objective deltas, warnings with hours-from-now, risk and confidence, under the
  known-only policy. Render the future your way; the backend never tells you colours or effects.
* `GET /black-box` → causal nodes (decision/trigger/effect/shortfall/cause/moment/outcome with
  simulation time, semantic anchors and counterfactual status) and edges — enough to lay out a
  spatial causal timeline.
* `GET /insights/{id}/why` → the live causes of an unlocked insight.

## 12. Fixture files

| File | Use |
|---|---|
| `create_session_response.json`, `bootstrap.json` | session start |
| `snapshot_incident.json` | a snapshot during the power incident |
| `command_request.json` / `command_response.json` | one semantic action |
| `error_stale_state.json`, `error_action_unavailable.json`, `error_mars_locked.json` | errors |
| `event_*.json` | inventory, incident, mission, certification, transition, mission-end events |
| `future_lens_response.json`, `black_box_response.json`, `black_box_earth_command.json` | analysis |
| `restore_response.json`, `ws_resumed.json`, `ws_resync_required.json` | reconnect |
| `capabilities.json`, `readiness_mars.json`, `expansion_map.json`, `vehicle_luna01.json`, `why_insight.json`, `features.json` | progression and detail |

They are regenerated by `python -m app.tools.game_contract --write` and checked in CI with
`--check`; ids in them are deterministic placeholders (`gs_aaaa…`) — real ids are random.

## 13. Known limitations (Phase 5)

* Auth is a per-session bearer token with an anonymous principal; there are no accounts.
* One controllable actor (the commander); no multiplayer authority rules yet.
* Only Earth Command and LUNA-01 are playable; later phases are gated structure.
* Black Box shortfalls and outcome analysis exist once a simulation has concluded (LUNA-01);
  Earth Command ends by authorization, so its Black Box lists key moments only.
