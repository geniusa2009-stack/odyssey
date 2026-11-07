# Testing

```bash
uv run pytest                     # everything available (infra-gated tests skip cleanly)
uv run pytest -m "not perf"       # skip performance sanity checks
uv run pytest -m perf -s          # print performance numbers
```

PostgreSQL and Redis tests run when these are set (otherwise they are **skipped**, never
failed):

```bash
export ODYSSEY_TEST_POSTGRES_URL=postgresql+asyncpg://USER:REDACTED_SECRET@localhost:5432/odyssey_test
export ODYSSEY_TEST_REDIS_URL=redis://localhost:6379/15
```

The PostgreSQL tests **drop and recreate the `public` schema** of that database: point them at
a throwaway test database only.

## Results at the time of writing

| Run | Passed | Failed | Skipped |
|---|---|---|---|
| With PostgreSQL 16 + Redis 7 | 911 | 0 | 0 |
| Without infrastructure | 896 | 0 | 15 |
| PostgreSQL / Redis marker tests only | 8 | 0 | 0 |
| Phase 4 contract suite (5 files, with PostgreSQL) | 134 | 0 | 0 |
| Phase 5 game suite (`tests/test_game_*.py`, with PostgreSQL + Redis) | 230 | 0 | 0 |

Phase 1 ended at 328. Phase 2 added 128: 114 in six new files (below) and 14 in
`test_architecture.py`, which is parametrised over every simulation module and so grew with the
new Balancing Lab and invariant modules. Phase 3 added 84: 79 in six new files (below), 4 in
`test_architecture.py` (new simulation modules) and 1 in `test_balancing_lab.py`. Phase 4 added
134 in five new files (below); the 3 additional skips without infrastructure are the PostgreSQL
variants of the concurrency tests. Phase 5 added 230 tests in thirteen `test_game_*.py` files
(below; 681 → 911); the 6 additional skips without infrastructure are the PostgreSQL variants
of the game concurrency tests and the two Redis game realtime tests.

## What is covered

| Spec requirement | Where |
|---|---|
| Simulation determinism | `test_engine.py::TestDeterminism`: same seed → same hashes; fresh engines agree; step-by-step = advance; split = whole; JSON round-trip; **property test** over random decision sequences |
| Seeded randomness | `test_canonical_and_rng.py`: purity, range, independence of streams/ticks/seeds, distribution, **pinned reference values** |
| Resource calculations | `test_systems.py`: each system's documented equation checked against hand-computed values (generation, priority load shedding, battery efficiency/limits/capacity, rover transfer, thermal, consumption, cold-degraded recovery, electrolysis, scrubber floor, shielding, health, comms, wear) |
| System dependencies | `test_dependencies_and_alerts.py::TestDependencyGraph`: spec chain exists edge by edge, nodes are metrics, roots, acyclic |
| Cascade propagation | `TestCascades`: unit cascade warning + end-to-end "no sun → battery → load shed → CO₂ → crew" |
| Mission events | `test_systems.py::TestEvents`: scheduled, state-triggered, random (seeded), decision-triggered, modifiers/expiry; `test_engine.py`: suppression |
| Decision ledger | `test_ledger_replay_timeline.py::TestLedger`: all fields, frozen records, deterministic ids, chain verification, 5 kinds of tampering detected |
| Future Lens isolation | `test_future_lens.py::TestIsolation`: full-state equality before/after, mutating results, **property test** over horizons/samples; `test_api.py`: state hash unchanged and ledger untouched via HTTP |
| Future Lens determinism | `TestDeterminism`: identical output across engine instances; request hash |
| Timeline reconstruction | `TestReplay`, `test_black_box_and_profile.py::TestReconstruction`, API `verify` |
| Black Box causal trace | `TestBlackBox`: exact decision → control → CO₂ → crew chain, counterfactual verdict, causes precede effects, edges follow the graph |
| Rewind branching / timeline immutability | `TestTimelines` + `test_api.py::TestRewind`: parent ledger and head unchanged, nested forks, both timelines verify |
| Engineering profile determinism | `TestProfile`: deterministic, bounded, weights as data |
| Mission DNA determinism | `TestMissionDNA`: format, determinism, no ids/seed leaked, same play on another timeline → same code |
| Database models | `test_database.py`: create_all, idempotent reference sync, ORM guard, SQLite triggers, PostgreSQL trigger + retention override |
| Migration validity | `test_database.py`: upgrade → `alembic check` (no drift) → downgrade → upgrade on SQLite **and** PostgreSQL; offline SQL generation |
| API validation | `test_api.py::TestValidation`: malformed bodies, unknown fields, nested metadata, path injection, payload size, seed bounds; structured error shape everywhere |
| API mission lifecycle | `TestLifecycle` + PostgreSQL lifecycle with migrations |
| ORION mock behaviour | `test_orion.py`: all topics grounded, causal chain, unavailable info declared |
| AI never mutating state | `test_orion.py` + API test (state hash unchanged); `test_architecture.py` (no import path to write APIs) |
| NASA provider fallback | `test_nasa_and_evidence.py`: outage → fixture, disabled → fixture, cache hit, DONKI parsing, key never leaked |
| WebSocket / event architecture | in-memory + Redis bus tests; WebSocket snapshot, ping/pong, live updates, rejection codes; realtime through Redis end-to-end |
| Security | rate limits, role policy (403), CORS opt-in, production hides docs/stats, request ids, security headers, secret masking/redaction |
| Architecture rules | `test_architecture.py`: simulation imports only stdlib/pydantic/yaml; AI has no write path; routes don't touch ORM models; no frontend files |

