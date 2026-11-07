# Decision Impact Model

How much each kind of player decision matters in LUNA-01 v0.2.0, **measured**, not asserted.
Phase 2 found that removing any of 500 power, thermal, rover or cleaning decisions changed 0
outcomes and 0 objectives (v0.1.0). This document classifies every decision kind after Phase 3.

## Classes

| Class | Meaning | Rule (analysis parameters, not balance targets) |
|---|---|---|
| **HIGH** | Can change the mission | Changes the outcome tier or a primary / safety / stability objective in ≥ 25 % of insertions |
| **MEDIUM** | Changes the quality of the mission | Changes some objective in ≥ 10 % of insertions, or materially moves a resource (end battery ≥ 0.05 SOC, dose ≥ 1 mSv, science ≥ 10 points, water or oxygen ≥ 0.5 day) in ≥ 25 % |
| **LOCAL** | Measurable but contained | A measurable change in ≥ 25 % of insertions, below the MEDIUM bars |
| **REDUNDANT** | Usually no effect | No measurable change in ≥ 75 % of valid insertions |
| **INFORMATIONAL** | No state effect by design | Future Lens, ORION, Black Box and trace queries. None of the nine engine decision types is informational |

## Method

Two complementary measurements, both open loop (only the measured decision differs, the rest of
the mission is replayed exactly):

1. **Insertion audit** (`python -m app.simulation.analysis.balancing audit`): each of 24 catalogue
   decisions is inserted into a reference strategy's mission at ticks 30, 110, 175 and 212 (day,
   storm approach, dusk, night), 5 seeds, for three references (balanced, survival-first,
   science-first): 480 insertions per reference. Answers: *what does this action do on its own?*
2. **Omission forks** (`diagnose`, decision impact): every decision a strategy actually made is
   removed in turn (balanced, survival-first, science-first, power-conservative; 10 seeds; 508
   forks). Answers: *does this decision matter as part of a plan?*

Reports: `reports/phase3/audit-*.json`, `reports/phase3/diagnose-500/impact.json`.

## Classification (v0.2.0)

Insertion class per reference strategy (balanced / survival-first / science-first), and the
omission result where the strategies make that decision.

