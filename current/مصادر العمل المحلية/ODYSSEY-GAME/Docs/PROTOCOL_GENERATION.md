# OpenAPI code generation — evaluation (§31)

**Decision: not adopted.** A small maintained adapter (`Plugins/OdysseyAPI/…/OdysseyProtocol/`)
plus schema-driven tests against the frozen OpenAPI document is clearer, type-safer and easier to
debug for this contract.

## What was evaluated

`openapi-generator` 7.14.0, generator `cpp-ue4` (the Unreal-specific one), run against the real
`Tests/Fixtures/odyssey.game.v1/openapi-game-v1.json` (backend 4f7be83). Output: 113 headers +
113 sources, ~17,000 lines, module `OdysseyGenerated`. Not committed.

## Findings from the generated code

| Concern | Generated `cpp-ue4` | Maintained adapter |
|---|---|---|
| Command params `anyOf[string, integer]` | **`OpenAPIParamsValue` is an empty class**: `system.set_mode {mode: "off"}` and `cargo.transfer {quantity: 2}` cannot be expressed | `ParamValue` (string or int64), serialized with the JSON type the schema requires |
| `seq`, `state_version`, `sim_tick` | `int32` | `int64` |
| Event payloads | `TMap<FString, TSharedPtr<FJsonValue>>` (151 untyped `FJsonValue` uses) — every consumer would parse JSON | mirror applies typed fields; router emits typed structs |
| WebSocket frames | not generated (OpenAPI has no WebSocket model) | sequencer + exported frame schema |
| Closed schemas (`additionalProperties: false`), `pattern`, `const` | not enforced on read; unknown fields silently accepted | tests validate every emitted body and recorded response against the closed schemas |
| Idempotency retry, stale reconciliation, restore | out of scope of a generator | `SessionMachine`, tested |
| Blueprint exposure | plain C++ classes (no `USTRUCT`) | `USTRUCT` views in `OdysseyBackendTypes.h` |
| OpenAPI 3.1 | generator support "still in beta" (warns) | n/a |
| Testability without Unreal | generated code depends on UE `Json`/`HTTP` modules | engine-independent, natively tested |

## What *is* taken from the schema

* The frozen OpenAPI document and the backend-exported realtime frame schema are the reference
  for the adapter's types and the oracle in `ClosedSchemaCompatibility` and
  `EveryRequestMatchesTheOpenApiDocument`.
* A contract change on the backend shows up as a failing native test (fixtures are hash-pinned).

Re-evaluate if the contract grows far beyond the slice (dozens of new request types), or if a
generator gains correct `anyOf` and 64-bit integer support.
