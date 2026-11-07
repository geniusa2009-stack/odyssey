# Balancing Findings

> **Historical (Phase 2, LUNA-01 v0.1.0).** This document measures the v0.1.0 scenario
> (content hash `a67635671fa5…`) and is kept as the "before" picture. Phase 3 acted on its
> balance issues and product decisions; LUNA-01 v0.2.0 is measured in
> [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md). Every number below was re-reproduced byte
> for byte from commit `9d0b00d` at the start of Phase 3.

What the Balancing Lab measured about LUNA-01 in Phase 2. **Nothing here was tuned.** Every
number describes the shipped, provisional scenario (content hash `a67635671fa5…`). Balance
questions are listed for a human to decide in
[USER_DECISIONS_REQUIRED.md](USER_DECISIONS_REQUIRED.md).

Measured on 2026-10-07 with the code in this repository. To reproduce (about 35 minutes on
2 cores):

```bash
L="uv run python -m app.simulation.analysis.balancing"
$L sweep --strategy all --seeds 500 --format text
$L sweep --strategy all,reserve_keeper,always_shelter --seeds 500 --strict --format summary-csv
$L diagnose --seeds 500 --ablation-seeds 50 --impact-seeds 10 --sensitivity-seeds 50 --output-dir reports/diagnose-500
$L quality --lens-seeds 3 --failure-seeds 100 --failures-per-strategy 5 --output reports/quality.json
```

