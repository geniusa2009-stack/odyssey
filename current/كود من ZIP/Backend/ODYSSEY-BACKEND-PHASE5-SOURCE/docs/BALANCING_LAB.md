# Balancing Lab

A backend-only toolkit that **measures** how LUNA-01 plays by running thousands of
deterministic missions with scripted strategies. It never changes the shipped scenario:
parameter changes exist only inside an experiment.

Code: `app/simulation/analysis/balancing/` (standalone simulation package: no HTTP, database,
Redis or AI). Findings from running it: [BALANCING_FINDINGS.md](BALANCING_FINDINGS.md).

## What it does

| Capability | Module | Notes |
|---|---|---|
| Run one mission with a strategy, collect telemetry | `runner.py` | Drives `SimulationEngine` directly. Every decision passes the engine's normal validation; rejections are counted, never forced |
| Scripted strategies | `strategies.py` | 8 sweep strategies + 2 diagnostic probes (below) |
| Batch execution | `sweep.py` | strategies × seeds (× overrides, × suppressed events), serial or process pool. Output is sorted, so results are identical for any worker count (tested) |
| Scenario parameter overrides | `overrides.py` | `path=value` into the scenario JSON; list items by `id`. Re-validated by the scenario schema, so an override can never create an invalid scenario |
| Outcome distributions | `aggregate.py` | Outcome-class rates, objective rates, battery-depletion / crew-incapacitation / rover-loss rates, mean/min/p10/p50/p90/max of 27 telemetry fields, distinct-result count |
| Sensitivity | `sensitivity.py` | One parameter at a time over a bounded list of values |
| Event ablation | `sensitivity.py` | Suppress one scenario event at a time; compare with the unmodified scenario |
| Decision impact | `impact.py` | Fork every decision (omit or replace), continue open-loop (replay the rest) or closed-loop (strategy adapts), compare |
| Pathology detectors | `diagnostics.py` | Never-/always-achieved objectives, unreachable outcomes, unavoidable / never-firing alerts, seed insensitivity, degenerate strategies, decisive / inert events, no-op / pivotal decisions |
| Future Lens and Black Box quality | `quality.py` | Determinism, isolation, distinguishability (end values and, since Phase 3, every lens signal), surprise blindness, calibration, trace correctness, irrelevant blame, stability, outcome-analysis coverage, Engineering Profile separation |
| Decision audit (Phase 3) | `decision_audit.py` | Inserts each catalogue decision into a reference strategy's mission at fixed ticks (open loop) and classifies its measured impact: HIGH / MEDIUM / LOCAL / REDUNDANT ([DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md)) |
| Bounded parameter search (Phase 3) | `search.py` | Grid over GAMEPLAY parameters only (evidence-locked and protected paths are refused), screened on few seeds, top candidates refined; ranked by diagnostic envelopes passed, then by distance from the shipped values. Writes a report; **never edits the scenario** |
| Resource trajectories (Phase 3) | `trajectory.py` | Per-tick CSV/JSON of one mission (power, battery, O₂, water, food, temperature, CO₂, radiation and dose, crew health, science, phase, events, decisions), and a set of representative missions |
| Performance | `bench.py` | Missions/s, peak RSS, history memory, lens / replay / Black Box cost |
| Exports | `report.py` | JSON (versioned `odyssey.balancing.*` reports) and CSV (one row per mission, or one per strategy) |

## Strategies

They are **synthetic probes, not models of real players.** Each is a fixed, documented
heuristic. They may read only what a player can observe at the current tick (state, active
alerts, open opportunities, published limits). They never read future events, the RNG or
other seeds. Thresholds inside them are probe parameters, not balancing decisions.

| Name | Behaviour |
|---|---|
| `passive` | Control group: never decides |
| `survival_first` | Life support, crew safety and reserves first: shelter from radiation, rationing to the end date, tiered power saving, maintenance, array cleaning; no science |
| `science_first` | Every habitat science window in boost, rover traverses, comms kept up; no sheltering or power saving |
| `balanced` | Shelter, science when power allows, tiered load shedding, maintenance, cleaning, rationing |
| `power_conservative` | Eco loads, low setpoint and charger off from tick 0, early rover energy transfer, science only with a full battery |
| `high_risk` | Boosted science, traverses regardless of battery, no shelter, 12 °C setpoint, 70 % rations, maintenance only below 30 % health |
| `naive_beginner` | Reacts to one alert at a time with the first obvious fix, including counter-productive ones (maxing the thermostat when cold); starts any science offered |
| `random_valid` | Each tick, probability 0.1 of one action drawn uniformly from currently valid actions. Uses the counter-based RNG with a seed derived from the mission seed, so it is reproducible |
| `reserve_keeper` *(probe)* | Existence probe: can any play end with reserves? Balanced by day, strict night mode once generation falls |
| `always_shelter` *(probe)* | Probe: crew in the shelter from tick 0, nothing else |
| `expert` *(probe, Phase 3)* | Existence probe for *exceptional* success: budget-aware sheltering, boosted habitat science while power is plentiful, oxygen generation eco above 6.5 days of O₂, the rover traverse with comms kept up until its data is sent, a strict night plan, maintenance and cleaning |

`all` = the 8 sweep strategies. Probes are run by name or by `diagnose`.

**Phase 3 adaptations** (only where the new v0.2.0 rules made a probe misrepresent its
philosophy; every rule still reads only the current observation):

* Shelter policy: also reacts to the new `radiation_above_background` caution; survival-first
  and balanced (`budget_aware`) also shelter when the projected dose budget runs low (while no
  habitat science is running) or is exceeded.
