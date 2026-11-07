# Realtime

Verified natively (fixtures) and live (real backend, fault injection). The Unreal transport
(`FOdysseyRealtimeConnection` over `IWebSocket`) is UNREAL_EDITOR_VERIFICATION_REQUIRED.

## Connection

`ws(s)://<server>/api/game/v1/ws/sessions/{id}?last_seq=<cursor>` with
`Authorization: Bearer <token>`; no `Origin` header (the backend checks Origin only when sent).
The socket is opened only after a snapshot has been applied, so the client never assumes the
bootstrap is current: the server resumes from the snapshot's `last_seq`.

| Frame | Client |
|---|---|
| `RESUMED` (+ backlog events) | Ready; backlog flows through the sequencer |
| `CONNECTED` | Ready; if its `last_seq` is ahead of the cursor, fetch the gap over REST |
| `RESYNC_REQUIRED` | close, `POST /restore`, reconnect |
| `PONG` | ignored (answer to the 20 s `{"type":"ping"}`) |
| event envelope | sequencer → mirror → router |

The frame schema is exported from the backend models into
`Tests/Schemas/odyssey.game.v1/realtime-frames.schema.json` (OpenAPI has no WebSocket model).

## Ordering, duplicates, gaps (`odyssey::EventSequencer`)

* Applied cursor = last contiguous `seq`. `seq ≤ cursor` → duplicate, dropped (counted).
* `seq > cursor + 1` → held (bounded: 64). A gap that is not filled within 1 s is fetched with
  `GET /events?after_seq=<cursor>` (pages until `has_more` is false).
* Hold overflow, `resync_required` on the events page → restore.
* Envelopes from another session or protocol are rejected.

Live harness: frames delivered as *b, a, a, b* (swapped and duplicated) for a whole incident —
73–78 duplicates dropped, mirror identical to the server snapshot afterwards.

## Mirror (`odyssey::StateMirror`) — read-only, not authoritative

An event updates the mirror only where its payload fully states the change. Otherwise the mirror
asks for data instead of guessing:

| Event | Mirror |
|---|---|
| `system.state_changed`, `infrastructure.changed` | listed field changes |
| `world.access_changed`, `inventory.changed`, `cargo.changed`, `objective.updated`, `incident.*`, `mission.updated`, `clock.updated`, `crew.updated`, `crew.cue`, `capability.progressed`, `certification.granted`, `discovery.recorded`, `knowledge.unlocked`, `campaign.updated`, `resource.threshold_changed`, `system.alert_changed` | applied from the payload |
| `interactions.changed` | marks objects stale → `GET /objects/{id}` (≤ 6, else snapshot) |
| `world.object_revealed` | object refresh |
| `time.advanced` | tick/hours; resource values refreshed by snapshot (≤ every 5 s) |
| any `payload.snapshot_required: true` (`mission.transitioned`, `timeline.changed`, …) | snapshot |
| envelope on another timeline | snapshot |
| unknown type | ignored and counted (forward compatible) |

After every **applied command** one coalesced snapshot follows, because some authoritative
changes have no event (the player's semantic location and `visited` flags — found live).

## Typed router (`UOdysseyEventRouter`)

Raw JSON never reaches actors. The router runs after the mirror has applied the event and
broadcasts typed structs: `OnSystemStateChanged`, `OnIncident`, `OnAccessChanged`,
`OnInventoryChanged`, `OnObjectiveUpdated`, `OnAlertChanged`, `OnMissionUpdated`,
`OnClockUpdated`, `OnCrewUpdated`, `OnCrewCue`, `OnCapabilityProgressed`,
`OnCertificationGranted`, `OnKnowledge`, `OnFutureLensReady`, `OnBlackBoxReady`,
`OnCheckpointSaved`, `OnInteractionsRefreshed`, `OnSemanticIdsChanged`, `OnSnapshotApplied`.
Payloads carry identity and stated facts; listeners read current values from the mirror views.

## Reconnect / restore

Socket closed for any reason → `POST /restore {last_seq}` → snapshot, missed-event summary
(`while_disconnected`: ticks advanced, event types) → reconnect from the restored cursor.
Backend down → restore retried with backoff until it answers. Live harness: socket killed
mid-incident, and the backend process stopped for 4 s and restarted on the same database —
both recovered and converged to the authoritative snapshot.
