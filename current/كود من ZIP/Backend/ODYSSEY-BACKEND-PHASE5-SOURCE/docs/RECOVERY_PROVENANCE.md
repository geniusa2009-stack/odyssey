# Recovery Provenance (internal)

Internal engineering record. It is **not** part of the public API or gameplay contract.

The original ODYSSEY repository (commits `1606ade`, `9d0b00d`, `43f5e30`, `8a335da`) was lost
with a cloud workspace before it was pushed. The repository was reconstructed in controlled
steps from the Phase 1/2 source archives, the session log of the original work, the delivered
Phase 3 reports and the Phase 4 documentation. The old hashes are **forensic references
only**; no reconstructed commit carries them.

| Phase | Original (reference) | Recovered commit | How |
|---|---|---|---|
| 1 | `1606ade` | `fc3aa0d` | source archive |
| 2 | `9d0b00d` | `770afe7` | source archive; tree identical to the original |
| 3 | `43f5e30` | `7361005` | log replay on Phase 2; identical diffstat; all recorded reports reproduced byte for byte |
| 4 (+ D25) | `8a335da` | `fc50912` | log replay, assembly from later source reads, reconstruction against the recorded tests and docs |
| 4 fidelity pass | — | the commit that adds this document | alignment with the recorded Phase 4 contract (F1–F4, F13, F16 below) |

Gameplay is unaffected by the reconstruction: the strict 500-seed LUNA-01 regression (5,500
missions, 1,301,800 states, 0 invariant violations) reproduces the recorded row hash
`5dd64894d328c167` and summary hash `3c9ca293aa19590c`, and the determinism hashes match.

## Classification

* **CONFIRMED** — identical to recorded original text or recorded original output.
* **RECONSTRUCTED** — rebuilt from fragments of the original read later in the log (line-numbered
  indexes, partial file reads, recorded edits), so structure and names are known but not every
  line.
* **INFERRED** — written to satisfy the recorded tests, documentation and fixture values; names
  and internals not otherwise evidenced are the reconstruction's choice.
* **UNKNOWN** — the original differed in a way the evidence shows but does not describe.

## Phase 4 source

| Element | Status | Evidence / notes |
|---|---|---|
| `app/api/v1/ws.py` | CONFIRMED | full original text; 194/194 lines match a later read |
| `app/core/logging.py`, `app/main.py`, `app/services/idempotency.py`, `app/realtime/bus.py`, migration `0002`, `app/read_models/visibility.py` (D25), `app/tools/api_bench.py` | CONFIRMED | full original text in the log |
| `app/core/errors.py` | CONFIRMED (200 of 201 lines) + RECONSTRUCTED tail | later read of lines 1–200 |
| `app/api/deps.py`, `app/core/config.py`, `app/db/models.py` | RECONSTRUCTED | original fragments + Phase 3 base |
| `app/services/mission_service.py` | RECONSTRUCTED | original fragments; module header ~12 lines shorter than the original |
| `app/services/contract_service.py` | RECONSTRUCTED / INFERRED | class position and several methods confirmed by later reads; resume logic inferred (see F13) |
| `app/read_models/mission.py` | RECONSTRUCTED | class/def index with original line numbers; `outcome_tier`, `build_outcome`, `build_clock`, `build_phase` confirmed; other builders inferred |
| `app/read_models/objectives.py`, `resources.py`, `common.py` | RECONSTRUCTED (largely CONFIRMED) | later reads of most of each file; objectives tier-outlook logic inferred (original imports differ) |
| `app/read_models/analysis.py` | RECONSTRUCTED | class index with line numbers; `BlackBoxView`, `_moment`, the head of `build_black_box_view`, the heads of `build_profile_view` / `build_dna_view` confirmed |
| `app/read_models/bootstrap.py`, `decisions.py` | RECONSTRUCTED | recorded edits (capabilities, phases, tools) + docs |
| `app/read_models/systems.py`, `crew.py`, `radiation.py`, `events.py`, `results.py` | INFERRED | docs and tests; `systems.py` is among the lowest-confidence parts (F8) |
| `app/realtime/contract.py`, `app/schemas/commands.py` | INFERRED | envelope and command fields confirmed by docs/tests; class names of the command schemas inferred |
| `app/api/v1/routes.py` (contract endpoints) | INFERRED; internal gating CONFIRMED | paths, methods, statuses, rate-limit buckets from docs; the `internal` tag and gate on exactly 11 endpoints replayed from the recorded patch; resource-id pattern confirmed |
| `app/api/security.py` | INFERRED | public code `PAYLOAD_TOO_LARGE` (required by tests/docs); clearing the full log context per request |
| `app/ai/context.py` | INFERRED | `extra_facts` / `read_model` source from the confirmed caller |
| `app/tools/openapi_snapshot.py`, `contract_fixtures.py` | INFERRED; fixture docstring/format CONFIRMED in part | recorded diff of the original fixture tool |
| Tests: `test_contract_api`, `test_contract_hidden_information`, `test_contract_concurrency`, `test_read_models`, `test_phase_visibility` | CONFIRMED | full original text |
| Test updates in `test_api`, `test_database`, `test_realtime_security_logging`, `test_auth_seam` | INFERRED (categories CONFIRMED) | categories documented in TESTING.md; the original `test_api.py` was ~0.9 KB larger |
| Docs (`API.md`, `API_CONTRACT.md`, `API_FREEZE_V1.md`, `FRONTEND_HANDOFF.md`, other Phase 4 doc edits) | CONFIRMED | full original text and recorded edits; corrections in this pass are listed under F16 |