Strategies are scripted probes, not players ([BALANCING_LAB.md](BALANCING_LAB.md#strategies)).
"No strategy does X" means *these probes* don't; where it mattered, a dedicated probe or a
forked replay checked whether X is possible at all.

The findings are split three ways, as the Phase 2 brief requires:

* **Bugs**: the code did something it should not. Fixed, each with a regression test.
* **Balance issues**: the code does what it says, but the numbers make the game trivial,
  binary, unfair or inert. Measured, not changed.
* **Product decisions**: the behaviour is a design choice nobody has made yet. Recorded as
  D18–D22 in [USER_DECISIONS_REQUIRED.md](USER_DECISIONS_REQUIRED.md).

---

## Bugs

### Engine and service bugs (fixed)

| # | Bug | How it was found | Fix | Regression test |
|---|---|---|---|---|
| B1 | Battery charge could stay above the battery's **faded** capacity after component wear (seed 12345, no decisions: 157.936 kWh stored at tick 130 where the worn battery holds 157.920 kWh) | New state invariant `0 ≤ E ≤ capacity(health)` | `degradation.py` clamps charge to the current capacity at the end of the degradation step | `test_invariants_and_fuzz.py::TestInvariantChecker::test_regression_battery_never_exceeds_faded_capacity` |
| B2 | Root-cause tracing could **hide a later decision** when a parent metric was already degraded at the start of the record (e.g. low initial reserves masked "water recovery off") | Cascade validation (`test_cascades.py`) | `root_cause.py` adds a `scenario:initial:<metric>` node and keeps tracing at the worst tick | `test_cascades.py::test_initial_condition_does_not_hide_a_later_decision` |
| B3 | An **acute radiation** death had no causal path: the dependency graph had no edge from dose *rate* to crew health | Cascade validation (storm case) | New metric `crew.received_dose_rate_msv_h` and edges `env.radiation_dose_rate_msv_h → crew.received_dose_rate_msv_h → crew.min_health` | `test_cascades.py::test_acute_radiation_death_is_attributed`, `::test_harmless_flare_is_not_blamed_for_crew_loss` |
| B4 | Future Lens and ORION calls **bypassed the authorization seam** (any policy was silently skipped for them) | Auth-seam review | `participant_id` on both request bodies; `MissionService._authorize` called with `FUTURE_LENS` / `ORION` | `test_auth_seam.py::test_future_lens_and_orion_respect_the_policy` |

On the Phase 1 checkpoint (`1606ade`), 4 of the new cascade tests fail; all pass now.

Effect on results: B1 changes one stored value by 0.016 kWh from tick 130 onward in long
missions. Mission state hashes for the same seed and decisions are therefore different from
the checkpoint (Future Lens `base_state_hash` included), but **no outcome or objective changed**
in any measured run. B2–B4 change analysis output only, never the simulation.

### Balancing Lab and test bugs (fixed during Phase 2)

| # | Bug | Fix |
|---|---|---|
| T1 | Shelter probe treated "anyone in the shelter" as "everyone", so a crew member coming back from EVA mid-storm was never re-ordered to the shelter | `Observation.sheltered()` now means every movable crew member; regression test `test_balancing_lab.py::TestStrategies::test_shelter_order_is_reissued_for_a_member_back_from_eva`. Only the SPE-at-tick-200 sensitivity point changed (balanced dose 22.0 → 16.9 mSv); every 500-seed sweep result was identical before and after |
| T2 | `--strategy all,reserve_keeper` failed ("unknown strategy 'all'") | `strategies_or_all` expands `all` inside lists |
| T3 | One corruption case in the invariant-checker test was dead code (`if False`), so the "active opportunity is not ACTIVE" invariant was never exercised | Replaced with a real corruption; the invariant is now tested |
| T4 | `HYPOTHESIS_PROFILE=fuzz` failed ("profile not registered"): the profile was registered in a test module, after `conftest.py` had already loaded the profile | Registered in `conftest.py` |

The fuzz and invariant suite found no other engine bug (see
[State invariants and fuzzing](#state-invariants-and-fuzzing)).

---

## Balance issues

Measured facts. None was changed, because changing them is balancing (D1/D3).

| # | Issue | Evidence |
|---|---|---|
| BAL1 | **Outcomes are binary per strategy.** Each scripted strategy gets the same outcome class in 100 % of 500 seeds | [Outcome distributions](#outcome-distributions) |
| BAL2 | **One dominant path.** Doing the ice-core science gives full success; science-first does it with a median of 4 decisions and no sheltering or power management | Ablation: removing `ice_core_window` turns science-first from 100 % success to 100 % partial; open-loop forks: omitting `start ice_core_sampling` changes the outcome in 21 of 30 forks |
| BAL3 | **Battery always empties.** Battery reaches 0 % in 100 % of missions for every scripted strategy (median 6–26 ticks at zero) | Sweep. Not impossible: the `reserve_keeper` probe depletes in 0.2 % |
| BAL4 | **`reserves_at_end` is only reachable with a dedicated strategy** (0 % for all 7 scripted strategies, 99.4 % for `reserve_keeper`) | Sweep + probe |
| BAL5 | **`crew_survival` is free** (passive: 100 %) and the `mission_failed` outcome is **unreachable** (0 of 4,000 missions) | Diagnostics. Structural: see D3 |
| BAL6 | **Randomness barely matters**: 17–62 distinct mission results from 500 seeds per scripted strategy (random play: 489) | Diagnostics |
| BAL7 | **Alerts that carry no information**: `habitat_cold`, `radiation_elevated` and `comms_link_down` fire in 100 % of scripted missions; `oxygen_critical` never fires (0 of 5,000) | Diagnostics |
| BAL8 | **Inert content**: removing `relay_outage`, `water_processor_pump_fault`, `far_crater_window` or `freeze_damage_water_processor` changes no outcome or objective rate. The freeze event never fires for any scripted strategy (habitat minimum ≥ 3.7 °C vs a 3 °C trigger); only random play reaches it (15 of 500 missions) | [Event ablation](#event-ablation) |
| BAL9 | **Power decisions never change the result.** 500 open-loop forks of power, thermal, rover and cleaning decisions changed 0 outcomes and 0 objectives (they do change ticks at zero battery in 171 forks) | [Decision impact](#decision-impact) |
| BAL10 | **CO₂ ends far above "critical" without consequence.** Median CO₂ peak in the final hours: 17,710 ppm (balanced), 20,717 (passive), 25,483 (science-first) vs a 10,500 ppm critical limit. The crew survives (minimum health 0.74–0.84) because the mission ends | Sweep |
| BAL11 | **1.8 % of seeds fail radiation safety by luck** for a reactive player (flare stacked on the SPE). Avoidable only with sub-alert reactions and a dose budget | D21 and [Outcome distributions](#outcome-distributions) |
| BAL12 | **Thermal conductance is a cliff.** 0.015 (baseline) → 0.03: minimum health 0.84 → 0.52; → 0.04: crew loss 100 % for balanced and science-first | [Sensitivity](#sensitivity) |
| BAL13 | **Science payload power has no effect** (0.6–2.4 kW: identical results); water recovery 0.80–0.98: identical results | [Sensitivity](#sensitivity) |

---

## Product decisions

New open decisions recorded in [USER_DECISIONS_REQUIRED.md](USER_DECISIONS_REQUIRED.md):

| # | Question | Measured trigger |
|---|---|---|
| [D18](USER_DECISIONS_REQUIRED.md#d18-end-of-mission-objectives-after-an-early-conclusion) | Evaluate end-of-mission objectives when the crew is lost early? | High-risk meets `reserves_at_end` in 2.0 % of seeds, all crew-loss missions; random play: 39 of 46 such seeds (100-seed set) |
| [D19](USER_DECISIONS_REQUIRED.md#d19-where-an-eva-crew-member-returns-during-a-radiation-event) | Where does an EVA member return during a radiation event? | SPE at tick 200: 22.0 mSv without re-ordering, 16.87 mSv with |
| [D20](USER_DECISIONS_REQUIRED.md#d20-decisions-that-have-no-effect-while-a-load-is-shed) | Feedback for decisions on an unpowered subsystem? | Scrubber `boost` at tick 227 (balanced) and 235 (survival-first): flagged no-op in 10 of 10 forks each |
| [D21](USER_DECISIONS_REQUIRED.md#d21-overlapping-radiation-events) | How should overlapping radiation events combine? | 9 of 500 seeds |
| [D22](USER_DECISIONS_REQUIRED.md#d22-what-the-mission-risk-index-includes) | Should the risk index include radiation? | Risk error from the hidden SPE ≤ 0.021 while dose error is 10.67 mSv |

Measured notes were also added to D1 (balancing), D3 (objectives: any two optional objectives
win; science and data always come together) and D6 (Future Lens).

---

## Outcome distributions

500 seeds (1–500) per strategy, LUNA-01 as shipped. Rates in %; dose, health, science and
decisions are medians.

| Strategy | Success | Partial | Crew loss | Science | Data | Radiation | Reserves | Battery 0 % | Dose mSv | Min health | Science pts | Decisions | Distinct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `passive` | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 18.9 | 0.83 | 0 | 0 | 17 |
| `survival_first` | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 98.2 | 0.0 | 100.0 | 11.7 | 0.95 | 0 | 9 | 62 |
| `science_first` | 100.0 | 0.0 | 0.0 | 100.0 | 100.0 | 0.0 | 0.0 | 100.0 | 18.9 | 0.74 | 131 | 4 | 27 |
| `balanced` | 100.0 | 0.0 | 0.0 | 100.0 | 100.0 | 98.2 | 0.0 | 100.0 | 11.7 | 0.84 | 125 | 12 | 61 |
| `power_conservative` | 100.0 | 0.0 | 0.0 | 100.0 | 100.0 | 98.2 | 0.0 | 100.0 | 11.8 | 0.98 | 85 | 12 | 23 |
| `high_risk` | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 0.0 | 2.0 | 98.0 | 18.4 | 0.00 | 127 | 6 | 25 |
| `naive_beginner` | 100.0 | 0.0 | 0.0 | 100.0 | 100.0 | 98.2 | 0.0 | 100.0 | 11.7 | 0.83 | 84 | 6 | 18 |
| `random_valid` | 0.4 | 42.0 | 57.6 | 1.8 | 0.2 | 21.2 | 43.6 | 36.4 | 18.0 | 0.00 | 0 | 21 | 489 |
| `reserve_keeper` *(probe)* | 100.0 | 0.0 | 0.0 | 100.0 | 100.0 | 98.2 | 99.4 | 0.2 | 11.7 | 0.98 | 84 | 44 | 44 |
| `always_shelter` *(probe)* | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 100.0 | 4.7 | 0.83 | 0 | 1 | 17 |

`failure` (`mission_failed`) is 0.0 for every strategy. Rover loss: 2.4 % for balanced,
high-risk and science-first, 0.4 % for random play, 0 otherwise.

**Stability across sample sizes.** Outcome classes are identical at 50, 100 and 500 seeds for
every scripted strategy. Radiation safety for the sheltering strategies: 94 % (50 seeds),
96 % (100), 98.2 % (500). Random play: success 0 / 1 / 0.4 %, crew loss 66 / 58 / 57.6 %.

**Radiation failures (BAL11).** The 9 failing seeds are 2, 12, 39, 63, 259, 291, 297, 449 and
482 for every sheltering strategy. Forked replays (seed by seed, the strategy's own decisions
kept):

| Mechanism | Seeds | Avoidable by |
|---|---|---|
| Flare (×5, 0.285 mSv/h, below the 0.5 mSv/h alert) starts one tick before the SPE; the SPE's first hour is ×200 in the habitat (+6.84 mSv) | 39, 291, 297 | Sheltering on *any* reading above the 0.057 mSv/h baseline (re-running all 500 seeds with that rule: these 3 pass, nothing else changes) |
| Flare overlaps the SPE while the crew is sheltered (12–15 mSv after the event); background dose in the habitat crosses 15 mSv before the end | 2, 12, 63, 259, 449, 482 | Staying in the shelter for extra time after the event: 36 h fixes 5 of 6, seed 2 needs ~60 h |

`always_shelter` (crew in the shelter for the whole mission) passes in all 500 seeds but gives
up all habitat science.

## Impossible and dominant paths

* **Dominant:** `start_science_activity(ice_core_sampling)`. With it, any second optional
  objective is already met (data return), so success needs no survival play at all.
* **Looked impossible, is not:** `reserves_at_end` (0 % for every scripted strategy) is met in
  99.4 % by `reserve_keeper`, which runs balanced by day and a strict night mode once generation
  falls. Battery depletion is therefore a strategy outcome, not a hard floor.
* **Unreachable:** the `mission_failed` fallback outcome (structural; D3).
* **Never happens for any reasonable play:** `oxygen_critical`; the freeze-damage event.
* **Degenerate strategies flagged:** naive-beginner (100 % success, median 6 decisions) and
  science-first (100 % success, median 4 decisions).

## Sensitivity

One parameter at a time, 50 seeds, strategies balanced / science-first / survival-first. Every
other parameter at its shipped value. "No change" means identical outcome and objective rates
and medians to within rounding.

| Parameter | Baseline | Values tried | Effect |
|---|---|---|---|
| `power.battery.capacity_kwh` | 160 | 100, 130, 200, 250 | Min health tracks capacity (balanced 0.60 → 0.98). At **250**, survival-first jumps from 0 % to **94 % success** (reserves met 100 %, battery never empties); balanced stops depleting (2 %) |
| `power.solar_rated_kw` | 15 | 11, 13, 17, 20 | Min health only (balanced 0.52 → 0.96); no outcome change |
| `power.consumers.habitat_core.nominal_kw` | 1.5 | 1.0, 1.25, 1.75, 2.0 | Min health only (balanced 0.94 → 0.72) |
| `power.consumers.oxygen_generation.nominal_kw` | 1.5 | 0.75, 1.1, 2.0, 2.5 | At **0.75**, survival-first **94 % success** (reserves met); above baseline, min health falls (balanced 0.58 at 2.5) |
| `life_support.water_recovery_nominal` | 0.93 | 0.80, 0.86, 0.98 | No change |
| `food.initial_food_kg` | 70 | 55, 62, 80 | Food minimum 0.03 days (balanced) / 0.00 (science-first: runs out) at 55; min health 0.78 / 0.63; no outcome change |
| `radiation.habitat_shielding_factor` | 0.6 | 0.3, 0.45, 0.8, 1.0 | Radiation safety (balanced): 100 / 98 / **44** / **0** %; science-first passes at 0.3 (96 %) and 0.45 (94 %) |
| `objectives.radiation_safety.fail_when.value` (mSv) | 15 | 10, 12.5, 20, 25 | Radiation safety (balanced): **0** / 78 / 100 / 100 %; science-first passes 94 % at 20 and 25 |
| `thermal.conductance_kw_per_k` | 0.015 | 0.01, 0.02, 0.03, 0.04 | Min health (balanced) 0.86 / 0.80 / 0.52; at **0.04**, **crew loss 100 %** for balanced and science-first, survival-first partial with min health 0.05 |
| `power.consumers.comms.nominal_kw` | 0.4 | 0.2, 0.8 | Min health only (balanced 0.88 / 0.75) |
| `power.consumers.science_payload.nominal_kw` | 1.2 | 0.6, 1.8, 2.4 | No change |
| `events.solar_particle_event.trigger.at_tick` | 122 | 60, 100, 160, 200 | Radiation safety (balanced) 90 / 98 / 98 / **0** %. At 200 the SPE overlaps a cleaning EVA (D19) |

Full per-point data: `reports/diagnose-500/sensitivity.json` (regenerate; `reports/` is not
committed).

## Event ablation

Each scenario event suppressed in turn (50 seeds, 4 strategies), compared with the unmodified
scenario:

| Event removed | Effect |
|---|---|
| `ice_core_window` | **Decisive.** Data return → 0 % for balanced and science-first; science-first 100 % success → 100 % partial; balanced 8 % partial |
| `regolith_survey_window` | Science −20 pts (balanced); science-first 2 % partial |
| `solar_particle_event` | Radiation safety → 100 % for every strategy (dose −10.67 mSv passive / science-first, −3.46 sheltering) |
| `minor_flare` | Radiation safety +6 % for sheltering strategies (the 3 of 50 flare-stacking seeds); dose −0.41 mSv |
| `far_crater_window` | No outcome change; balanced min health +0.12, science −41 pts (the traverse costs energy) |
| `water_processor_pump_fault` | No outcome change; water minimum +0.56 to +0.74 days |
| `relay_outage` | No change at all |
| `freeze_damage_water_processor` | No change at all (never fires) |

## Decision impact

Every decision of 4 strategies × 10 seeds forked by omitting it (752 forks), then continued two
ways:

| Continuation | Forks | Outcome changed | Objectives changed | No measurable effect |
|---|---|---|---|---|
| Open loop (`replay`: the rest of the original decisions) | 376 | 22 | 68 | 20 |
| Closed loop (`strategy`: the strategy keeps playing) | 376 | 0 | 0 | 160 |

* **All 22 outcome changes are `mission_complete → mission_complete_partial` from omitting a
  science start:** ice core (power-conservative 10, science-first 10, balanced 1) and regolith
  survey (power-conservative 1).
* Omitting a **shelter** order loses radiation safety in 27 of 30 forks (the other 3 are seeds
  that fail anyway). Omitting a **return to the habitat** gains radiation safety in 1 fork,
  consistent with D21.
* **Power, thermal, rover and cleaning decisions: 500 forks, 0 outcome or objective changes.**
  `battery_soc_min` never changes (it is 0 in every scripted mission); ticks at zero battery
  change in 171 forks.
* **No-op decisions** (no effect in 10 of 10 open-loop forks): CO₂ scrubber `boost` at the end
  of the mission when the battery is empty (balanced, survival-first). See D20.
* **Reading the closed-loop column:** "no effect" there mostly means the strategy re-issued the
  same decision a tick later, because its rule still applied. It measures how robust a
  strategy is to one missed action, not whether the action matters. The open-loop column
  measures the action itself.

## Cascade validation

`tests/test_cascades.py` forces six multi-system cascades through scenario data or decisions:

| Case | Forced by | Chain checked |
|---|---|---|
| `night_power_to_water` | No sun, 25 % battery | generation → water-recovery supply → recovery efficiency |
| `heater_off_to_water_recovery` | Heater off in deep cold | heater mode → habitat temperature → recovery efficiency |
| `power_to_comms` | Night, comms lowest priority | comms supply → link |
| `water_to_oxygen_to_crew` | Water recovery off, low reserves | water days → O₂ generation → crew health |
| `pump_fault_to_water` | Scheduled pump damage | component health → recovery efficiency → water days |
| `storm_to_crew` | ×200 radiation for 30 ticks | dose rate → received dose rate → crew health |

For each: every cascade warning names a declared edge whose source and target really are past
their thresholds at that tick (read back from recorded state); traces are acyclic, follow
declared edges and never put a cause after its effect; traces are identical across runs; and
every counterfactual verdict matches an independent replay without the decision. Plus five
targeted cases (decision blamed, initial condition, acute radiation, harmless flare not blamed,
natural cascade with no decision roots). 35 tests, all passing; 4 failed on the checkpoint
(B2, B3).

## Future Lens quality

`quality` command, 24 mission states from 3 balanced missions (seeds 1–3, ticks 20–200), 10 single-decision
candidates each (240 candidate cases, 432 predictions):

| Measure | Result |
|---|---|
| Deterministic (same input → byte-identical output) | Yes, every case |
| Isolated (real state unchanged) | Yes, every case |
| Candidates indistinguishable from the baseline over 24 h | 32.5 % overall. Heater eco: 100 %; rover charger off: 87.5 %; comms eco / habitat core eco: 62.5 %; shelter: 12.5 %; rations, CO₂ scrubber eco, O₂ off, water recovery off, setpoint 15 °C: 0 % |
| Candidate named in the causal explanation when it introduces a new warning | 77.8 % (21 of 27). The 6 misses: explanations cover the first 3 warnings *by time*, which were warnings the baseline also had |
| Confidence by horizon | 6 h: 0.628 (high) · 24 h: 0.51 (medium) · 72 h: 0.336 (low) · 144 h (clipped to 105): 0.276 (low) |
| Calibration (24 h, `known_only`) | 23 of 24 "medium", 1 "high"; end-risk error 0.0 without hidden events, ≤ 0.021 with |
| Sample stability (1 vs 4 vs 16 samples) | Median end risk identical; max spread 0.00012 |
| Surprise blindness (`known_only` vs what happened) | 12 of 24 projections had a hidden event in the horizon. Mean dose error 3.33 mSv (max 10.67, the SPE); water-days error ≤ 0.18 (pump fault); 0 without hidden events |

Interpretation (measure, don't redesign): the lens is honest and stable, but its confidence is
effectively a function of the horizon (the spread term is ~1), and its risk index cannot see
radiation (D22). Many single toggles look identical to doing nothing over 24 h, partly because
internal heat dominates heating needs until night. Options are recorded under D6.

## Black Box quality

15 failure cases: 5 injected (scrubber off, water recovery off with low reserves, O₂
generation off, an extreme SPE, cold and hungry with an irrelevant comms decision) plus the
first 5 crew-loss missions each from high-risk and random play. Each traced with
counterfactuals, twice.

| Defect checked | Total |
|---|---|
| Cyclic chains | 0 |
| Order violations (cause after effect) | 0 |
| Undeclared edges | 0 |
| Missing context (a known cause absent) | 0 |
| Unexplained failures | 0 |
| Unstable traces (differ between runs) | 0 |
| Irrelevant blame (decision root whose counterfactual shows no effect) | 2 of 57 decision roots |

Both "irrelevant blame" roots are in one random-play mission (`random_valid:3`), an
over-determined failure: each decision is on a real causal path, but the crew is lost even
without it. The trace reports this correctly as `no_effect`; a UI must show the verdict (see
[BLACK_BOX.md](BLACK_BOX.md#reading-a-verdict-on-the-path-vs-necessary)). The injected
irrelevant comms decision is correctly not blamed.

Seven traces are pinned as regression fixtures (`tests/fixtures/black_box/*.json`,
`tests/test_black_box_regression.py`): any change to their chains or roots fails the build.

## State invariants and fuzzing

* `app/simulation/engine/invariants.py` checks every state for finite numbers,
  physical bounds, flow consistency, monotone counters, phase order and outcome consistency
  (full list in [SIMULATION_MODEL.md](SIMULATION_MODEL.md#4a-state-invariants)).
* **Strict sweep:** 10 strategies × 500 seeds with invariants checked after every tick:
  5,000 missions, 1,174,210 states checked, **0 violations**.
* **Property/fuzz suite** (`tests/test_invariants_and_fuzz.py`; `HYPOTHESIS_PROFILE=fuzz` runs
  500 examples per property): arbitrary decision sequences (valid and invalid) keep every
  invariant, are deterministic, hash-chain and replay exactly, and every fork point reproduces
  its recorded state; random parameter perturbations (battery 5–2,000 kWh, solar 0.5–60 kW,
  food 0–300 kg, conductance 0.001–0.2, tick 0.25–6 h, fault probability 0–1, shielding 0–1)
  keep states valid. Results are in [TESTING.md](TESTING.md#property-and-fuzz-testing).
* Genuine bugs found: B1 only.

## Performance

See [TESTING.md](TESTING.md#performance-at-scale). In short: ~37 ms of engine time per 240-tick
mission; ~60–65 ms per mission end to end with a strategy on 2 workers; 10,000 missions in
647 s with a 100 MB peak.
