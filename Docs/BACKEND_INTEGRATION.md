# Backend integration — `odyssey.game.v1`

Backend: `odyssey` at `4f7be839a21b054b83d34151c56510fa45ba18a4` (protected; not modified in Phase 6).
Contract source of truth: the backend's recorded artifacts, vendored verbatim into
`Tests/Fixtures/odyssey.game.v1/` with `PROVENANCE.json` (sha256 of every file).

Behaviour below is implemented in `odyssey::SessionMachine` and **verified natively and against a
live backend**. Its Unreal execution in `UOdysseyBackendSubsystem` is
`UNREAL_EDITOR_VERIFICATION_REQUIRED`.

## Configuration

`Config/DefaultGame.ini` → `[/Script/OdysseyCore.OdysseyBackendSettings]` (Project Settings → Game →
ODYSSEY Backend).

| Environment | ServerRoot | Notes |
|---|---|---|
| development | `http://127.0.0.1:8000` | API = `http://127.0.0.1:8000/api/game/v1`; `bAllowInsecureTransport=True` |
| staging | `https://staging.odyssey.invalid` | placeholder (`.invalid` fails loudly until a real host exists) |
| production | `https://api.odyssey.invalid` | placeholder; Shipping builds refuse non-https |

Selection: `-OdysseyEnv=<name>` → `ODYSSEY_ENV` → `DefaultEnvironment`. No secret exists in config:
the only credential is the per-session bearer token the backend issues at runtime.

## Session and token

* Created by `POST /sessions` (`session_token` shown once) or reused from
  `Saved/SaveGames/OdysseySession_<env>.sav` (`UOdysseySessionSaveGame`: session id, token,
  last seq, server root). Credentials are reused only against the same server root.
* Sent as `Authorization: Bearer <token>` on every authorized request **and** on the WebSocket
  handshake (never in the URL, so it does not appear in server access logs).
* Risk (Phase 6): the token is stored unencrypted at rest under `Saved/`. Use the platform keychain
  before any public build.

## Startup

```
GET  /api/v1/ready                      retry with backoff until 200
GET  /api/game/v1/features              protocol == odyssey.game.v1 and all slice actions present,
                                        else ProtocolMismatch (fatal: nothing else is sent)
stored credentials?
  yes → POST /sessions/{id}/restore {protocol, last_seq}
        403/404 → SessionReplaced notice, POST /sessions (new campaign)
  no  → POST /sessions {protocol, display_name}
load snapshot → reset sequencer to snapshot.session.last_seq → persist credentials
WS   /api/game/v1/ws/sessions/{id}?last_seq=<cursor>   (Authorization header)
RESUMED/CONNECTED → Ready
```

Slice actions required by the feature check: `world.zone_entered`, `system.inspect`,
`system.set_mode`, `repair.perform`, `power.reroute`, `mission.clock_set`, `mission.authorize`,
`npc.context_request`.

The player is placed at the Unreal anchor of `snapshot.world.player_location` once, when the
session first becomes ready. The backend never supplies coordinates.

## Commands

Every command is `POST /sessions/{id}/commands` with `Idempotency-Key` header = body key:

```json
{"protocol":"odyssey.game.v1","command_id":"<uuid v4>","session_id":"gs_…","timeline_id":"gt_…",
 "expected_state_version":7,"idempotency_key":"<uuid v4>","action":"system.inspect",
 "actor":"commander","target":"earth.command.engineering.power_bus_b","params":{},
 "anchor":"Sys_PowerBusB"}
```

Validated in tests against the closed `GameCommandRequest` schema of the frozen OpenAPI document.

