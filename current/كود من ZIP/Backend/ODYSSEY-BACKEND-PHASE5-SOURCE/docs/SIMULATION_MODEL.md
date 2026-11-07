# Simulation Model

ODYSSEY's engine (`app/simulation/`) is an **educational abstraction** of a lunar outpost, not
an aerospace-grade simulator. Its job is to make real engineering trade-offs *visible and
explainable* with equations simple enough to state on one page, every one of them
deterministic.

All balancing numbers quoted here are LUNA-01 v0.1.0 values and are **provisional**
([D1](USER_DECISIONS_REQUIRED.md#d1-scenario-balancing)). They live in
`app/simulation/scenarios/data/luna-01.yaml`, not in code. How these numbers actually play
out across strategies and seeds is measured in [BALANCING_FINDINGS.md](BALANCING_FINDINGS.md).

## 1. Time

* One **tick** = `time.tick_hours` (LUNA-01: 1 h). Δt below is in hours.
* A mission lasts at most `time.max_ticks` ticks (LUNA-01: 240 = 10 days).
* `state.tick = t` means "the instant between step t-1 and step t". Decisions recorded at tick
  *t* are applied **before** the step *t → t+1*. Events emitted during that step carry
  `tick = t`.

### Order of one step (t → t+1)

1. Scenario events (scheduled → state-triggered → random), in scenario order
2. Environment (natural profile + event modifiers)
3. Power (dust, generation, rover transfer, demand, priority allocation, battery)
4. Thermal
5. Life support (water, O₂, CO₂) and food
6. Communications, then science
7. Rover
8. Crew (radiation dose, EVA, fatigue, health)
9. Degradation, random faults, maintenance
10. `tick += 1`, then alerts → cascade warnings → objectives → outcome → phase advance

Systems read values written earlier in the same step, so the order is part of the model. For
example, thermal uses this tick's power allocation, and the heater demand uses last tick's
internal heat.

## 2. Modelled quantities

| Quantity | Unit | State field | Notes |
|---|---|---|---|
| Solar availability | fraction 0–1 | `environment.solar_availability` | Keyframed profile × event modifiers |
| Radiative sink temperature | °C | `environment.sink_temp_c` | Effective environment temperature |
| Surface dose rate | mSv/h | `environment.radiation_dose_rate_msv_h` | Unshielded |
| Earth link geometry | bool | `environment.earth_visible` | Step function |
| Array dust transmission | fraction | `power.dust_factor` | Decays, restored by cleaning EVA |
| Solar generation | kW | `power.generation_kw` | |
| Battery energy | kWh | `power.battery_charge_kwh` | Capacity shrinks with battery health |
| Per-load demand / allocation | kW | `power.consumers[*]` | `supply_ratio = allocated/demand` |
| Habitat temperature | °C | `thermal.habitat_temp_c` | Lumped thermal mass |
| Oxygen | kg | `life_support.oxygen_kg` | Storage cap `oxygen_capacity_kg` |
| Cabin CO₂ | kg (→ ppm) | `life_support.co2_kg` | ppm = kg × `co2_ppm_per_kg` |
| Water | kg | `life_support.water_kg` | |
| Water recovery efficiency | fraction | `life_support.water_recovery_efficiency` | Effective, this tick |
| Food | kg | `food.food_kg` | Ration level 0.5–1 |
| Crew health, fatigue | index 0–1 | `crew[*].health`, `fatigue` | Abstract, **not physiology** |
| Crew dose | mSv | `crew[*].dose_msv` | Cumulative |
| Component health | index 0–1 | `components[*].health` | Wear + faults, restored by maintenance |
| Science return | points | `science.points` | Abstract |
| Science data | MB | `science.data_pending_mb`, `comms.data_downlinked_mb` | |
| Rover battery | kWh | `rover.battery_kwh` | |

Derived quantities are exposed as **metrics** (83 for LUNA-01 v0.2.0, 79 for v0.1.0, listed by
`GET /api/v1/missions/luna-01/metrics`), e.g. `life_support.oxygen_days` = O₂ / (crew × daily
use), `power.battery_soc`, and the composite `risk.mission`.

## 3. Equations

### 3.1 Environment

```
base_x(t) = piecewise-linear interpolation of keyframes (earth_visible: step function)
x(t)      = base_x(t) with active modifiers applied in (start_tick, event_id) order
            multiply: x *= v     add: x += v     set: x = v
solar_availability ∈ [0, 1];  dose_rate ≥ 0;  earth_visible = (x ≥ 0.5)
```

LUNA-01: sunlight declines 0.85 → 0 between ticks 40 and 210 ("the last light"), the sink
cools from −45 °C to −185 °C, and the baseline dose rate is 0.057 mSv/h (Chang'E-4 LND).
Concurrent `multiply` modifiers compound: a minor flare (×5) during the solar particle event
(×40) gives ×200 ([D21](USER_DECISIONS_REQUIRED.md#d21-overlapping-radiation-events)).

### 3.2 Power

```
dust(t+1)    = max(dust_floor, dust(t) − deposition · m_dust)
P_gen        = P_rated · solar_availability · dust · perf(solar_array)
demand_i     = nominal_i · mode_factor_i
               heater:      clamp(UA·(setpoint − T_sink) − Q_internal(prev)
                                  + k·max(0, setpoint − T), 0, max) · mode_factor
               science:     only while an activity runs
               rover charger: only while docked, not full, and not transferring this tick
               any load whose component is under maintenance: 0
P_rover      = min(transfer_kw, E_rover/Δt) · η_transfer     (rover → bus, when enabled)
P_batt_max   = min(max_discharge · perf(battery), E_batt · η_dis / Δt)
allocation   = greedy by (priority, id): a_i = min(demand_i, remaining)
surplus s    = P_gen + P_rover − Σa  → E += min(s, max_charge·perf, headroom) · η_ch · Δt
deficit d    = Σa − P_gen − P_rover → E −= d / η_dis · Δt
capacity     = capacity_rated · max(0.05, health(battery))
```

Load shedding is therefore implicit and **priority-ordered**: habitat core (0), CO₂ removal
(1), O₂ generation and heaters (2), water recovery (3), comms (4), science (5), rover
charger (6).

### 3.3 Thermal (single lumped mass)

```
Q_internal = f_internal · (Σ allocated − allocated_heater)
Q_heater   = allocated_heater · perf(heater)
Q_loss     = UA · (T − T_sink)
T'         = T + (Q_heater + Q_internal − Q_loss) · Δt / C
if T' > setpoint: T' = max(setpoint, min(T', T) − relax·Δt)   (active cooling)
```

### 3.4 Life support and food (n = crew with health > 0)

```
O2_req = n·0.818·Δt/24   CO2_prod = n·1.04·Δt/24   W_use = n·4.35·Δt/24   (kg)
f_T      = clamp((T − T_zero)/(T_min − T_zero))                (cold processor)
η        = η_nominal · min(mode,1) · supply · perf · f_T
W        = W − W_use + η · W_use
O2_gen   = min(cap·Δt·mode·supply·perf,  W / 1.125,  O2_max − O2 + O2_req)
W       −= O2_gen · 1.125                                     (electrolysis)
O2       = max(0, O2 + O2_gen − O2_req)
removed  = min(cap_CO2·Δt·mode·supply·perf, max(0, CO2 − floor))
CO2      = CO2 + CO2_prod − removed
Food    −= n · 1.51 · Δt/24 · ration_level
```

### 3.5 Communications and science

```
link_up   = earth_visible ∧ comms_output ≥ 0.5
downlink  = min(pending, rate·Δt·comms_output)
science output = science_consumer_output · crew_factor
crew_factor    = health of science officer in habitat (else ½ · best crew in habitat)
progress += output; points += points_per_tick · output; data += data_per_tick · output
```

Opportunities open via events and are **missed** when their window closes.

### 3.6 Rover (tele-operated)

```
DOCKED ⇄ STOWED,  DOCKED → TRAVERSING → (site work) → RETURNING → DOCKED,  any → LOST
draw = traverse_kw · Δt   (¼ while halted without a comms link)
P(loss per tick) = p_loss · (1 − health)       seeded stream "rover_loss"
battery exhausted away from base → LOST (stranded)
```

### 3.7 Crew (abstract health index)

```
received = dose_rate · shielding(location)     habitat 0.6, shelter 0.15, EVA 1.0
dose    += received · Δt
penalty  = k_rad·max(0, received − 0.5)·Δt
         + k_hyp·(1 − O2_gen/O2_req)   when the O2 reserve is empty
         + k_co2·clamp((ppm − 5300)/(10500 − 5300))
         + k_cold·max(0, 15 − T)
         + k_dehyd (no water) + k_starve (no food) + k_ration·(1 − ration)
health   = clamp(health − penalty)  or  health + recovery  when penalty = 0
```

EVA (array cleaning) exposes one crew member for `eva_ticks`, adds fatigue, then restores the
dust factor to `dust_after_cleaning`. A shelter order skips crew on EVA, and a member returning
from EVA always goes to the **habitat**, even if the rest of the crew is sheltered (open decision
[D19](USER_DECISIONS_REQUIRED.md#d19-where-an-eva-crew-member-returns-during-a-radiation-event)).

The metric `crew.received_dose_rate_msv_h` (highest received rate after shielding) is the
quantity the acute penalty acts on. Its severity starts exactly at the 0.5 mSv/h threshold.
Cumulative dose (`crew.max_dose_msv`) drives the radiation-safety objective, not acute harm, so
the dependency graph has **no** edge from cumulative dose to crew health (Phase 3 removed one
that contradicted this model).

LUNA-01 v0.2.0 penalty constants: `k_cold` = 0.0004 per K per hour (v0.1.0: 0.001; at 0.001 a
10 °C cabin was as harmful as having no food at all, see
[PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md#changes-in-v020)), `k_starve` 0.005, `k_dehyd`
0.02, `k_hyp` 0.08, `k_co2` 0.01, `k_ration` 0.002 per hour; recovery 0.002 per hour.

**Dose budget (scenarios with `radiation.dose_limit_msv`, LUNA-01 v0.2.0: 15 mSv).** What a
dosimeter and the mission plan already tell the crew, using only the scenario's *baseline* dose
rate (no knowledge of future space weather):

```
dose_margin            = limit − max crew dose
projected_dose(t)      = max dose of active crew + Σ_{k ≥ t} baseline_rate(k) · 0.6 · Δt
projected_dose_margin  = limit − projected_dose        (habitat shielding 0.6)
```

Alerts on these metrics (`dose_budget_low` < 2 mSv, `dose_budget_exceeded` < 0) and a
`radiation_above_background` caution (> 0.12 mSv/h, so a ×5 flare at 0.285 mSv/h is visible below
the 0.5 mSv/h warning) give the player measurable warning before the radiation objective fails.

### 3.8 Degradation and maintenance

```
wear   = wear_per_tick · (boost_wear_multiplier if a consumer using it is in BOOST)
                       · (deep_discharge_multiplier for the battery below 15 % SOC)
fault  ~ Bernoulli(fault_probability · (1 − health))   seeded stream "fault:<component>"
perf(component) = floor + (1 − floor) · health;  0 while under maintenance
maintenance: offline for maintenance_ticks, then health += maintenance_restore
E_batt  = min(E_batt, capacity(health))      after wear/faults (capacity fade loses energy)
```

### 3.9 Alerts, cascades, risk

* **Alerts**: threshold rules on metrics with **hysteresis** (`clear_threshold`).
* **Severity**: each analysable metric maps to 0 (nominal) … 1 (critical) via
  `(nominal − value)/(nominal − critical)`, clamped.
* **Cascade warning**: a dependency edge is *active* when source severity ≥ 0.5 and target
  severity ≥ 0.3. Newly active edges produce one warning per source node.
* **Composite risk**: `risk.mission = 1 − Π (1 − wᵢ · severityᵢ)` over the scenario's risk
  terms. An educational indicator, **not** a probability of failure. LUNA-01's terms cover
  oxygen, CO₂, water, food, temperature, battery and crew health, and since v0.2.0 the
  projected dose margin (weight 0.6, provisional:
  [D22](USER_DECISIONS_REQUIRED.md#d22-what-the-mission-risk-index-includes)).

### 3.10 Objectives and outcomes (LUNA-01 v0.2.0)

Objectives belong to **pillars** (`category`). Outcome rules are tried in order and combine
pillars, so no single action or pillar gives full success:

| Pillar | Objectives (v0.2.0) |
|---|---|
| primary (required) | crew survival; two science campaigns completed; ≥ 800 MB returned to Earth |
| safety | crew dose < 15 mSv; crew health stays ≥ 0.5 |
| stability | no forced load shedding (unmet power ≤ 0.05 kW); no life-support crisis (CO₂ > 10,500 ppm, O₂ or water < 1 day, habitat < 5 °C) |
| efficiency | at the end: ≥ 3 days O₂ and water, ≥ 15 % battery |
| science | ≥ 100 science points |
| discovery | all three campaigns completed |

```
crew loss                                       → mission_failed_crew_loss    (critical failure)
any primary objective failed (at the end)       → mission_failed              (crew may be safe)
primary + safety + stability + efficiency + science → mission_complete_exceptional
primary + safety + stability                    → mission_complete            (success)
primary                                         → mission_complete_partial    (partial)
otherwise                                       → mission_failed              (catch-all)
```

Achieve-type objectives still pending at the end become FAILED; at-end objectives are evaluated
on the final state. The mechanism (`category`, `tier`, `requires_categories`,
`min_achieved_in_categories`, `any_failed_in_categories`) is opt-in: v0.1.0 has no categories,
and its outcomes replay byte-identically (`tests/test_scenario_compat.py`).

## 4. Dependencies

The dependency graph (`app/simulation/engine/dependency_graph.py`, 73 edges / 50 nodes for
LUNA-01 v0.2.0; 69 / 47 for v0.1.0) declares *how* quantities influence each other, each edge with a physical mechanism.
The spec's example chain exists edge-for-edge and is tested:

```
env.solar_availability → power.generation_ratio → power.battery_soc
→ power.supply_ratio.thermal_heater → thermal.habitat_temp_c
→ life_support.water_recovery_efficiency → life_support.water_days → crew.min_health
→ risk.mission
```

`env.*` and `control.*` nodes are roots (set by the environment or by decisions). The graph is
acyclic (tested). It powers cascade warnings, root-cause tracing ([BLACK_BOX.md](BLACK_BOX.md))
and what ORION may cite.

Phase 2 added `env.radiation_dose_rate_msv_h → crew.received_dose_rate_msv_h → crew.min_health`,
so acute radiation harm is traced through the mechanism that causes it, not through cumulative
dose (which only correlates).

Phase 3 changes:

* **Removed** `crew.max_dose_msv → crew.min_health`. Accumulated dose has no health effect in
  this model; the edge was never traversed in v0.1.0 (no severity scale), but v0.2.0 gives
  cumulative dose a scale and the Black Box began citing it as a cause. That was fabricated
  causality.
* **Added** `crew.received_dose_rate_msv_h → crew.max_dose_msv` (dose accumulates from the
  received rate); `power.battery_soc → power.unmet_kw` and `power.generation_ratio →
  power.unmet_kw` (forced load shedding); `comms.link_up → comms.data_downlinked_mb`,
  `power.supply_ratio.science_payload → science.points`, `crew.in_shelter → science.points`
  (science delivery); and, only when a dose limit is declared, `crew.max_dose_msv →
  crew.dose_margin_msv`, `crew.max_dose_msv → crew.projected_dose_msv → crew.projected_dose_margin_msv`.

## 4a. State invariants

`app/simulation/engine/invariants.py` defines what a valid state is. The fuzz suite and the
Balancing Lab's `--strict` mode check every state after every step:

* every number finite; battery 0 ≤ E ≤ capacity(health); rover 0 ≤ E ≤ its capacity;
  0 ≤ O₂ ≤ storage; CO₂, water, food, generation, unmet load, science ≥ 0
* dust, ration, setpoint and water-recovery efficiency inside their scenario ranges;
  per consumer 0 ≤ allocated ≤ demand, 0 ≤ supply ≤ 1
* crew health and fatigue in [0, 1], dose ≥ 0, EVA flag ⇔ EVA ticks remaining; component
  health in [0, 1]
* at most one active habitat science activity; tick ≤ max_ticks; known phase; ordered phase
  history; alerts ⊆ rules; event fire counts ≤ max_fires; no expired modifier; concluded ⇔
  outcome recorded
* between consecutive states: tick +1 exactly; dose, science points, downlinked data, decision
  count and event fire counts never decrease; resolved objectives never change; the phase never
  moves backwards

## 5. Determinism

* **No hidden randomness.** Every random draw is `uniform(seed, stream, tick, index)`:
  BLAKE2b of the four values → 64-bit integer → [0, 1). Draws are a *pure function*, so
  adding a new random event never perturbs existing ones, and replays/forks reproduce draws
  regardless of order. Reference values are pinned by tests.
* **Engine purity.** `step`, `advance` and `apply_decision` deep-copy their input and return
  new states. Tests assert inputs are never mutated.
* **Canonical hashing.** States, ledger records, decision ids and Mission DNA are hashed from
  canonical JSON (sorted keys, floats rounded to 9 decimals, −0.0 normalised, NaN rejected).
* **Verified.** Identical state, event, Black Box and Future Lens hashes across separate
  processes with different `PYTHONHASHSEED`s. Property-based tests replay random decision
  sequences.
* **Pinned scenarios.** Sessions store the scenario's content hash, so a re-balanced scenario
  never changes how an old session replays.

## 6. Simplifications and assumptions

* Single habitat volume, single thermal node, no thermal stratification or radiators' geometry.
* Solar availability is a scripted profile (south-pole illumination is not computed from
  ephemerides); dust is a uniform transmission loss.
* Battery is an energy bucket with charge/discharge efficiency and rate limits (no voltage,
  temperature or SOC-dependent efficiency).
* Life support is mass-balance only (no partial pressures, humidity, trace contaminants;
  hydrogen from electrolysis is vented; no Sabatier).
* Crew health is a single abstract index. **It is not a physiological model.** Radiation
  "health" effects are acute-dose abstractions for gameplay. Cumulative dose is tracked
  separately for the safety objective.
* Communications are on/off with a fixed downlink rate; no link budget.
* Science is abstract points/data; the rover is tele-operated and uncrewed.

## 7. Boundaries (deliberately not modelled)

Orbital mechanics, landing dynamics, structural loads, micrometeoroids, medical events,
psychology, EVA suit consumables, in-situ resource utilisation, and multi-habitat logistics.
Adding any of these is a scenario/engine extension, not a rewrite: systems are independent
functions over `TickContext`.

## 8. Evidence

Constants marked `[evidence]` in the scenario map to entries in
`app/science/data/evidence.yaml` (`GET /api/v1/science/evidence`), each with source,
retrieval date, verification status, simplification and confidence. Two entries are still
`unverified` ([D15](USER_DECISIONS_REQUIRED.md#d15-unverified-scientific-evidence)).
