# Black Box and Root-Cause Tracing (Mission Trace)

The Black Box is the mission's flight recorder. Everything in it is **reconstructed**:
initial state + decision ledger → deterministic replay (with every decision's before/after hash
verified) → per-tick history → analysis. Nothing is inferred from free text.

Implementation: `app/simulation/analysis/black_box.py`, `root_cause.py`, `reconstruct.py`.
Endpoints: `GET /mission-sessions/{id}/black-box/summary` (frontend-safe projection,
[API_CONTRACT.md](API_CONTRACT.md#black-box)); internal raw views `GET /mission-sessions/{id}/black-box`
and `GET /mission-sessions/{id}/trace`.

## Report contents

| Section | Content |
|---|---|
| `decisions` | Every ledger decision: id, sequence, tick, phase, type, inputs, affected systems |
| `timeline` | Every event, categorised: `alert`, `failure`, `milestone`, `phase`, `decision`, `outcome`, `event` |
| `alerts`, `failures`, `milestones`, `phase_transitions` | Filtered views. Failures include faults, crew incapacitation, rover loss and failed outcomes |
| `resource_trends` | 13 series (battery, generation, demand, temperature, O₂/water/food days, CO₂, crew health and dose, science, data, risk): sampled every 4 ticks plus the last tick, with exact min/max and when |
| `causal_traces` | Root-cause traces for: crew loss (traced from `crew.min_health`), the first occurrence of every *critical* alert, otherwise the peak of `risk.mission` (if ≥ 0.2); plus the traces the outcome analysis needs. At most 6 + one per failed objective |
| `outcome_analysis` | Phase 3: why the mission ended in its tier, objective by objective (below) |
| `outcome`, `status`, `final_tick`, `final_state_hash` | |

## Outcome analysis (Phase 3)

`app/simulation/analysis/outcome_analysis.py`. With the v0.2.0 pillars a mission can fail while
the crew is safe, so "trace `crew.min_health`" no longer explains every failure. For every
FAILED objective the report gives a `FailureChain`:

| Field | Meaning |
|---|---|
| `triggers` | The **triggering condition**: the objective's own rule and the recorded value that met it at the resolution tick (`fail_when`), or the unmet target at the end (`achieve_when`), e.g. `power.unmet_kw > 0.05 (= 1.33 at tick 240)` |
| `root_decisions` | **Root decisions**, only those whose removal, by counterfactual replay, makes the triggering metric better (`decision_worsened_target`) |
| `on_path_no_effect` | Decisions on a causal path whose removal changes nothing (over-determined failures). Reported, **never blamed** |
| `other_roots` | Non-decision causes: scenario events, environment, random faults, initial conditions |
| `intermediate_effects` | The **intermediate system effects**: metrics on the traced chains between roots and trigger |
| `consequence` | The **final mission consequence**: which better outcome tier the failure blocked |
| `kind` | `traced` (degraded-state chain), `omission` (science and data objectives: recorded facts such as "campaign never started", "data produced but not downlinked", link outages) or `untraced` |

`blocked_tiers` maps each better tier to the objectives that blocked it, e.g. a balanced mission
that ran the battery empty: `{"exceptional": ["power_continuity", "reserves_at_end"], "success":
["power_continuity"]}`.

Science and data objectives have no severity scale (more is better, there is no "degraded"
value), so they are explained by recorded facts, not by a causal chain. Nothing is inferred
beyond the recorded history and the declared dependency graph.

## How a trace is built

Given a target `(metric, tick)` and the replayed history:

1. For each parent edge of the node in the [dependency graph](SIMULATION_MODEL.md#4-dependencies),
   look back (default 72 ticks) for the latest contiguous run where the parent's **severity ≥
   0.2**. If found, the parent is a contributing cause. The edge records evidence: onset tick,
   worst tick, peak severity, and the anchor tick on the target.
2. Recurse from the parent's **onset** tick, so causes always precede or coincide with their
   effects (tested). Exception (Phase 2): a parent already degraded when the record starts has no
   observable onset. It gets an explicit `scenario:initial:<metric>` cause ("already degraded
   when the record starts"), and its causes are searched up to its *worst* tick (still ≤ the
   effect's anchor). Without this, a decision that made an already-low reserve worse (e.g.
   water recovery switched off with low starting water) was hidden behind "normal
   consumption".
3. Leaf nodes are resolved through **provenance** stored in the state: which decision, scenario
   event, random fault or scenario default set that value. Examples: a mode setting →
   `decision:<id>`; component damage → `event:water_processor_pump_fault` or
   `fault:<component>:<tick>`; low sunlight → `environment:solar_availability` (natural
   profile); a blocked downlink → `event:relay_outage`.
4. Nodes with no degraded parent get a `baseline` cause ("driven by this subsystem's own
   dynamics, e.g. normal consumption"). The tracer does not invent a culprit.
5. **Counterfactual check** (default on): for each decision root, the mission is replayed with
   the same seed and all other decisions, *without* that one. The target metric is compared and
   a verdict is attached: `decision_worsened_target`, `decision_improved_target` or
   `no_effect`.

Output: `RootCauseTrace {target_metric, target_tick, target_value, target_severity, nodes,
edges, roots, chains, parameters}`. `chains` lists root → … → target paths.

### Example (tested)

A player switches the CO₂ scrubber off at tick 5 (seed 42). The crew is lost at tick 112. The trace is
**not** "decision X caused mission failure". It is:

```
decision:dec_…  (set_subsystem_mode co2_scrubber=off, tick 5)
  → metric:control.mode.co2_scrubber       "Scrubber mode sets its removal rate"
  → metric:life_support.co2_ppm            degraded from tick 40, peak severity 1.0
  → metric:crew.min_health                 "High CO2 impairs and harms the crew"
counterfactual at tick 112: crew.min_health 0.0 with the decision, 1.0 without
                → decision_worsened_target
```

Every edge in a trace is either a declared dependency-graph edge or a provenance link into a
metric (tested), so traces only contain mechanisms the model actually has.

## Regression fixtures and their Phase 3 changes

Seven failure traces are pinned (`tests/fixtures/black_box/`). Phase 3 changed three, each for a
documented reason (`ODYSSEY_REGEN_FIXTURES=1` was run only after the diff was reviewed):

| Fixture | Change | Why |
|---|---|---|
| `cold_and_hungry_with_irrelevant_comms` | Inputs rebuilt: 20 kg food and the solar particle event neutralised (×1); crew loss at tick 226 instead of 153; the ration decision's verdict is now `no_effect` | The v0.2.0 cold penalty makes a 10 °C cabin on half rations survivable for 10 days (health ends ≈ 0.3), so the case no longer tested what it was built for: a decision-driven crew loss with an irrelevant comms decision mixed in. With less food it is again a decision-driven crew loss (thermostat verdict `decision_worsened_target`). The ration cut is over-determined (the crew starves either way with 20 kg), which the verdict states honestly. The comms decision is still not blamed (tested) |
| `random_valid_1` | Crew loss at tick 190 instead of 191; same roots and chains | v0.2.0 numbers (battery, array, oxygen, wear) change this random mission slightly |
| `high_risk_1` → `high_risk_2` | Replaced | The fixture takes high-risk play's first crew loss in seeds 1–4. In v0.2.0, seed 1 no longer loses the crew (partial success with an injured crew), so the first crew loss is seed 2 |

`extreme_solar_particle_event` also changed during Phase 3 development, then returned to
byte-identical once the false `crew.max_dose_msv → crew.min_health` edge was removed (see
[SIMULATION_MODEL.md](SIMULATION_MODEL.md#4-dependencies)). The remaining three
(`scrubber_off`, `water_off_low_reserves`, `oxygen_generation_off`) are unchanged.

## Mission Trace on demand

`GET /trace?metric=<any metric>&tick=<any tick>` traces any quantity at any point, e.g. "why was
water recovery low at tick 180?". The metric catalogue is at `/missions/{id}/metrics`.

## Reading a verdict: on the path vs necessary

A decision root means the decision set a value that was degraded on a declared causal path.
The counterfactual verdict says whether removing it changes the target. These can differ. In
an **over-determined** failure (several sufficient causes), a contributing decision gets
`no_effect` because the crew is lost either way. In the Phase 2 quality run this happened for
2 of 57 decision roots (15 failure cases), both in one random-play failure. Anything that
displays a trace must show the verdict next to each decision. See
[BALANCING_FINDINGS.md](BALANCING_FINDINGS.md#black-box-quality).

## Limits and cost

* Severity thresholds and lookback are parameters (returned in `parameters`), not truths.
  A trace shows *recorded* degraded states along declared mechanisms; it does not quantify
  how much each cause contributed. Counterfactuals give that verdict only for decisions.
* Cost: a 240-tick, 22-decision reconstruction ≈ 0.15 s; the Black Box with counterfactuals
  ≈ 0.3 s (one extra replay per decision root, max 5 per trace, memoised).
