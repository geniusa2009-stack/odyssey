# Game Realtime Protocol (`odyssey.game.v1`)

Server → client WebSocket at **`/api/game/v1/ws/sessions/{session_id}?token=gst_…[&last_seq=N]`**
(an `Authorization: Bearer` header also works and is preferred — Unreal's WebSockets module can
set handshake headers; `?token=` exists for clients that cannot, and is redacted from server
logs). Commands never go over the socket: REST is the single write path. Implementation: `app/game/api/ws.py`, `app/game/realtime/`.

## Event envelope

```json
{"protocol": "odyssey.game.v1",
 "event_id": "gs_…:42", "seq": 42,
 "session_id": "gs_…", "timeline_id": "gt_…",
 "state_version": 17, "prev_state_version": 16,
 "type": "incident.started", "scope": "mission",
 "sim_tick": 5, "sim_time_hours": 1.25,
 "server_time": "2026-10-27T06:00:00+00:00",
 "payload": {"incident": "earth.command.power_incident", "stage": "active", "…": "…"}}
```

* `seq` is per session, **gap-free and strictly increasing** across timelines and missions.
* `state_version` is the session version after the turn that produced the event
  (`prev_state_version` before it). Informational events (`future_lens.ready`) have
  `state_version == prev_state_version`: they change no authoritative state.
* `scope`: `world`, `mission`, `crew`, `campaign`, `session`.
* Payloads are small deltas with semantic ids. Events are **derived** from the before/after
  public state of a turn (`realtime/derive.py`), so an event can never reveal anything the
  snapshot would not.

## Event types

| Type | When |
|---|---|
| `clock.updated` | mode/rate/pause reason changed |
| `time.advanced` | the server clock advanced the simulation (from/to tick) |
| `mission.updated`, `objective.updated` | mission status/tier, objective status |
| `resource.threshold_changed`, `system.alert_changed` | alert raised/cleared (resource vs system) |
| `system.state_changed`, `infrastructure.changed` | object status/power/mode/modules changed (infrastructure objects; persistent records use scope `campaign` + `persistent: true`) |
| `world.access_changed`, `world.object_revealed`, `interactions.changed` | access, newly known objects, availability of interactions |
| `incident.started`, `incident.updated`, `incident.resolved` | incident lifecycle (never before it starts) |
| `inventory.changed`, `cargo.changed` | container contents (player kit/storage vs vehicle cargo) |
| `crew.updated`, `crew.cue` | crew intent/location, a fired cue (speaker, cue id, priority, line) |
| `discovery.recorded`, `knowledge.unlocked` | discovery, insight |
| `capability.progressed`, `certification.granted`, `campaign.updated` | campaign progression |
| `mission.transitioned` | mission ended and the next one started (`snapshot_required: true`) |
| `timeline.changed` | rewind activated a new timeline (`snapshot_required: true`) |
| `checkpoint.saved` | manual save |
| `future_lens.ready` | a projection finished (informational) |
| `black_box.ready` | a mission ended; its Black Box is available |

Clients must ignore unknown types (new types are additive).

## Control frames

```json
{"protocol": "odyssey.game.v1", "type": "RESUMED", "session_id": "gs_…",
 "state_version": 17, "last_seq": 42, "replayed": 3, "reason": null,
 "restore_path": "/api/game/v1/sessions/gs_…/restore"}
```

| Type | Meaning |
|---|---|
| `CONNECTED` | no `last_seq` sent: current `state_version`/`last_seq`; load the snapshot (or `/restore`) |
| `RESUMED` | `replayed` retained events follow, in order, right after this frame |
| `RESYNC_REQUIRED` | `reason` `events_expired` (retention passed, or position unknown/ahead) or `backlog_too_large`: call `restore_path` |
| `PONG` | answer to `{"type": "ping"}` |

## Connection sequence

1. The server validates the session id format, the `Origin` (when CORS origins are configured)
   and the token — any failure closes with **1008** (policy violation) before accepting.
2. It **subscribes to the session channel before reading** the database, so nothing committed
   during the handshake can be missed.
3. It sends `CONNECTED`, or `RESUMED` + backlog, or `RESYNC_REQUIRED`.
4. Live events follow strictly in `seq` order: duplicates (already sent from the backlog) are
   dropped; a **gap** (a message the bus lost, e.g. a slow consumer or a Redis hiccup) is
   back-filled from the database; if the missing events have expired the server sends
   `RESYNC_REQUIRED`. Clients therefore see every `seq` exactly once (tested with a lossy bus).
5. The only client frame understood is `{"type": "ping"}`; anything else (including attempted
   commands) is ignored — a socket can never mutate state.

## Delivery and fan-out

Events are written to `game_events` **in the same transaction** as the state change and
published after commit. The database is the source of truth; publishing is best effort.
`InMemoryGameBus` (single process, zero infrastructure) or `RedisGameBus` (pub/sub channel
`odyssey:game:<session_id>`) when `ODYSSEY_REDIS_URL` is set — required when running more than
one API process. Retention: the last 2,000 events per session (`GameRuntime.event_retention`).

## Client algorithm

```
on start/reconnect:   POST /restore {last_seq}  → snapshot, missed events or resync_required
                      open WS ?last_seq=<snapshot.session.last_seq>
on event e:           if e.seq <= applied: ignore
                      if e.seq == applied + 1: apply, applied = e.seq
                      (gaps cannot happen on one socket; if one ever did: /restore)
                      if payload.snapshot_required: GET /snapshot
on RESYNC_REQUIRED:   POST /restore
on command 409 STALE_STATE: GET /snapshot (or apply pending events), re-decide, resend with
                      new command_id + idempotency_key
```

## Never on the socket

Per-frame data, transforms, hidden incidents or schedules, unfired unforeseeable events, seeds,
simulation/ledger ids, presentation directives.