### Added in Phase 2

| File | Tests | What it checks |
|---|---|---|
| `test_invariants_and_fuzz.py` | 16 | State invariant checker (valid states pass, 11 kinds of corruption flagged, transition rules); B1 regression; fuzzed decision sequences and parameter perturbations (below) |
| `test_cascades.py` | 35 | Six forced multi-system cascades × 5 checks (expected systems on the chain, acyclic/ordered/declared, cascade warnings match recorded state, stable, counterfactuals match an independent replay) + 5 targeted root-cause regressions |
| `test_black_box_regression.py` | 15 | Seven pinned failure traces (`tests/fixtures/black_box/`), their quality checks, and "an irrelevant decision is not blamed" |
| `test_future_lens_quality.py` | 5 | Determinism and isolation report, confidence falls with horizon, `known_only` blind to an unforeseeable storm, sampling stability, explanation names the candidate |
| `test_balancing_lab.py` | 39 | Overrides, every strategy (completes with invariants, deterministic, cannot read future events), telemetry consistency, replayable decisions, parallel = serial, sensitivity / ablation / impact, detectors, CLI formats, the shipped scenario is never modified, shelter-probe regression |
| `test_auth_seam.py` | 4 | Session isolation, rewind cannot target another session, vandalism is still valid and verifiable play, Future Lens and ORION go through the permission policy |

### Added in Phase 3 (LUNA-01 v0.2.0)

