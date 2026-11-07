# ODYSSEY-GAME — Architecture (Phase 6 scaffold)

> **Status.** This repository is the Phase 6 *integration scaffold*. Everything marked
> `UNREAL_EDITOR_VERIFICATION_REQUIRED` has **not** been compiled, loaded or run in Unreal Engine
> 5.8. The engine-independent protocol core **has** been verified natively and against a live
> backend (see [TESTING.md](TESTING.md) and [STATUS.md](STATUS.md)). No Blueprint assets, maps,
> binaries, screenshots or automation results are included or claimed.

## The loop this project exists to prove

```
Unreal world ──(physical action)──▶ semantic intent ──REST──▶ ODYSSEY backend (authoritative)
      ▲                                                            │ validates, simulates
      │                                                            ▼
 presentation ◀── typed event router ◀── local mirror ◀── realtime events / snapshot
```

Unreal owns everything physical (movement, camera, animation, physics, lighting). The backend owns
every game truth (mission, incidents, legal actions, resources, consequences, time, progression).
Only *semantic* information crosses the boundary: ids such as `earth.command.engineering`, actions
such as `repair.perform`. Never transforms, never per-frame data.

## Repositories

| Repository | Role |
|---|---|
| `odyssey` (backend) | `odyssey.game.v1`, protected at `4f7be839a21b054b83d34151c56510fa45ba18a4`. Not modified in Phase 6. |
| `ODYSSEY-GAME` (this) | Unreal Engine 5.8 project. Consumes the backend's recorded contract artifacts (vendored, hashed). |

## Functional core, imperative shell

The single most important design decision: **all protocol behaviour is engine-independent C++**
that performs no I/O, so it can be tested exhaustively without Unreal.

```
Plugins/OdysseyAPI/Source/OdysseyAPI/Public/OdysseyProtocol/   (header-only C++20, no exceptions/RTTI)
  Json.h             exact JSON (int64-preserving, order-insensitive equality)
  Protocol.h         protocol guard, feature check, id validators, UUID v4, error envelope
  Command.h          intent → closed GameCommandRequest, response classification, CommandLedger
  EventSequencer.h   seq ordering, duplicates, bounded hold, gap → restore
  StateMirror.h      read-only mirror; applies events only where they fully describe the change
  SemanticRegistry.h id registry (same JSON as the DataTable)
  SessionMachine.h   startup / commands / realtime / recovery state machine → Effects
  Analysis.h         Future Lens + Black Box models
  MirrorDiff.h       mirror vs authoritative snapshot (tests + debug "verify mirror")
  PresentationRules.h  light intensity as a pure function of backend power/mode/status (+ incident)
  Backoff.h          bounded exponential backoff with deterministic jitter
```

`odyssey::SessionMachine` receives inputs (`Start`, `Submit`, `OnHttpResponse`, `OnWsText`,
`OnWsClosed`, `OnTimer`) and returns `Effects` (HTTP requests, socket open/close/send, timers,
notices, "persist credentials"). Two shells execute those effects:

| Shell | Transport | Status |
|---|---|---|
| `UOdysseyBackendSubsystem` (Unreal) | `FHttpModule`, `IWebSocketsModule`, `FTSTicker`, `USaveGame` | UNREAL_EDITOR_VERIFICATION_REQUIRED |
| `Tools/ProtocolCore/live_harness.cpp` | POSIX sockets (HTTP/1.1 + RFC 6455) | verified against the real backend |

Because both shells drive the same machine, the live harness exercises the exact decision logic
the game ships, against the real server, including a backend process restart.

## Unreal modules

Dependencies point one way only (no cycles):

```
OdysseyAPI (plugin: protocol core + its automation tests)
   └─ OdysseyCore        settings per environment, semantic id types + registry subsystem, logs, string conversion
       └─ OdysseyRealtime  FOdysseyRealtimeConnection (IWebSocket), typed events, UOdysseyEventRouter
           └─ OdysseyBackend  UOdysseyBackendSubsystem (the only network owner), view structs, session save
               ├─ OdysseyWorld        anchors, zones, bindings, world reaction, crew placeholders, world subsystem
               │   └─ OdysseyInteraction  interactable, interactor, power console, system actor
               ├─ OdysseyUI           minimal HUD, ORION presenter, Future Lens / Black Box debug views
               ├─ OdysseyPlayer       character, camera, controller, game mode (spawn at semantic anchor)
               └─ OdysseyDebug        dev-only overlay + network fault controls (not created in Shipping)
```

| Module | Key types |
|---|---|
| OdysseyCore | `UOdysseyBackendSettings`, `FOdysseySemanticId`, `FOdysseySemanticIdRow`, `UOdysseySemanticRegistry` |
| OdysseyRealtime | `FOdysseyRealtimeConnection`, `UOdysseyEventRouter`, `FOdyssey*Event` |
| OdysseyBackend | `UOdysseyBackendSubsystem`, `FOdysseySemanticIntent`, `FOdysseyObjectView` … , `UOdysseySessionSaveGame` |
| OdysseyWorld | `AOdysseySemanticAnchor`, `AOdysseySemanticZone`, `UOdysseySemanticBindingComponent`, `UOdysseyObjectPresentationComponent`, `AOdysseyCrewPlaceholder`, `UOdysseyCrewStateComponent`, `UOdysseyWorldSubsystem` |
| OdysseyInteraction | `UOdysseyInteractableComponent`, `UOdysseyInteractorComponent`, `AOdysseyPowerConsole`, `AOdysseySystemActor` |
| OdysseyUI | `UOdysseyHUDWidget`, `UOdysseyOrionPresenter`, `UOdysseyFutureLensDebugWidget`, `UOdysseyBlackBoxDebugWidget` |
| OdysseyPlayer | `AOdysseyPlayerCharacter`, `AOdysseyPlayerController`, `AOdysseyGameMode` |
| OdysseyDebug | `UOdysseyDebugSubsystem` |

## Data flow for one interaction

1. The player walks to the Engineering power console. `UOdysseyInteractorComponent` (local only)
   focuses its `UOdysseyInteractableComponent`; the HUD shows the prompt.
2. Interact opens the physical panel. Each control shows what the **backend** offers for
   `earth.command.engineering.power_bus_b` (mirror interactions, with safe reasons such as
   `fault_not_diagnosed`).
3. The player presses *DIAGNOSTIC*. `AOdysseyPowerConsole` → `UOdysseyBackendSubsystem::SubmitIntent`
   `{action: system.inspect, target: …power_bus_b}`.
4. The machine builds the closed command (ids, `expected_state_version`, idempotency key) and
   POSTs it. Lost answer → same bytes, same key, again.
5. The response's events go through the sequencer into the mirror; the router broadcasts typed
   events (`OnIncident`, `OnSystemStateChanged`); the machine fetches whatever events do not
   fully describe (object interactions, the player's location → snapshot).
6. `UOdysseyObjectPresentationComponent` reads the new object view: lights dim, the warning light
   comes on, the Blueprint hook drives materials/audio. The console re-renders its controls.

## Verification map

Seven areas — Observation Deck, Main Corridor, Mission Control, Engineering, Training,
Laboratory, Hangar Entrance — defined as data in
`Content/Systems/Greybox/L_EarthCommand_Slice.layout.json` (see
[EARTH_COMMAND_GREYBOX.md](EARTH_COMMAND_GREYBOX.md)). Both backend-accepted power-incident
strategies are physically playable in it.

## Non-goals in Phase 6

No Moon, no Mars, no final art, no MetaHumans, no final Future Lens visuals or Black Box room, no
LLM-driven game truth, no movement/transform streaming of any kind.