## Contract alignment applied in the fidelity pass

| # | Change | Status of the result | Evidence |
|---|---|---|---|
| F1 | Snapshot/bootstrap alerts expose `id` (was `alert_id`). `alert_id` is unchanged in Future Lens warnings and resource alert rules | CONFIRMED name | Phase 5 code written against the original read `id`, `severity` and `category` from `build_alerts(...)` and passed strict mypy; the original class had the same length |
| F2 | `participant_id: str \| None = None` on `DecisionEntryView` (decision results, history, `DECISION_ACCEPTED`, rewind preview, timeline branches) | **INFERRED name**, CONFIRMED presence | the original realtime fixture had exactly one more decision key sorting between `option_id`/`parameters` and `phase` (`"phase"` on line 18); the original class was one line longer. Populated from the decision's recorded participant, `null` otherwise |
| F3 | Future Lens explanation `target_metric` names the quantity a budget margin is the margin of (`crew.projected_dose_margin_msv` → `crew.projected_dose_msv`) when that metric is directly upstream on the explained chain | CONFIRMED output for the recorded scenario; rule INFERRED | the doc example was pasted from the original fixture output. The engine is unchanged: its trace still targets the margin metric, and values and steps are passed through as is |
| F4 | Black Box `key_moments` stay chronological but exclude randomly sampled wear faults (engine `data.random`); designed and state-triggered incidents remain | CONFIRMED output for the recorded scenario; rule INFERRED | the original fixture's first two key moments at tick ≥ 120 were 139 (communication loss) and 159 (resource cascade). Every script consistent with the other recorded Black Box values produces the tick-146 wear fault, which remains in the raw report and causal data |
| F13 | Resume semantics frozen by tests (`tests/test_contract_recovery.py`) | INFERRED behaviour, now frozen | see below |
| F16 | Bootstrap size described with its measurement method | CONFIRMED measurement | the original measured `len(json.dumps(body))` = 50,972 bytes (default separators, not compact) before D25 |

F13, `GET .../events` (and the WebSocket resume that uses the same function):

