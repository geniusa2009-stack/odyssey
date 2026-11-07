# ODYSSEY Backend

Backend for **ODYSSEY, Mission LUNA-01 "The Last Light"**, a NASA Space Apps Challenge
educational simulation in which students run a lunar outpost through the onset of lunar night
and feel real engineering trade-offs: power, thermal control, life support, water, food,
radiation, communications, science and crew safety.

This repository is the **backend only**: a deterministic simulation engine plus the API,
persistence, analysis and AI-explanation layers around it. There is no frontend here.

## What it does

* **Deterministic, replayable mission simulation.** The same seed and decisions give the same
  mission, bit for bit. Randomness is a pure function of `(seed, stream, tick)`.
* **Data-driven scenarios.** LUNA-01's 13 phases, events, alerts, objectives, outcomes and
  every balancing constant are YAML. All numbers are flagged *provisional*.
* **Immutable decision ledger.** Hash-chained, append-only (enforced by the database). Any state
  is `initial state + ledger + engine`, and `GET /verify` proves it.
* **Future Lens.** What-if projections on isolated copies, with confidence, assumptions and
  causal explanations, without leaking unforeseeable future events.
* **Black Box / Mission Trace.** Post-mortems with causal chains built from recorded state
  transitions, provenance and counterfactual replay, never "decision X caused failure".
* **Rewind.** Fork any decision into a new timeline. The original is never modified.
* **Engineering profile and Mission DNA.** Deterministic, with weights and genes as versioned
  data.
* **ORION.** An AI explanation layer that only cites simulation facts. Every answer is
  validated, and ungrounded output falls back to a deterministic mock. No API key needed.
* **NASA data architecture.** Provider interfaces, provenance on every value, cache and
  fallback, an evidence registry linking constants to sources.
* **Frontend-safe application contract (v1).** Read models projected from simulation truth
  (bootstrap, snapshot, resources, systems, crew, objectives, radiation budget, legal decisions),
  option-based decision commands with state versions (`409 STALE_STATE`) and idempotency keys,
  a stable error envelope, an OpenAPI snapshot test, and deterministic contract examples.
  Nothing in the contract reveals the seed or hidden future events (tested).
* **Realtime.** Ordered, versioned WebSocket events (`odyssey.realtime.v1`) via an in-memory or
  Redis bus, with reconnect/resume; multiplayer-ready participants, roles and permission policy.
* **Balancing Lab.** Runs thousands of deterministic missions with scripted strategies and
  measures outcome distributions, parameter sensitivity, decision impact and Future Lens /
  Black Box quality. It measures only; it never changes the shipped scenario.

## Quick start (no infrastructure, no keys)

```bash
uv sync
ODYSSEY_AUTO_CREATE_SCHEMA=true uv run uvicorn app.main:app --reload
open http://127.0.0.1:8000/docs
uv run pytest
```

With PostgreSQL and Redis: `docker compose up -d db redis`, then see
[docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md).

## Balancing Lab

```bash
uv run python -m app.simulation.analysis.balancing sweep --strategy all --seeds 100
uv run python -m app.simulation.analysis.balancing sweep --strategy balanced --seeds 500 \
    --set power.battery.capacity_kwh=200 --format json --output reports/sweep.json
uv run python -m app.simulation.analysis.balancing diagnose --seeds 500 --output-dir reports/diagnose
uv run python -m app.simulation.analysis.balancing quality --output reports/quality.json
uv run python -m app.simulation.analysis.balancing bench --missions 100,1000
uv run python -m app.simulation.analysis.balancing audit --reference balanced --seeds 5
uv run python -m app.simulation.analysis.balancing trajectory --representative reports/trajectories
uv run python -m app.simulation.analysis.balancing search --seeds 30 --refine-seeds 100 \
    --param power.solar_rated_kw=11,12,13 --output-dir reports/search
```

Details: [docs/BALANCING_LAB.md](docs/BALANCING_LAB.md). Current measurements:
[docs/PHASE3_BALANCE_REPORT.md](docs/PHASE3_BALANCE_REPORT.md).