| File | Tests | What it checks |
|---|---|---|
| `test_phase3_outcome_model.py` | 19 | Every objective has a pillar; primary ⇔ required; primary science needs two campaigns; schema rejects mismatches and unknown pillars; outcome tiers driven through the real engine (exceptional / success / partial / mission failed with a safe crew / crew loss); passive play fails with a safe crew; **no single science action gives full success** (each campaign tried alone) |
| `test_phase3_analysis.py` | 13 | Good play ends with a battery reserve; balanced succeeds without emptying the battery; depletion fails the stability pillar; switching oxygen generation off has a consequence; science ambition costs margins; two different strategies both succeed (Pareto); Future Lens shows a different future for major choices and explains every warning a candidate introduces; outcome analysis blames only counterfactually verified decisions and explains a crew-safe failure as an omission; Engineering Profile separates strategies from behaviour; exceptional missions get DNA tag `MX` |
| `test_radiation_information.py` | 13 | Dose limit matches the objective; the dose projection uses no knowledge of future events (identical with or without scheduled space weather) and equals dose + remaining baseline; a ×5 flare is visible as a caution below the warning; the 9 seeds that failed radiation safety in Phase 2 pass with budget-aware sheltering, each with a warning sign first |
| `test_scenario_compat.py` | 10 | Eight missions recorded on commit `9d0b00d` replay **byte-identically** (final state hash and event stream) on the v0.1.0 scenario with the Phase 3 engine; v0.1.0 has no Phase 3 metrics |
| `test_parameter_governance.py` | 8 | Every scenario value linked to numeric evidence still equals it; every such path is EVIDENCE_LOCKED; the balance search refuses locked and protected paths and accepts gameplay ones; the governance document lists them |
| `test_balancing_lab_phase3.py` | 16 | Outcome classes and success rate with the exceptional tier; trajectories (every tick, required columns, CSV/JSON, CLI); decision audit classifies from measured consequences; search refuses protected paths, never modifies the scenario and writes a report; `*` and `*=` overrides; probe hygiene (8): no strategy flips a setting back and forth tick after tick |

