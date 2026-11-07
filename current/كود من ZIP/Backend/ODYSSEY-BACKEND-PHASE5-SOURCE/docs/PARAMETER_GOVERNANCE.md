# Parameter Governance

Every adjustable LUNA-01 parameter, classified so that balance is built **around** the science
and never by rewriting it. Scenario file: `app/simulation/scenarios/data/luna-01.yaml`
(v0.2.0). Evidence details: [SCIENCE_EVIDENCE_AUDIT.md](SCIENCE_EVIDENCE_AUDIT.md).

| Class | Meaning | May Phase 3 change it? |
|---|---|---|
| **EVIDENCE_LOCKED** | Value taken directly from a cited NASA or other scientific source and checked in the audit | **No.** Enforced by `tests/test_parameter_governance.py` (value = evidence registry value) and by the balance search, which refuses these paths |
| **EDUCATIONAL_ABSTRACTION** | A simplified representation of a real system (lumped models, engineering sizing) | Only with a plausibility reason that is not "it improves the success rate", recorded below |
| **GAMEPLAY_PARAMETER** | Mission configuration that shapes the challenge (initial reserves, timings, thresholds) | Yes, with evidence from the Balancing Lab (search, sweeps, sensitivity), recorded in [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md) |
| **UNVERIFIED** | Not supported strongly enough to treat as scientific truth | No silent changes. Story-central values stay until sourced ([D15](USER_DECISIONS_REQUIRED.md#d15-unverified-scientific-evidence)) |

Paths the balance search refuses (`app/simulation/analysis/balancing/search.py`,
`PROTECTED_PATHS`): `life_support.o2_consumption_kg_per_crew_day`,
`life_support.co2_production_kg_per_crew_day`, `life_support.water_use_kg_per_crew_day`,
`life_support.water_per_kg_o2`, `life_support.water_recovery_nominal`,
`food.consumption_kg_per_crew_day`, `environment.radiation_dose_rate_msv_h` (all
EVIDENCE_LOCKED), plus `environment.sink_temp_c`, `environment.solar_availability`, `events` and
`phases` (protected story environment and scripted timing).

"Changed" below means changed in v0.2.0 relative to v0.1.0.

## EVIDENCE_LOCKED

| Parameter | Value | Evidence | Phase 3 may modify | Rationale |
|---|---|---|---|---|
| `life_support.o2_consumption_kg_per_crew_day` | 0.818 | `bvad_o2_consumption` (BVAD, verified secondary) | No | Physiology; the mass balance students learn from |
| `life_support.co2_production_kg_per_crew_day` | 1.04 | `bvad_co2_production` (BVAD, verified secondary) | No | Physiology |
| `life_support.water_use_kg_per_crew_day` | 4.35 | `bvad_water_total` (BVAD, verified secondary) | No | Physiology |
| `food.consumption_kg_per_crew_day` | 1.51 | `bvad_food_mass` (verified secondary; attribution issue noted in the audit) | No | Physiology |
| `life_support.water_per_kg_o2` | 1.125 | `electrolysis_stoichiometry` (first principles) | No | Chemistry |
| `life_support.water_recovery_nominal` | 0.93 | `iss_water_recovery` (verified secondary) | No | ISS heritage performance |
| `environment.radiation_dose_rate_msv_h` (baseline keyframe) | 0.057 mSv/h | `change4_lnd_dose_rate` (verified secondary) | No | Measured lunar surface dose rate |

## UNVERIFIED

| Parameter | Value | Evidence | Phase 3 may modify | Rationale |
|---|---|---|---|---|
| `environment.solar_availability` keyframes | 0.85 → 0 over ticks 40–210 | `lunar_polar_illumination` (unverified) | No | The mission's premise ("the last light"). Must be sourced, not tuned |
| `crew_health.co2_warning_ppm`, `crew_health.co2_critical_ppm` (and the matching alert and stability thresholds) | 5300 / 10500 ppm | `co2_crew_limits` (unverified) | No | Changing an unsourced limit to tune balance would be worse than leaving it; sourcing is D15 |
| `events.solar_particle_event` existence | scheduled SPE | `donki_sep_events` (not re-checked) | No (timing/magnitude are GAMEPLAY but protected story content) | Event catalogue existence only |

## EDUCATIONAL_ABSTRACTION

| Parameter | Value | Evidence | Phase 3 may modify | Rationale / Phase 3 action |
|---|---|---|---|---|
| `environment.sink_temp_c` keyframes | −45 → −185 °C | Informed by `diviner_surface_temperature` extremes | No (protected) | Abstraction of radiator sink, kept |
| `thermal.conductance_kw_per_k` | 0.015 | none | Yes, with reason | Unchanged. Internal electrical heat keeping a well-insulated habitat warm is a correct lesson ("your electronics are your heater"); load shedding already makes it cold |
| `thermal.capacitance_kwh_per_k`, `internal_heat_fraction`, `heater_max_kw`, `heater_gain_kw_per_k`, `overheat_relaxation_k_per_hour` | 5.0, 0.8, 6.0, 0.5, 1.0 | none | Yes, with reason | Unchanged |
| `life_support.co2_ppm_per_kg` | 5500 | Derivation (100 m³ cabin, ideal gas; audit re-did the arithmetic) | Yes, with reason | Unchanged |
| `life_support.co2_floor_kg`, `water_recovery_min_temp_c`, `water_recovery_zero_temp_c` | 0.3, 10, 0 | none | Yes, with reason | Unchanged |
| `life_support.o2_generation_capacity_kg_per_hour`, `co2_removal_capacity_kg_per_hour` | 0.16, 0.22 | Engineering sizing above 4-crew demand | Yes, with reason | Unchanged |
| `power.consumers.*.nominal_kw`, `mode_factors`, `priority` | see scenario | Engineering placeholders | Yes, with reason | Unchanged |
| `power.battery.charge_efficiency`, `discharge_efficiency`, `max_charge_kw`, `max_discharge_kw`, `deep_discharge_soc` | 0.95, 0.95, 8, 12, 0.15 | Engineering placeholders | Yes, with reason | Unchanged |
| `power.dust_deposition_per_tick`, `dust_floor`, `decisions.dust_after_cleaning` | 0.0006, 0.5, 0.98 | Abstraction of lunar dust | Yes, with reason | Unchanged |
| `radiation.habitat_shielding_factor`, `shelter_shielding_factor`, `eva_shielding_factor` | 0.6, 0.15, 1.0 | none | Yes, with reason | Unchanged |
| `radiation.health_threshold_msv_per_hour`, `health_penalty_per_msv` | 0.5, 0.02 | Acute-harm abstraction, not physiology | Yes, with reason | Unchanged |
| `crew_health.cold_threshold_c` | 15 °C | [WHO Housing and Health Guidelines (2018), ch. 4](https://www.ncbi.nlm.nih.gov/books/NBK535294/): 18 °C recommended minimum; blood-pressure risk higher below 16 °C (OR 4.92); "evidence is insufficient to establish the precise temperature" | Yes, with reason | Unchanged: placement is consistent with the evidence |
| `crew_health.cold_penalty_per_k_tick` | **0.0004** (was 0.001) | WHO 2018 gives no time course or lethality at moderate cold | Yes, with reason | See [Changes](#changes-in-v020) |
| Other `crew_health.*` penalties and recovery | see scenario | Abstract health index | Yes, with reason | Unchanged |
| `degradation.components.*.performance_floor`, `deep_discharge_wear_multiplier` | see scenario | Engineering abstraction | Yes, with reason | Unchanged |

## GAMEPLAY_PARAMETER

| Parameter | Value | Evidence | Phase 3 may modify | Rationale / Phase 3 action |
|---|---|---|---|---|
| `time.tick_hours`, `time.max_ticks` | 1 h, 240 | Mission design (D2) | Yes | Unchanged |
| `crew` (4 roles) | 4 | Mission design | Yes | Unchanged |
| `power.solar_rated_kw` | **12.0 kW** (was 15.0) | Engineering placeholder sized for the mission | Yes | See [Changes](#changes-in-v020) |
| `power.battery.capacity_kwh` | **240 kWh** (was 160) | Engineering placeholder | Yes | See [Changes](#changes-in-v020) |
| `power.battery.initial_soc` | 0.9 | Mission configuration | Yes | Unchanged |
| `life_support.initial_oxygen_kg`, `oxygen_capacity_kg`, `initial_water_kg`, `initial_co2_kg`, `food.initial_food_kg`, `food.ration_min` | **24** (was 40), 60, 120, 0.35, 70, 0.5 | Mission configuration | Yes | Oxygen: see [Changes](#changes-in-v020); others unchanged |
| `comms.downlink_mb_per_hour` | 120 | Mission configuration | Yes | Unchanged |
| `science.opportunities.*` (windows, work ticks, points, data) | see scenario | Mission design | Yes | Unchanged |
| `rover.*` | see scenario | Mission design | Yes | Unchanged |
| `degradation.components.*.wear_per_tick` | **3 × v0.1.0** (0.0003 / 0.0006) | Gameplay values | Yes | See [Changes](#changes-in-v020) |
| `degradation.components.*.fault_probability_per_tick`, `fault_damage`, `maintenance_ticks`, `maintenance_restore` | see scenario | Gameplay values | Yes | Unchanged |
| `events.*` timing and magnitude (SPE tick 122 ×40 8 h; minor flare p = 0.003/tick ×5 3 h; relay outage; pump fault) | see scenario | Gameplay/story | Protected in Phase 3 | Story content (the brief forbids story changes) |
| `phases` | 13 phases | Story | Protected | Unchanged |
| `radiation.dose_limit_msv` | 15 mSv (new field) | Gameplay threshold; no regulatory limit claimed | Yes | New: exposes dose-budget metrics (same value as the existing radiation objective) |
| Alert thresholds (`alerts`) | see scenario | Gameplay/UX | Yes | New radiation and dose-budget alerts, see [Changes](#changes-in-v020) |
| Objectives and outcome rules | see scenario | Mission design (D3) | Yes | Redesigned, see [Changes](#changes-in-v020) |
| `analysis.risk_terms` weights | see scenario | Analysis indicator (D22) | Yes | Radiation term added, see [Changes](#changes-in-v020) |

## Changes in v0.2.0

Each change is backed by a **leave-one-out** experiment: the shipped v0.2.0 scenario with that
one change reverted to its v0.1.0 value, 11 strategies × 100 seeds (seeds 1–100), checked against
the 13 diagnostic envelopes of `balancing/search.py`. The envelopes are qualitative checks taken
from the Phase 3 brief (e.g. "passive never wins", "balanced succeeds usually but not
automatically", "battery depletion is not universal"), not percentage targets. Final 500-seed
distributions are in [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md).

| Configuration (100 seeds) | Envelopes passed (of 13) |
|---|---|
| Shipped v0.2.0 | **13** |
| … battery back to 160 kWh | 7 |
| … array back to 15 kW | 11 |
| … wear back to ×1 | 11 |
| … initial oxygen back to 40 kg | 13 |
| … cold penalty back to 0.001 | 13 |
| All five reverted (new outcome rules on v0.1.0 numbers) | 8 |

Two changes pass every envelope when reverted. They are kept for reasons the envelopes do not
measure (a dominant decision; physiological plausibility), stated below.

### Numeric parameters

| Parameter | v0.1.0 → v0.2.0 | Class | Reason | Evidence |
|---|---|---|---|---|
| `power.battery.capacity_kwh` | 160 → **240** kWh | GAMEPLAY | The brief requires that a well-managed mission *can* end with reserves (§6, §8). At 160 kWh the night cannot be crossed by managed play, so battery depletion is universal and uninformative | Reverted: balanced and power-conservative empty the battery in 100 % of missions and never reach full success; 6 envelopes fail |
| `power.solar_rated_kw` | 15 → **12** kW | GAMEPLAY | With the larger battery, a 15 kW array removes the energy trade-off for competent play: balanced always succeeds and science never threatens power continuity. 12 kW keeps a binding energy budget around dusk, so balanced success is strong but not guaranteed | Reverted: balanced 100 % success (median end SOC 0.25 instead of 0.08); power-conservative 95 % |
| `life_support.initial_oxygen_kg` | 40 → **24** kg | GAMEPLAY | 40 kg is 12.2 days of crew oxygen, more than the 10-day mission, so oxygen generation was optional: switching it off was free power with no consequence. 24 kg (7.3 days) makes the generator a real life-support decision | Balanced, seeds 1–20, generator off from tick 30 and never back on: at 40 kg the mission **improves** from success to exceptional in 20/20 (a dominant action); at 24 kg oxygen runs out (life-support stability fails 20/20) |
| `crew_health.cold_penalty_per_k_tick` | 0.001 → **0.0004** per K per hour | EDUCATIONAL_ABSTRACTION | Plausibility of *relative* severity. At 0.001 a 10 °C cabin (the lowest allowed setpoint) cost 0.005 health/h, exactly as much as having no food at all (starvation 0.005/h), and was lethal in about 8 days. WHO 2018 links cold homes (< 16–18 °C) to health risks such as higher blood pressure, not to death within days. At 0.0004, 10 °C costs 0.002/h and 12 °C 0.0012/h: still harmful, no longer lethal within the mission. The 15 °C threshold is unchanged | Reverted: only high-risk changes materially (crew loss 4 % → 100 %); every other strategy's median minimum health moves by ≤ 0.03. This side effect is reported, not the reason |
| `degradation.components.*.wear_per_tick` | **× 3** (0.0001/0.0002 → 0.0003/0.0006) | GAMEPLAY | Random faults scale with wear (p · (1 − health)). In v0.1.0 they averaged ~0.6 per mission and a strategy's mission barely depended on the seed (Phase 2: 17–62 distinct results per 500 seeds). × 3 makes wear and faults a genuine operational uncertainty | Reverted: balanced 100 % success (no failure risk at all); distinct results 33 instead of 41 per 100 seeds. **Not claimed:** maintenance did not become a major decision (decision audit: LOCAL impact with and without the change; see [DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md)) |

Parameters searched but left unchanged: everything else, including all EVIDENCE_LOCKED and
UNVERIFIED values, the story environment (sunset and cooling curves), event timings and
magnitudes, consumer loads, thermal constants, shielding factors, science opportunities and the
food supply. The bounded search report (`reports/phase3/search/`, regenerated by the command in
[BALANCING_LAB.md](BALANCING_LAB.md)) screened 18 neighbouring configurations (array 11 / 12 /
13 kW × battery 200 / 240 / 280 kWh × wear × 1 or × 3 *relative to v0.2.0*, i.e. 3× or 9× the
v0.1.0 wear) on 30 seeds and re-ran the top three on 100 seeds. The shipped configuration ranks
first (13 of 13 envelopes, deviation 0); array 13 kW with 9× wear and battery 280 kWh with 9×
wear also pass all 13. The exact values are therefore a choice within a family, recorded as open
decision
[D23](USER_DECISIONS_REQUIRED.md#d23-exact-values-of-the-v020-gameplay-parameters).

### Rules, alerts and indicators

| Item | v0.1.0 → v0.2.0 | Class | Reason |
|---|---|---|---|
| Objectives | 5 → 10, each in a pillar: primary (crew survival, two science campaigns completed, ≥ 800 MB returned), safety (dose < 15 mSv, crew health ≥ 0.5), stability (no forced load shedding; no life-support crisis), efficiency (end reserves ≥ 3 days O₂ and water and ≥ 15 % battery), science (≥ 100 points), discovery (all three campaigns) | GAMEPLAY (mission design, D3) | v0.1.0 allowed one action (the ice core) to give full success, and passive play to be "partial". Primary science now needs two campaigns, so no single action completes it |
| Outcome rules | complete / partial / fallback by optional-objective fraction → tiers: crew loss = critical failure; any primary failed = mission failed (crew may be safe); primary = partial; + safety + stability = success; + efficiency + science = exceptional | GAMEPLAY (D3) | Surviving ≠ completing ≠ excelling (brief §3, §14). Outcome codes are backward compatible; `mission_complete_exceptional` is new |
| `radiation.dose_limit_msv` | — → 15 mSv | GAMEPLAY | Same value as the radiation objective. Turns on dose-budget metrics (dose margin, projected end-of-mission dose at *baseline* rate) so a player can budget exposure without knowledge of future events (brief §13) |
| Alerts | + `radiation_above_background` (caution, > 0.12 mSv/h), + `dose_budget_low` (projected margin < 2 mSv), + `dose_budget_exceeded` (< 0) | GAMEPLAY | Phase 2: a ×5 flare (0.285 mSv/h) stayed below the only radiation alert (0.5 mSv/h). Information, not lower difficulty |
| `analysis.severity_overrides` | + `power.unmet_kw` (0 → 2 kW), + `crew.max_dose_msv` (7.5 → 15 mSv) | Analysis | Lets the Black Box trace the new stability and safety objectives |
| `analysis.risk_terms` | + `crew.projected_dose_margin_msv`, weight 0.6 | Analysis indicator | D22: the risk index had no radiation term. The weight is provisional (same scale as habitat temperature and water) |