## API contract tools

```bash
uv run python -m app.tools.openapi_snapshot --check      # API changed? (--write after review)
uv run python -m app.tools.contract_fixtures --check     # contract examples (--write to regenerate)
uv run python -m app.tools.api_bench --repeat 20         # endpoint latency and SQL query counts
```

Frontend integration starts at [docs/FRONTEND_HANDOFF.md](docs/FRONTEND_HANDOFF.md).

## Stack

Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic · PostgreSQL / SQLite ·
Redis (optional) · httpx · pytest + Hypothesis · ruff · mypy (strict) · uv.

The simulation package (`app/simulation/`) depends only on the standard library, Pydantic and
PyYAML. A test enforces it.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, data flows (decision → ledger → realtime; ORION), principles |
| [SIMULATION_MODEL.md](docs/SIMULATION_MODEL.md) | Every modelled quantity, unit, equation, dependency, simplification |
| [API.md](docs/API.md) | Endpoint overview (frozen, provisional, internal), conventions, engine decisions |
| [API_CONTRACT.md](docs/API_CONTRACT.md) | The frontend-safe contract with JSON examples: bootstrap, read models, decisions, versions, idempotency, errors, realtime, resume, Future Lens, Black Box, rewind, completion |
| [API_FREEZE_V1.md](docs/API_FREEZE_V1.md) | What is FROZEN / PROVISIONAL / INTERNAL, compatibility rules, Phase 4 changes |
| [FRONTEND_HANDOFF.md](docs/FRONTEND_HANDOFF.md) | How a frontend should use the backend: what to trust, what never to compute |
| [DATABASE.md](docs/DATABASE.md) | Tables, integrity model, indexes, migrations |
| [FUTURE_LENS.md](docs/FUTURE_LENS.md) | Prediction model, honesty policy, confidence |
| [BLACK_BOX.md](docs/BLACK_BOX.md) | Reconstruction and root-cause tracing |
| [ORION.md](docs/ORION.md) | AI provider abstraction, grounding rules, prompt safety |
| [NASA_DATA_OPTIONS.md](docs/NASA_DATA_OPTIONS.md) | Data architecture and candidate datasets |
| [BALANCING_LAB.md](docs/BALANCING_LAB.md) | Strategies, sweeps, sensitivity, decision impact, CLI |
| [BALANCING_FINDINGS.md](docs/BALANCING_FINDINGS.md) | Phase 2 measurements of LUNA-01 v0.1.0 (the "before"): bugs, balance issues, product decisions |
| [SCIENCE_EVIDENCE_AUDIT.md](docs/SCIENCE_EVIDENCE_AUDIT.md) | Every evidence entry classified VERIFIED / UNVERIFIED / FIXTURE_ONLY / PROVISIONAL |
| [PARAMETER_GOVERNANCE.md](docs/PARAMETER_GOVERNANCE.md) | Every scenario parameter: EVIDENCE_LOCKED / EDUCATIONAL_ABSTRACTION / GAMEPLAY_PARAMETER / UNVERIFIED, and every v0.2.0 change with its reason |
| [DECISION_IMPACT_MODEL.md](docs/DECISION_IMPACT_MODEL.md) | Measured impact class of every decision kind (HIGH / MEDIUM / LOCAL / REDUNDANT) |
| [PHASE3_BALANCE_REPORT.md](docs/PHASE3_BALANCE_REPORT.md) | LUNA-01 v0.1.0 vs v0.2.0: outcome model, strategy distributions, resources, decisions, analysis quality |
| [GAME_BACKEND_ARCHITECTURE.md](docs/GAME_BACKEND_ARCHITECTURE.md) | Phase 5: the open-world game backend (`odyssey.game.v1`) — layers, turn, clock, persistence, concurrency |
| [UNREAL_BACKEND_CONTRACT.md](docs/UNREAL_BACKEND_CONTRACT.md) | The frozen Unreal protocol: endpoints, semantic commands, versions, idempotency, errors |
| [UNREAL_HANDOFF.md](docs/UNREAL_HANDOFF.md) | How the Unreal client should use the backend (bootstrap, actions, resume, never per-frame) |
| [GAMEPLAY_BACKEND_BOUNDARIES.md](docs/GAMEPLAY_BACKEND_BOUNDARIES.md) | What Unreal owns vs what the backend owns; trust; crew cues; Earth Command on the real engine |
| [CAMPAIGN_MODEL.md](docs/CAMPAIGN_MODEL.md) | Eight phases, mission states, Earth Command flow, LUNA-01, Mars gates |
| [CAPABILITY_AND_CERTIFICATION.md](docs/CAPABILITY_AND_CERTIFICATION.md) | Capability graph, qualification stages, certifications, readiness, Human Expansion Map, knowledge |
| [INVENTORY_CARGO_MODULES.md](docs/INVENTORY_CARGO_MODULES.md) | Items, containers, mass budgets, modules and compatibility, shipyard view |
| [WORLD_SEMANTIC_STATE.md](docs/WORLD_SEMANTIC_STATE.md) | Semantic ids, objects, incidents, infrastructure states and persistence, discoveries |
| [GAME_REALTIME_PROTOCOL.md](docs/GAME_REALTIME_PROTOCOL.md) | Game event envelope and types, control frames, resume and back-fill |
| [SAVE_RESTORE.md](docs/SAVE_RESTORE.md) | Saves, checkpoints, the single restore path, rewind, timeline ownership, content versions |
| [RUN_LOCAL_GAME_BACKEND.md](docs/RUN_LOCAL_GAME_BACKEND.md) | Local start path for Unreal development |
| [TESTING.md](docs/TESTING.md) | Test map, results, fuzzing, performance |
| [LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) | Setup and commands |
| [BACKEND_AUDIT.md](docs/BACKEND_AUDIT.md) | Repository audits |
| [USER_DECISIONS_REQUIRED.md](docs/USER_DECISIONS_REQUIRED.md) | Product decisions deliberately left open |
| [RECOVERY_PROVENANCE.md](docs/RECOVERY_PROVENANCE.md) | Internal: provenance of the reconstructed repository |