Phase 3 also updated existing tests where a deliberate behaviour change required it, each with
a comment: objective and outcome expectations in `test_engine.py`,
`test_dependencies_and_alerts.py` and `test_balancing_lab.py` (v0.2.0 objectives, passive play
now `mission_failed`, battery 240 kWh), the DNA tag pattern, and three regenerated Black Box
fixtures (reasons in [BLACK_BOX.md](BLACK_BOX.md#regression-fixtures-and-their-phase-3-changes)).

### Added in Phase 4 (application contract)

| File | Tests | What it checks |
|---|---|---|
| `test_contract_api.py` | 65 | Bootstrap schema and content (no seed, raw state or scheduling internals); snapshot = authoritative state and recovery after lost events; trends only from recorded states; decision options (availability from the engine, impact classes, parameters); decision commands: valid, invalid (`INVALID_DECISION`), unavailable (`DECISION_UNAVAILABLE`), concluded (`MISSION_COMPLETE`); `409 STALE_STATE` never applied; monotonic versions; idempotent retries (create, decision, advance, branch; key reuse; failures not stored); realtime ordering rules and determinism; `MISSION_COMPLETED`; resume cursors and resync reasons; WebSocket connect, live events, reconnect replay, resync after expiry and timeline change, malformed cursors, ignored client frames; objective outlook (no probabilities); radiation budget; Future Lens (knowledge boundary, state untouched, omniscient off on every endpoint, limits); Black Box (only verified root decisions); rewind (points, preview, branch, parent immutable, tree); Engineering Profile; share-safe and comparable Mission DNA; science claims never present unverified items as verified; **v0.1.0 sessions through the contract** (8 golden missions: same outcomes and objectives, ledger and replay verify); deterministic contract fixtures; **OpenAPI snapshot unchanged**; production hides internal endpoints and seeds; bootstrap query count does not grow with timelines |
| `test_contract_hidden_information.py` | 13 | Snapshot, radiation budget, objectives, decision options and known-only Future Lens are **identical** with and without unforeseeable events after tick t (3 seeds × 3 ticks); power checks: omniscient and raw engine results do differ; unopened science is not listed |
| `test_contract_concurrency.py` | 6 | On SQLite and PostgreSQL: racing decisions on one version (one wins, the rest `STALE_STATE`, ledger verifies); a retry racing its original with one `Idempotency-Key` (applied once, same response for all); racing advances |
| `test_phase_visibility.py` | 30 | D25 phase visibility: the rule on LUNA-01; the same phases are withheld with and without unforeseeable events (so `null` reveals nothing) and under renaming (no name-based rule); a planned milestone does not unmask a hidden-event chapter; unscheduled transitions withhold later phases; `next_phase` at known and withheld transitions; **every frontend-safe REST response** (bootstrap, snapshot, objectives, decision options, radiation, all resources, completion, history, events, timelines, rewind points and preview, Black Box, profile, DNA, Future Lens, capabilities, science, session and mission views) **and every realtime frame** scanned at ticks 0–119 for withheld phase names and not-yet-happened unforeseeable event names; Future Lens engine output unchanged while the view withholds; scenario hash and determinism hash unchanged; science claims redact unforeseeable event ids |
| `test_contract_recovery.py` | 7 | Recovery-fidelity regressions after the repository reconstruction ([RECOVERY_PROVENANCE.md](RECOVERY_PROVENANCE.md)): snapshot/bootstrap alerts expose `id` (`alert_id` kept for Future Lens warnings and resource alert rules); `participant_id` on decision entries (null without a participant; decision results, history, `DECISION_ACCEPTED`, rewind preview and branches); the recorded Future Lens explanation names `crew.projected_dose_msv` while the engine trace is unchanged; Black Box key moments exclude random wear faults (still in the raw report); resume cursors (latest, mid-group, auxiliary, `last_state_version=0`, beyond the group, foreign timeline, negative version, no cursor) |
| `test_read_models.py` | 20 | Static affected-systems map equals the engine; impact classes follow the Phase 3 measurements (D24: maintenance local); option ids round-trip; projections never mutate state; display rounding; no `-0.0`/NaN; closed and immutable models; radiation budget during the storm; event views strip scenario internals |

Phase 4 also updated existing tests where the contract deliberately changed, each with a comment:
the error envelope (`code` → public code, specific code in `reason`) and the 409 status of
unavailable decisions in `test_api.py` / `test_auth_seam.py`, the realtime message shape in
`test_api.py` / `test_realtime_security_logging.py`, the two new tables in `test_database.py`,
and the omniscient switch in `test_auth_seam.py`.

Property-based tests use Hypothesis (profile `odyssey`: 25 examples, no deadline; override
with `HYPOTHESIS_PROFILE`).

### Added in Phase 5 (open-world game backend, `odyssey.game.v1`)

| File | What it checks |
|---|---|
| `test_game_content.py` | Content loads and validates; every cross-reference; bad references fail; incidents never in the client catalog; content hash/version |
| `test_game_domain.py` | Pure core through `InMemoryGame`: Earth Command full flow to LUNA-01, strategies with different costs, incident invisible before it happens, action validation, clock modes/catch-up/decision pause, capability derivation, certification once, Mars lock with missing critical gates, phases cannot be skipped, determinism |
| `test_game_properties.py` | Hypothesis: transfers conserve units and mass; seed-reproducible action-sequence fuzzer (in memory, before and after the mission transition) with inventory/discovery/certification/stage/phase invariants |
| `test_game_api.py` | **Section 53 end-to-end through the production API** (create → bootstrap → engineering → inspect → act → consequence → resolve → inspect LUNA-01 → requirements → authorize → transition → save → disconnect → restart → restore → identical state); strategy costs; token seam; frozen error envelope; client cannot set authoritative values; `STALE_STATE` and recovery; monotonic versions and gap-free seq; read-only actions; idempotent retries, key reuse, duplicate command ids; discovery idempotency; locked/unauthored/Mars-locked starts; progression and detail reads; payload bounds; v1 cannot see game sessions |
| `test_game_concurrency.py` | SQLite **and** PostgreSQL: racing commands on one version (one wins), a retry racing its original (applied once, same response), racing transfers conserve mass, racing syncs never double-advance |
| `test_game_realtime.py` | WebSocket CONNECTED/live order/envelope schema, resume replays exactly the missed events, resync on expiry or unknown position, **lost bus messages back-filled gap-free**, token/id/cursor refusal (1008), ping and ignored client frames, informational events keep the version, Redis fan-out end to end and the Redis bus round trip |
| `test_game_hidden_information.py` | Every client payload (bootstrap, snapshot, events, restore, checkpoints, detail and progression reads, Future Lens, Black Box, DNA/profile, features, catalog, command results) free of hidden incidents/unforeseeable events before they happen, seeds and derived mission seeds, simulation/ledger ids and token hashes; analysis shapes carry no engine internals or presentation directives |
| `test_game_rewind_and_saves.py` | Rewind forks timeline-local state and leaves the campaign identical; rewind errors; rewind cannot duplicate or farm meta progression; bounded auto checkpoints; content-version guard; restore reports what happened while disconnected and never double-advances; unattended cap |
| `test_game_infrastructure.py` | Infrastructure state rules (planned → under construction → operational/degraded/offline/damaged); completion commits persistent records once and inheritance; failure commits nothing and the mission is replayable |
| `test_game_api_fuzz.py` | Seed-reproducible HTTP fuzzing: random valid/invalid actions, duplicate keys, stale commands, time, restore, rewinds, unlock attempts, mission-transition boundary; invariants after every step |
| `test_game_contract.py` | Game OpenAPI snapshot and recorded Unreal examples regenerate identically and validate against the real models; required handoff examples; no internal ids/seeds in examples; every route documents its errors; no spatial fields; API v1 snapshot unchanged |
| `test_game_architecture.py` | Pure game core imports no web/DB/service layers; the simulation never imports the game; only `app/game/api` uses FastAPI; no Unreal/frontend/3D files in the repository |
| `test_game_engine_seam.py` | `engine.advance(stop_when=…)` is observational (chunked advancement equals one advance, LUNA-01 and Earth Command); game-owned simulation sessions are invisible to API v1 and write no v1 realtime rows |

Phase 5 changed one existing test deliberately: `test_database.py` expects the seven new tables.

## Property and fuzz testing

```bash
HYPOTHESIS_PROFILE=fuzz uv run pytest tests/test_invariants_and_fuzz.py tests/test_engine.py tests/test_future_lens.py
```

The `fuzz` profile runs 500 examples per property (the default run uses 25). Properties:

* **Any decision sequence** (valid and invalid decisions, unknown subsystems and components,
  out-of-range values, at random ticks) keeps every state invariant after every tick, is
  deterministic (same hashes on a second run), produces a valid hash chain, replays exactly
  with hash verification, and every fork point reproduces its recorded "state before".
* **Random parameter perturbations** (battery, solar, food, conductance, tick length, fault
  probability, shielding over wide ranges) keep every state valid.
* Engine determinism over random decision sequences and Future Lens isolation over random
  horizons and sample counts (existing properties, also run at 500).

Result of the last fuzz run (2026-10-19, Phase 4 code, LUNA-01 v0.2.0; 75 tests in those three
files, all passed, 398 s):

| Property | Examples passed | Failed | Time |
|---|---|---|---|
| Any decision sequence keeps the engine sound | 500 (64 generated inputs discarded as invalid by the strategy's filters) | 0 | 259 s |
| Parameter perturbations keep states valid | 500 | 0 | 62 s |
| Random decision sequences replay identically | 500 | 0 | 50 s |
| Future Lens isolation for any request | 240 (input space exhausted) | 0 | 23 s |

Phase 3 run (2026-10-12; 399 s):

| Property | Examples passed | Failed | Time |
|---|---|---|---|
| Any decision sequence keeps the engine sound | 500 (79 generated inputs discarded as invalid by the strategy's filters) | 0 | 258 s |
| Parameter perturbations keep states valid | 500 | 0 | 63 s |
| Random decision sequences replay identically | 500 | 0 | 51 s |
| Future Lens isolation for any request | 240 (input space exhausted) | 0 | 24 s |

Phase 2 run (2026-10-07, v0.1.0; 339 s):

| Property | Examples passed | Failed | Time |
|---|---|---|---|
| Any decision sequence keeps the engine sound | 500 (82 generated inputs discarded as invalid by the strategy's filters) | 0 | 221 s |
| Parameter perturbations keep states valid | 500 | 0 | 52 s |
| Random decision sequences replay identically | 500 | 0 | 44 s |
| Future Lens isolation for any request | 240 (input space exhausted) | 0 | 19 s |

The invariant checker found one genuine engine bug (battery charge above the worn battery's
capacity), now fixed with a regression test. Neither fuzz run found anything further. See
[BALANCING_FINDINGS.md](BALANCING_FINDINGS.md#bugs).

The Balancing Lab's `--strict` flag applies the same invariant checker to every tick of a
sweep. Phase 4 regression (2026-10-19) and Phase 3 (v0.2.0), 11 strategies × 500 seeds: 5,500
missions, 1,301,800 states, 0 violations; every mission row identical between the two runs (Phase 2, v0.1.0: 5,000 missions, 1,174,210 states, 0 violations).

## Performance sanity (`tests/test_performance.py`)

Measured in the build workspace (CPython 3.13, in-process, SQLite):

| Measurement | Result | Threshold |
|---|---|---|
| Full 240-tick mission | ≈ 38 ms (0.16 ms/tick) | < 5 ms/tick |
| Future Lens, 5 branches × 4 samples × 48 ticks | ≈ 0.5 s | < 15 s |
| Reconstruct 240 ticks / 22 decisions, hash-verified | ≈ 0.14 s | < 10 s |
| Black Box with counterfactuals (same mission) | ≈ 0.3 s | < 60 s |
| `GET /state` | ≈ 7 ms/read | < 500 ms |
| `POST /advance` (1 tick, incl. commit) | ≈ 12 ms | |

## API performance (Phase 4)

`python -m app.tools.api_bench --repeat 20` drives one deterministic session through the frozen
contract in-process (no network) and counts SQL statements per call. 2-core workspace,
2026-10-19 (`reports/phase4/api-bench-*.json`):

| Endpoint | SQLite median / p95 ms | PostgreSQL median / p95 ms | SQL statements (SQLite / PostgreSQL) |
|---|---|---|---|
| `POST /mission-sessions` | 15.6 / 129.2 | 16.0 / 131.2 | 12 / 11 |
| `GET …/bootstrap` | 27.2 / 75.9 | 25.5 / 72.7 | 7 / 7 |
| `GET …/snapshot` | 24.8 / 40.5 | 25.3 / 38.1 | 5 / 5 |
| `GET …/decision-options` | 21.8 / 29.2 | 22.1 / 23.7 | 4 / 4 |
| `POST …/decision-commands` | 17.6 / 24.4 | 20.5 / 24.3 | 15 / 13 |
| `POST …/advance-commands`, medians for 1 tick / 24 ticks | 14.4 / 27.0 | 15.5 / 26.8 | 10 and 21 / 9 and 10 |
| `GET …/objectives` | 6.8 / 9.9 | 8.0 / 10.9 | 4 / 4 |
| `GET …/radiation-budget` | 7.4 / 9.0 | 8.4 / 10.0 | 4 / 4 |
| `GET …/events` (resume) | 7.8 / 9.4 | 8.0 / 10.3 | 5 / 5 |
| `POST …/future-lens/projections` (1 candidate + baseline, 4 samples, 24 h) | 130.0 / 186.2 | 135.3 / 205.3 | 8 / 8 |
| `GET …/history` | 86.8 / 158.6 | 83.5 / 139.7 | 5 / 5 |
| `GET …/timelines` / `…/rewind-points`, medians | 6.2 / 9.5 | 7.1 / 11.8 | 5 / 5 |
| `GET …/completion` | 8.0 / 11.1 | 8.6 / 14.2 | 4 / 4 |
| `GET …/black-box/summary` | 197.7 / 278.9 | 188.3 / 276.8 | 6 / 6 |
| `GET …/mission-dna/share` / `…/engineering-profile`, medians | 185.1 / 189.5 | 184.7 / 186.7 | 6 / 6 |
| `GET /science/claims` | 3.1 / 4.2 | 3.8 / 6.6 | 1 / 1 |

The p95 of the first request type includes warm-up (engine cache). The Black Box, DNA, profile
and history replay the whole mission by design (hash-verified). No N+1 pattern: the bootstrap
issues the same 7 statements with 1 or 4 timelines (`test_bootstrap_query_count_does_not_grow_with_timelines`).
No cache was added: measurements do not justify one at hackathon scale.

Engine benchmarks re-run in Phase 4 (`reports/phase4/bench.json`) are within ±7 % of Phase 3
(engine 40.5 ms vs 43.1 ms per mission; 1,000 missions on 2 workers 71.0 vs 74.7 ms per
mission): the application layer does not touch the engine's hot path.

## Performance at scale

Phase 3 re-measurement (2026-10-12, LUNA-01 v0.2.0; `reports/phase3/bench.json`): engine 43.1 ms
per 240-tick mission, `balanced` mission 130.8 ms, 1,000 missions on 2 workers 74.7 ms per mission
(13.4 /s), Future Lens default 94.2 ms, Black Box with counterfactuals mean 162 ms / max 461 ms.
The engine difference is the larger scenario: Phase 3 code runs v0.1.0 within noise of Phase 2
code. Details: [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md#invariants-fuzzing-determinism-performance).
The tables below are the Phase 2 measurements (v0.1.0).

Measured with `python -m app.simulation.analysis.balancing bench` on this 2-core workspace
(CPython 3.13). Strategy `balanced`, full 240-tick missions, result rows kept in memory.

| Missions | Workers | Wall time | Per mission | Missions/s | Peak RSS (parent / each worker) | Result rows |
|---|---|---|---|---|---|---|
| 100 | 1 | 12.3 s | 123.3 ms | 8.1 | 75 MB / – | 61 KB |
| 100 | 2 | 7.1 s | 71.0 ms | 14.1 | 75 MB / 54 MB | 70 KB |
| 1,000 | 2 | 65.1 s | 65.1 ms | 15.4 | 75 MB / 54 MB | 659 KB |
| 10,000 | 2 | 647.1 s | 64.7 ms | 15.5 | 100 MB / 55 MB | 6.4 MB |

The 10,000-mission row is from an earlier run the same day, before the shelter-probe fix
(which does not touch the `balanced` path in these seeds); the other rows are from the final
code.

| Component (single mission or call) | Time / size |
|---|---|
| Engine alone, 240 ticks, no decisions | 39.7 ms |
| Mission with the `balanced` strategy (observation, decisions, telemetry) | 122.3 ms |
| Same, with invariants checked every tick | 159.1 ms (+30 %) |
| Replay 240 ticks / with full history kept | 51.1 ms / 134.1 ms |
| Full history (241 states) in memory | 8.3 MB (≈ 35 KB per state; canonical JSON 9,283 bytes) |
| Future Lens, default request (baseline + 1 candidate × 4 samples × 24 h) | 91.1 ms |
| Future Lens, 5 branches × 16 samples × 72 h | 2.94 s |
| Black Box with counterfactuals, 5 failure cases | mean 106 ms, max 234 ms |

Scaling is linear in mission count; memory is flat (results are small rows, histories are not
kept). Two workers give ~1.9× on 2 cores. A 500-seed × 8-strategy sweep takes ~4 minutes and
the full `diagnose` run ~18 minutes here.

**Observed bottlenecks** (not optimised; no need yet): replay cost is dominated by Pydantic
deep copies of the full state per recorded tick and by canonical hashing at every decision.
Counterfactuals multiply replay cost by the number of decision roots (capped at 5 per trace,
memoised). If missions grow 10×, the first steps would be copy-on-write history and caching
reconstructions by head hash.

## Quality gates

```bash
uv run ruff check app tests alembic
uv run ruff format --check app tests alembic
uv run mypy app tests                 # strict
uv run alembic upgrade head && uv run alembic check
uv run python -m app.tools.openapi_snapshot --check     # API v1 frozen
uv run python -m app.tools.contract_fixtures --check    # API v1 examples frozen
uv run python -m app.tools.game_contract --check        # odyssey.game.v1 frozen
uv run pytest
```