| Situation | Client behaviour |
|---|---|
| one intent at a time | further intents queue (max 8); a new key is created only when the previous command resolved |
| timeout / connection error / 5xx / 429 | resend the **identical bytes** with the **same** key after backoff; the server answers once (`Idempotent-Replayed: true`) |
| 200 `applied` | apply response events through the sequencer; **then one coalesced snapshot** (see findings) |
| 200 `no_change` | apply events, no snapshot |
| 409 `STALE_STATE` | never retried blindly: GET snapshot (at least the version the error reports) → if the backend still offers the action for the target, re-submit **once** with **new** ids and the new version; else `superseded` |
| `DECISION_UNAVAILABLE` / `INVALID_REQUEST` / `NOT_FOUND` (e.g. reason `not_at_location`) | resolved `rejected` with the backend's safe code/reason; presentation shows it |
| `MISSION_COMPLETE` | resolved `mission_complete`; snapshot |
| `VALIDATION_ERROR` / `IDEMPOTENCY_KEY_REUSED` / non-envelope 4xx | resolved `client_bug` (contract violation; logged, never retried) |
| `PERMISSION_DENIED` / `SESSION_NOT_FOUND` mid-session | `SessionInvalid` — needs the player's decision; no silent new campaign |

## Time

The server owns time. While `clock.mode` is `REALTIME` or `ACCELERATED` the client settles the
clock with `POST /sessions/{id}/sync` **once per simulation tick** (`1/ticks_per_second`, clamped
to 1–5 s: REALTIME 0.2 tick/s → 5 s, ACCELERATED 0.8 tick/s → 1.25 s). No sync while paused,
while a command is in flight, or while recovering.

## Recovery

| Trigger | Action |
|---|---|
| WebSocket closed (any code) | `POST /restore {last_seq: cursor}` → snapshot → reconnect WS from the restored cursor |
| `RESYNC_REQUIRED` frame | same |
| sequence gap not filled within 1 s | `GET /events?after_seq=<cursor>` |
| gap beyond the 64-event hold | restore |
| restore fails (server down) | retry with backoff (0.5 s → 15 s, ±20 % jitter); never gives up silently |

Restore is the single reconnect path, as the backend handoff specifies.

## Request budget

The backend rate-limits each client to `ODYSSEY_RATE_LIMIT_PER_MINUTE` (default **120/min**, shared
by all default-bucket endpoints; Future Lens/Black Box use the 20/min expensive bucket). Measured
in the live harness, which plays far faster than a human (19 commands in ~50 s, ACCELERATED clock):
82–100 requests/min across three runs, zero 429s. Contributors: clock sync ≤ 48/min (ACCELERATED), one snapshot per
applied command, resource refresh ≤ 12/min (skipped when a snapshot already arrived),
object refreshes after `interactions.changed` (≤ 6, else one snapshot).

## Integration findings (verified against the live backend)

1. **No realtime event carries the player's semantic location or `visited` flags.** After an
   applied `world.zone_entered` the recorded events are `clock.updated` + `interactions.changed`
   only. The first live run showed the mirror keeping `observation_deck`. Resolution (client
   side, no backend change): one coalesced snapshot after every applied command. This is not a
   protocol contradiction — the snapshot is authoritative for anything events do not describe.
2. **WebSocket frames are not part of the OpenAPI document** (OpenAPI has no WebSocket model).
   `Tools/Contract/export_realtime_schema.py` exports the backend's own pydantic models
   (`GameControlFrame`, `GameEventEnvelope`) into `Tests/Schemas/odyssey.game.v1/` so frames are
   validated with the same closed-schema validator.
3. **`payload.snapshot_required`** is honoured generically (any event type), as the realtime
   protocol document specifies, not only for `mission.transitioned` / `timeline.changed`.
4. **Load-shedding strategy needs rooms outside the specified greybox.** The backend accepts two
   incident strategies; "shed training/laboratory loads first" requires `earth.command.training`
   and `earth.command.laboratory`, which are not among the five Phase 6 areas. "Repair at once"
   works within them (at a station-stability cost). See [EARTH_COMMAND_GREYBOX.md](EARTH_COMMAND_GREYBOX.md).
5. Request rate stays under the default limit (above), but there is little headroom if the client
   added more periodic reads.

No backend change was needed or made.

## What the client never sends

Positions, rotations, velocities, camera, animation state, physics, input, or anything per frame.
The only periodic request is the clock settlement above.

## OpenAPI code generation

Evaluated with the real document; not adopted. See [PROTOCOL_GENERATION.md](PROTOCOL_GENERATION.md).
