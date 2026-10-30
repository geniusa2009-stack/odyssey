# Testing

Three layers, clearly separated by what has actually been run.

| Layer | Runs | Status at this checkpoint |
|---|---|---|
| 1. Native protocol tests (fixtures) | `make -C Tools/ProtocolCore test` (clang++, UE-like flags) and `test-asan` (g++, ASan+UBSan) | **run: 22/22 cases, 606 checks pass** (both builds) |
| 2. Live contract harness (real backend) | `ODYSSEY_BACKEND=../odyssey Tools/ProtocolCore/run_live.sh` | **run: 51/51 checks pass** (backend 4f7be83) |
| 3. Unreal automation tests | `Automation RunTests Odyssey` | **UNREAL_EDITOR_VERIFICATION_REQUIRED** — written, never run |

## 1. Native protocol tests

`Plugins/OdysseyAPI/Source/OdysseyAPI/Private/Tests/ProtocolTestCases.h` holds the test bodies;
`Tools/ProtocolCore/run_tests.cpp` runs them natively, `OdysseyAPIAutomationTests.cpp` runs the
**same bodies** as `Odyssey.Protocol.<Case>` in Unreal.

Build flags mirror Unreal module code: `-std=c++20 -fno-exceptions -fno-rtti -Wall -Wextra
-Wshadow -Werror` (also clean under `-Wundef -Wimplicit-fallthrough -Wshorten-64-to-32`). The
runner defines Unreal's `check/checkf/verify/ensure/TEXT` macros first, so a name collision in the
shared headers fails natively instead of only inside Unreal.

| Case | Covers (§29 / §30) |
|---|---|
| JsonRoundTripOfEveryFixture | all recorded fixtures parse/serialize losslessly; int64, unicode |
| ProtocolGuard / BackendProtocolMismatchFailsStartup | **backend protocol mismatch**, missing slice action → fatal, nothing else sent |
| UuidV4 | id generation |
| CommandSerializationMatchesTheContract | **command serialization** == recorded `command_request.json` (+ protocol/actor) |
| ClosedSchemaCompatibility | **closed schema compatibility**: emitted bodies validate against `GameCommandRequest`, `RestoreRequest`, `CreateGameSessionRequest`; recorded responses against their schemas; WS frames against the exported realtime schema; every field the client reads is declared |
| EveryRequestMatchesTheOpenApiDocument | every request the machine can emit targets a declared operation, with declared query params, required headers, valid body, correct auth |
| IntentValidation | local rejection of malformed intents |
| StateVersionHandling | **state version** from the recorded command response; never lowered by older events; next command uses it |
| IdempotencyRetryKeepsTheKey | **idempotency retry**: timeout/5xx/429 → identical bytes + same key; replayed answer resolves once; next intent gets a new key |
| EventOrderingAndDuplicates / MachineHandlesDuplicateAndOutOfOrderFrames | **event ordering**, **duplicate rejection**, foreign session/protocol, hold bound, REST gap fetch |
| ResumeCursor | **resume cursor**: restore with cursor, reconnect from the restored cursor |
| StaleStateReconciliation | **stale-state reconciliation**: refresh first, resubmit once with new ids if still offered, else superseded; debug-forced stale |
| RestoreMapping / ResyncRequiredTriggersRestore | **restore mapping** (recorded restore → LUNA-01 state, cursor 69); 404 stored session → new campaign; RESYNC → restore with retries |
| MirrorAppliesRecordedEvents | incident, inventory, mission, certification fixtures; transition → snapshot; unknown types; `snapshot_required` |
| InteractionsFromBackendAndObjectRefresh | availability/reasons only from the backend, object refresh |
| ClockSyncWhileTheClockRuns | sync cadence = one per tick (rate budget) |
| SemanticRegistry | **semantic id mapping** + **unknown semantic id handling** against the generated registry and the real bootstrap |
| FutureLensAndBlackBoxIngestion | Future Lens (known-only) and Black Box (edges resolve) fixtures |
| BackoffBounds | reconnect backoff bounds |

## 2. Live contract harness

`Tools/ProtocolCore/live_harness.cpp` executes the same `SessionMachine` over a minimal POSIX
HTTP/1.1 + WebSocket client (handshake key verified with SHA-1) against a **real backend process**
started by `run_live.sh` (uvicorn, SQLite in a temp dir, in-memory bus, mock AI; no secrets). It
plays the Earth Command slice end to end and compares the mirror with a fresh authoritative
snapshot after every step (`odyssey::DiffMirrors`).

| Step | Fault injected | Verified |
|---|---|---|
| 1 startup | — | ready → features → create → snapshot → WS; registry covers every id |
| 2 zone entry | **REST timeout** after the server applied the command | same key resent, `Idempotent-Replayed: true`, applied once |
| 3 incident | **duplicate + out-of-order** frames for the whole incident | incident arrives, duplicates dropped, mirror == server (incl. resource values while paused) |
| 4 inspect | **stale state** forced | `STALE_STATE` → snapshot → resubmitted with new ids → applied |
| 5 resolve | — | training load shed, repair, clock ACCELERATED |
| 6 Future Lens | — | known-only projection parsed |
| 7 socket | **WebSocket disconnect** | Recovering → restore → Ready; incident resolves in trusted time |
| 8 server | **backend process stopped 4 s and restarted** (same DB) | Recovering while down → Ready → mirror == server |
| 9 LUNA-01 | — | inspections, module install, cargo, charging, **authorization**, campaign → LUNA-01 |
| 10 Black Box | — | causal graph parsed, edges resolve |
| 11 second client | **client restart** from persisted credentials | same campaign, same state |

Also asserted: zero `429 Too Many Requests` (measured 82–100 requests/min).

## 3. Unreal automation (to run on the UE 5.8 machine)

```
UnrealEditor-Cmd <path>/Odyssey.uproject -ExecCmds="Automation RunTests Odyssey; Quit" \
  -unattended -nullrhi -nosplash -log -ReportExportPath=<dir>
```

* `Odyssey.Protocol.*` — the 22 shared cases inside Unreal (proves the core compiles and behaves
  identically under UE's toolchain, allocator and macros).
* `Odyssey.Semantic.RegistryImport` — imports the registry JSON through Unreal's DataTable importer
  into `FOdysseySemanticIdRow`, round-trips it into the core registry, checks the real bootstrap.

## Development fault controls (in game, non-Shipping)

`Odyssey.Net.LoseCommandResponse [n]`, `Odyssey.Net.DropRealtime`, `Odyssey.Net.Scramble 0|1`,
`Odyssey.Net.ForceStale`, `Odyssey.Net.Restore`, `Odyssey.Net.VerifyMirror`,
`Odyssey.Session.Forget`, `Odyssey.Debug.Overlay 0|1`, `Odyssey.Act <action> [target|-] [k=v…]`. Server restart = restart the backend
process. All are UNREAL_EDITOR_VERIFICATION_REQUIRED; their protocol effect is what the live
harness exercises.

## Contract integrity

```
python3 Tools/Contract/sync_fixtures.py --check                     # vendored fixtures untouched
python3 Tools/Contract/sync_fixtures.py --backend ../odyssey --check   # still equal to the backend
../odyssey/.venv/bin/python Tools/SemanticIds/generate_registry.py --backend ../odyssey --check
../odyssey/.venv/bin/python Tools/Contract/export_realtime_schema.py --backend ../odyssey --check
```