* A shared night power plan once observed solar availability falls below 0.35 (dusk): eco loads,
  lower setpoint, oxygen generation eco/off while a reserve remains, rover energy transferred at
  night. Strict for survival-first, moderate for balanced.
* Survival-first: habitat science in eco mode when calm (battery ≥ 80 %, no warnings, not dusk);
  never sends the rover. The brief describes it as "low/moderate science", not none.
* Naive-beginner: notices alerts on a given tick with probability 0.6 (seeded from the mission
  seed), modelling inconsistent attention.
* Balanced: rover traverse only with the battery above 60 % (was 30 %).
* Power-conservative: also applies the strict night plan at dusk, with the shared life-support
  safety reaction; its own comms/setpoint rules apply only before dusk. Before, it saved power
  only by day, when the battery was full and surplus was curtailed, and ended v0.2.0 missions
  with the lowest battery of the successful strategies (median 6 %), contradicting its
  philosophy. (A first version of this change made two rules fight over the comms mode, 219
  flips in three missions; fixed, and `test_balancing_lab_phase3.py::TestProbeHygiene` now
  rejects any probe whose rules flip a setting back and forth.)

## Telemetry per mission

Outcome and outcome class (exceptional / success / partial / failure / crew_loss; "success
rate" = exceptional + success), ending phase, duration;
battery SOC min/final (and final kWh), battery-zero events and ticks, load-shed ticks, unmet
energy; O₂, water and food minima (days and kg) and O₂ / water days at the end, CO₂ peak; habitat temperature minimum, cold ticks, ticks below
the water-processor minimum; crew dose, minimum health, incapacitations; science points,
completion and downlinked data; objectives (per id); emergency events, critical and warning
alerts (per id), cascade warnings, comms outages (events and ticks), space-weather events,
random and scripted faults, maintenance completed, rover traverses / successes / loss; final
and peak risk; decisions accepted / rejected (by type and code); invariant violations.

## CLI

```bash
uv run python -m app.simulation.analysis.balancing --help
```

| Command | Purpose | Example |
|---|---|---|
| `sweep` (default) | Strategies × seeds → distributions | `… --scenario luna01 --strategy balanced --seeds 100` |
| | All strategies, JSON | `… sweep --strategy all --seeds 500 --format json --output reports/sweep.json` |
| | Override parameters | `… sweep --set power.battery.capacity_kwh=200 --set food.initial_food_kg=80` |
| | Remove an event | `… sweep --suppress-event solar_particle_event` |
| | Check invariants every tick | `… sweep --strategy all --seeds 500 --strict` |
| `sensitivity` | One-at-a-time parameter sweep | `… sensitivity --parameter power.solar_rated_kw --values 11,13,15,17,20 --seeds 50` |
| `ablation` | Suppress each event | `… ablation --seeds 50` |
| `impact` | Fork each decision | `… impact --strategy balanced --seeds 10 --continuation both` |
| `diagnose` | sweep + ablation + impact (+ sensitivity) + findings | `… diagnose --seeds 500 --sensitivity-seeds 50 --output-dir reports/diagnose` |
| `quality` | Future Lens, Black Box and profile quality | `… quality --profile-seeds 10 --output reports/quality.json` |
| `bench` | Performance at scale | `… bench --missions 100,1000,10000 --output reports/bench.json` |
| `audit` | Decision impact classification | `… audit --reference balanced --seeds 5 --output reports/audit.json` |
| `search` | Bounded gameplay-parameter search (report only) | `… search --seeds 30 --refine-seeds 100 --top 3 --param power.solar_rated_kw=11,12,13 --param power.battery.capacity_kwh=200,240,280 --output-dir reports/search` |
| `trajectory` | Per-tick trajectory of one mission, or the representative set | `… trajectory --strategy balanced --seed 1 --format csv --output reports/b1.csv` · `… trajectory --representative reports/trajectories` |

Common options: `--seeds N`, `--start-seed S`, `--workers W` (default: CPU count, max 8),
`--format text|json|csv|summary-csv`, `--output FILE`. Progress goes to stderr; reports go to
stdout or `--output`. `reports/` is git-ignored: regenerate rather than commit results.

### Override paths

```
power.battery.capacity_kwh=200                        mapping key
power.consumers.habitat_core.nominal_kw=1.2           list item by id
events.solar_particle_event.trigger.at_tick=100       event by id
objectives.radiation_safety.fail_when.value=20        objective by id
environment.solar_availability.0.value=0.9            list item by index
degradation.components.*.fault_damage=0.2             every item of a list (Phase 3)
degradation.components.*.wear_per_tick*=3             multiply instead of set (Phase 3)
```

Values are JSON (`200`, `0.5`, `true`, `"eco"`). An unknown path or an invalid resulting
scenario is an error that lists the valid keys or ids.

## Reproducibility

* Same scenario + strategy + seed → identical mission (the engine is deterministic and
  strategies are pure functions of the observation plus a derived seed).
* Every JSON report carries the scenario's content hash; a re-balanced scenario is
  distinguishable from the one measured.
* Decision ids inside the lab are `<strategy>:<sequence>`; any mission can be replayed or
  forked from its recorded decisions (`AppliedDecision.to_replay()`).

## Limits

* Strategies are heuristics. A result such as "no scripted strategy achieves X" means *these
  probes* do not, and needs an existence probe or a human playtest before concluding X is
  impossible.
* One-at-a-time sensitivity shows main effects, not interactions.
* Throughput on this 2-core workspace is ~60 ms per mission with 2 workers. See
  [TESTING.md](TESTING.md#performance-at-scale).