| Cursor | Result |
|---|---|
| last event of the latest version | empty page |
| mid-group (`last_state_version` + `last_seq`) | the rest of that group, then later groups |
| auxiliary event id (`…:aux:…`) | treated as the end of that version |
| `last_state_version=0` | all retained events |
| `seq` beyond the end of its group | `resync_required`, `events_unavailable` |
| a timeline of another session | `resync_required`, `unknown_timeline` |
| negative `last_state_version` | `422 VALIDATION_ERROR` |
| no cursor | `422 INVALID_REQUEST`, reason `cursor_required` |

## Known remaining differences (accepted)

| # | Area | Status | Description |
|---|---|---|---|
| F5 | Bootstrap size | UNKNOWN (accepted) | Like for like (default separators, D25 changes undone), the recovered bootstrap is ≈ 3.3 KB (6.5 %) smaller than the original 50,972 bytes. Partly explained by F6, F7 and F9; the rest is in reconstructed parts. No speculative fields were added. |
| F6 | `MissionHUD` (also `RESOURCE_CHANGED`) | UNKNOWN (accepted) | The original class was 3 lines longer and `build_hud` 4 lines longer: the recovered HUD may lack 1–3 fields. Restoring fields later would be an additive v1 change. |
| F7 | `CrewMemberStatus` | UNKNOWN (accepted) | The original crew builder was 2 lines longer; possibly one more member field. |
| F8 | Systems view | INFERRED, low confidence | The original `build_systems` began at line 109 (recovered: 169), so the module was organised differently. The per-system field set rests on one documented sentence. Kept as recovered. |
| F9 | Bootstrap `endpoints` map | UNKNOWN (accepted) | The original bootstrap fixture had 3 more lines containing the session id, most likely 3 more endpoint entries, which are not known. |
| F10 | Small class-length differences | UNKNOWN (accepted) | Original longer: `ForkPreviewView` +3 lines, `RewindPointView` +1, `TierBlock` +1, `MissionCompletionView` +1, `EngineeringProfileView` ≈ +2; recovered `RiskDriver` +1. These may be fields or docstrings; nothing was added. |
| F11 | OpenAPI snapshot `tests/fixtures/contract/openapi-v1.json` | the recovered **API v1 baseline** | Not byte-identical to the lost original. CONFIRMED: paths, methods, status codes, the `internal` tag set, the `contract-` tag prefix, rate-limit buckets, request fields and limits, the resource-id pattern, read-model class names. INFERRED: the seven `contract-*` tag names, every operationId (derived from function names), command schema names, schemas of reconstructed views, `/history` default `limit` (500), `last_event_id` max length (128), descriptions and file formatting. Frozen by `test_openapi_schema_is_unchanged`. |
| F12 | Contract fixtures `tests/fixtures/contract/examples/` | the recovered **fixture baseline** | Generated by `app.tools.contract_fixtures` through the production app and builders (never hand-edited). CONFIRMED: seed 42, the script up to tick 123 (decision ids `dec_hlv7xyiiwzpubrgsagyj` and `dec_jzy5ztbgtpofvweqqw4w`, timeline `…0004`), the radiation, Future Lens, Black Box, decision-option and resource examples, the realtime fixture's first 21 lines, JSON format, timestamp placeholder. INFERRED: the script after tick 123 (advance 1, shelter, advance 12, return to habitat; consistent with every recorded value), the mid-game capture point, hex formatting of ids above 9. |
| — | `/ops/stats` | CONFIRMED behaviour | Listed as INTERNAL in `API_FREEZE_V1.md` and `API.md` but tagged `ops`, not `internal`, in OpenAPI; the original gate patch also left it `ops`. It is always 404 in production. Kept as recovered. |
| F14 | Security / authorisation / WebSocket | as recovered | Internal-endpoint gating, seed hiding, Origin check, close code 1008 and frame limits are confirmed. Unauthenticated `participant_id`, read endpoints and WebSocket are inherited open product decisions, out of scope for the recovery. |
| F15 | Internal implementation details | as recovered | Differences without contract effect (helper imports, fixture-tool layout, objectives tier-outlook implementation) are not imitated. |