| Decision | Insertion audit (bal / surv / sci) | Omission forks: outcome changed (objectives changed) | Verdict |
|---|---|---|---|
| CO₂ scrubber eco | HIGH / HIGH / HIGH | — | **HIGH**: CO₂ rises past the stability limit |
| Oxygen generation off | HIGH / HIGH / HIGH | 0 % (85 %) of 20 night-plan forks | **HIGH**: stored oxygen lasts 7.3 days of a 10-day mission (v0.1.0: 12.2 days, a free action) |
| Water recovery off | HIGH / HIGH / HIGH | — | **HIGH** |
| Water recovery eco | HIGH / HIGH / MEDIUM | — | **HIGH** for planners |
| Crew to shelter | HIGH / HIGH / HIGH | 55 % (59 %) of 51 forks | **HIGH**: radiation safety |
| Crew back to habitat | — | 62 % (62 %) of 47 forks | **HIGH**: staying sheltered stops habitat science, so a campaign is missed |
| Start a science campaign | — | ice core 57 % (100 %) of 49; regolith 46 % (95 %) of 41 | **HIGH**: primary science needs two campaigns |
| Rover traverse (far crater) | — | 0 % (100 %) of 20 | **MEDIUM**: science quality and discovery |
| Oxygen generation eco | MEDIUM / MEDIUM / MEDIUM | 100 % (100 %) of 10 (balanced at dusk) | **HIGH as part of the night plan** |
| Habitat core eco | LOCAL / LOCAL / LOCAL | 33 % (33 %) of 30 | **HIGH as part of the night plan**, local as a one-off |
| Rover charger off | REDUNDANT / REDUNDANT / LOCAL | 33 % (33 %) of 30 | **HIGH as part of the night plan**; a one-off is redundant (the charger draws only when the rover battery is not full) |
| Comms off | MEDIUM / HIGH / HIGH | 0 % (0 %) of 22 | **MEDIUM**: saves power, blocks data return while off |
| Comms eco | LOCAL / LOCAL / LOCAL | 5 % (5 %) of 22 | LOCAL |
| CO₂ scrubber boost | HIGH / MEDIUM / MEDIUM | — | MEDIUM–HIGH (power cost vs CO₂) |
| Setpoint 24 °C | HIGH / MEDIUM / LOCAL | — | MEDIUM (heating costs energy at night) |
| Setpoint 15–18 °C | LOCAL / LOCAL / LOCAL | 0 % (0 %) of 40 | **LOCAL**: internal heat keeps the habitat warm until load shedding |
| Heater eco | LOCAL / LOCAL / REDUNDANT | — | LOCAL / REDUNDANT (same reason) |
| Rations 75 % | LOCAL / LOCAL / MEDIUM | — | LOCAL (food lasts; small health cost) |
| Science payload boost / eco | LOCAL / MEDIUM / REDUNDANT | eco: 5 % (5 %) of 20 | LOCAL |
| Rover energy transfer | HIGH / MEDIUM / LOCAL | 3 % (3 %) of 30 | MEDIUM (40 kWh reserve; matters at night) |
| Rover stow | MEDIUM / MEDIUM / MEDIUM | — | MEDIUM |
| Stop science | MEDIUM / HIGH / — | 0 % (0 %) of 11 | MEDIUM–HIGH (stopping can lose a campaign) |
| Clean solar array | MEDIUM / LOCAL / LOCAL | 0 % (0 %) of 40 | **LOCAL** |
| Maintenance (any component) | LOCAL or MEDIUM (solar array) | water processor: 0 % (20 %) of 15 | **LOCAL** (see [D24](USER_DECISIONS_REQUIRED.md#d24-should-maintenance-be-a-major-decision)) |

**Summary.** The engineering trade-offs presented as major (life support modes, sheltering,
science campaigns, preparing for the night) are HIGH impact. Small operational actions
(thermostat within the comfort band, heater eco, cleaning, maintenance, single eco toggles in
daylight) are LOCAL, which the brief allows ("small operational actions are allowed to have
local effects"). One kind is REDUNDANT as a one-off: switching off a rover charger that is not
charging.

Phase 2 → Phase 3, omission forks of power, thermal, rover and cleaning decisions: **0 of 500 →
33 of 294 changed the outcome, 70 changed an objective.** All decision kinds together: 22 of 376
→ 137 of 508 forks changed the outcome.

## Decision chains

The decisive behaviour comes from sequences, not single clicks:

| Chain | Mechanism (dependency graph) | Measured |
|---|---|---|
| Prepare for the night → reserve → no load shedding → stability pillar | eco loads at dusk → `power.battery_soc` → `power.unmet_kw` | Omitting any one of balanced's dusk actions (habitat core eco, O₂ generation eco, rover charger off) turns success into partial in 10/10 forks each |
| Science activity → power and crew time → less margin at dusk | `control.discretionary_load_kw` → `power.battery_soc`; `crew.in_shelter` → `science.points` | Science-first (every window, boosted) empties the battery in 100 % of missions; balanced in 3.4 % |
| Oxygen generation off → oxygen reserve → life-support stability | `control.mode.oxygen_generation` → `life_support.oxygen_days` | Off from tick 30 without turning it back on: life-support stability fails in 20/20 seeds (v0.1.0: never) |
| Shelter (and return) → dose and science → safety and primary pillars | `crew.in_shelter` → received dose → `crew.max_dose_msv`; `crew.in_shelter` → `science.points` | Omitting a shelter order: outcome changes in 55 %; omitting the return to the habitat: 62 % (a campaign is missed) |
| Skip maintenance → degradation → later faults | wear → `component.*.health` → fault probability | **Weak**: LOCAL in v0.2.0 (D24) |

## Known gaps

* **No-op decisions** (closed loop): a strategy that keeps playing re-issues an omitted decision a
  tick later, so "no effect" in closed loop measures a strategy's robustness, not the decision.
  Accepted decisions on an unpowered subsystem still do nothing silently
  ([D20](USER_DECISIONS_REQUIRED.md#d20-decisions-that-have-no-effect-while-a-load-is-shed)).
* **Maintenance** stays LOCAL ([D24](USER_DECISIONS_REQUIRED.md#d24-should-maintenance-be-a-major-decision)).
* **Thermostat** decisions inside the comfort band stay LOCAL because equipment heat warms the
  habitat until load shedding; this is a modelled lesson (Phase 2 noted it under D1), not a bug.