## Status

Backend complete and tested (911 tests passing with PostgreSQL and Redis). The repository
was reconstructed after a workspace loss; see [RECOVERY_PROVENANCE.md](docs/RECOVERY_PROVENANCE.md). Phase 2
added the Balancing Lab, state invariants, fuzzing, cascade and Black Box regression tests, a
science evidence audit and measured balancing findings. Phase 3 made LUNA-01 meaningful
(v0.2.0: multi-pillar outcomes, decision consequences, radiation information, parameter
governance; see [PHASE3_BALANCE_REPORT.md](docs/PHASE3_BALANCE_REPORT.md)). Phase 4 turned it
into an application platform with a frozen v1 contract for a future frontend
([API_FREEZE_V1.md](docs/API_FREEZE_V1.md)); gameplay is frozen (battery 240 kWh and array
12 kW are PLAYTEST-FROZEN, D23; maintenance stays a local mechanic, D24). Scoring,
authentication, final NASA datasets and ORION's production provider are open decisions. See [USER_DECISIONS_REQUIRED.md](docs/USER_DECISIONS_REQUIRED.md).

Phase 5 added the open-world game backend for the Unreal Engine client: a separately versioned
protocol `odyssey.game.v1` at `/api/game/v1` with semantic actions, a server-authoritative
clock, an eight-phase campaign (Earth Command fully playable and transitioning into LUNA-01),
capability qualification instead of XP, inventory/cargo/modules, persistent infrastructure,
discoveries and knowledge, saves and a single restore path, and game adapters for Future Lens,
Black Box and Rewind ([GAME_BACKEND_ARCHITECTURE.md](docs/GAME_BACKEND_ARCHITECTURE.md)). API v1
and LUNA-01 are unchanged.

Licence: not yet chosen ([D16](docs/USER_DECISIONS_REQUIRED.md#d16-project-licence)).
