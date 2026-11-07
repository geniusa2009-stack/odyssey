# Phase 3 Balance Report: LUNA-01 v0.1.0 → v0.2.0

Phase 3 turned LUNA-01 from a technically correct simulation into a mission where choices
matter, without altering scientific values. This report gives the evidence: **before**
(v0.1.0, measured at commit `9d0b00d`) and **after** (v0.2.0, this working tree).

* Scenario content hashes: v0.1.0 `a67635671fa5…`, v0.2.0 `ced64e641c46…`.
* Strategies are scripted probes, not players ([BALANCING_LAB.md](BALANCING_LAB.md#strategies)).
  A rate below describes what *that probe* achieves.
* Every number can be regenerated. Before: `git worktree add … 9d0b00d`, then the Phase 2
  commands. After: the commands in [Reproducing](#reproducing).

## Contents

1. [Method](#method)
2. [Success criteria](#success-criteria)
3. [Outcome model before and after](#outcome-model-before-and-after)
4. [Strategy distributions before and after](#strategy-distributions-before-and-after)
5. [Battery, reserves and resources](#battery-reserves-and-resources)
6. [Science and radiation](#science-and-radiation)
7. [Dominant strategies and decisions, unreachable outcomes, free objectives, meaningless decisions](#dominant-strategies-and-decisions-unreachable-outcomes-free-objectives-meaningless-decisions)
8. [Failure causes](#failure-causes)
9. [Decision impact](#decision-impact)
10. [Future Lens](#future-lens)
11. [Black Box](#black-box)
12. [Engineering Profile separation](#engineering-profile-separation)
13. [Parameter changes, and changes considered but rejected](#parameter-changes-and-changes-considered-but-rejected)
14. [Resource trajectories](#resource-trajectories)
15. [Invariants, fuzzing, determinism, performance](#invariants-fuzzing-determinism-performance)
16. [Remaining issues](#remaining-issues)
17. [Reproducing](#reproducing)

## Method

1. **Reproduce first.** The Phase 2 measurements were re-run from a clean worktree of
   `9d0b00d` before any change: the 500-seed strict matrix (5,000 missions), the full
   `diagnose` run (ablation, 752 decision-impact forks, sensitivity, findings) and the quality
   report. All were byte-identical to the Phase 2 files.
2. **Protect the science.** Every parameter was classified
   ([PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md)). Evidence-locked values are pinned by a
   test; the search tool refuses them and the story environment.
3. **Change the rules, then the numbers.** The outcome model was redesigned first. Then five
   gameplay numbers were changed, each with a stated reason and a **leave-one-out** experiment
   (revert one change, 11 strategies × 100 seeds, 13 qualitative diagnostic envelopes).
4. **Measure, never target.** The envelopes are pass/fail descriptions taken from the brief
   ("passive never wins", "balanced succeeds usually but not automatically", ...). No parameter
   was chosen to hit a percentage, and probes were changed only where the new rules made one
   misrepresent its own philosophy (documented in
   [BALANCING_LAB.md](BALANCING_LAB.md#strategies)).
5. **Validate at scale.** Final matrix: 11 strategies × 500 seeds with every invariant checked
   after every tick, plus diagnose, decision audit, quality, trajectories and a bounded search.

## Success criteria

The 17 Phase 3 success criteria, with the evidence for each (500 seeds per strategy unless
stated).

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | No single action guarantees full success | **Met** | Each science campaign started alone ends `mission_failed` (tested for all three). Primary science needs two campaigns; success also needs the safety and stability pillars |
| 2 | Passive play cannot achieve full success | **Met** | Passive: 0 % success, 100 % `mission_failed` (was 100 % partial) |
| 3 | A mission can fail while the crew is safe | **Met** | Passive: `mission_failed` in 100 % with crew health ≥ 0.5 in 99.4 %; always-shelter likewise; survival-first's 2.8 % non-successes are crew-safe mission failures |
| 4 | Full success needs multidimensional performance | **Met** | Success = primary + safety + stability; exceptional adds efficiency + science. No success-tier rule uses fewer than three pillars (tested) |
| 5 | Battery depletion is no longer universal | **Met** | Battery reaches zero in 0 % (survival-first, power-conservative, expert, reserve-keeper), 3.4 % (balanced), 100 % (science-first, high-risk, naive, passive). Was 100 % for every scripted strategy |
| 6 | Rational strategies produce different trajectories | **Met** | Median end battery 0.00–0.50, end water 2.1–4.1 days, science completion 0.67–1.00, crew health ≥ 0.5 in 0–100 % depending on strategy (tables below; trajectories exported) |
| 7 | Balanced play: strong but non-guaranteed success | **Met** | Balanced: 96.6 % success, 3.4 % partial (battery emptied; those 17 missions average 2.0 random component faults vs 1.22 in the successes) |
| 8 | Reckless play is measurably riskier | **Met** | High-risk: 0 % success; crew health < 0.5 in 100 %; crew loss 1.8 %; battery empty 100 %; radiation objective failed 100 % (balanced: 0 % / 0 % / 3.4 % / 0 %) |
| 9 | Science ambition creates resource trade-offs | **Met** | Science-first: science completion 1.00, battery empty 100 %, end water 2.2 days, radiation failed 100 %. Survival-first: completion 0.67, end battery 0.50, water 3.8 days |
| 10 | Resource conservation has opportunity costs | **Met** | Power-conservative and survival-first: 85 science points median vs 123 for balanced; never reach the science-quality pillar, so never exceptional |
| 11 | Major decisions have measurable consequences | **Met** | Decision audit: 8 of 24 catalogue decisions are HIGH for balanced play (CO₂ scrubber eco and boost, O₂ generation off, water recovery eco and off, setpoint 24 °C, shelter, rover energy transfer); v0.1.0 power / thermal / rover / cleaning forks changed 0 outcomes, v0.2.0: 33 of 294 changed the outcome and 70 an objective ([Decision impact](#decision-impact)) |
| 12 | Future Lens reflects consequences, not omniscient | **Met** | Deterministic and isolated in 432 predictions; unforeseeable events still hidden (mean dose error 3.3 mSv when the storm is in the horizon); explains **27 of 27** warnings a candidate introduces (Phase 2: 21 of 27); major choices are never indistinguishable from doing nothing |
| 13 | Black Box explains major failures | **Met** | 32 failure cases (14 crew losses, 5 crew-safe mission failures, 13 partials): 0 cycles, order violations, undeclared edges, missing context, unexplained failures or unstable traces. The outcome analysis produced 194 failed-objective chains; it blames 55 decisions, every one verified by counterfactual replay, and reports 11 on-path-but-no-effect decisions separately |
| 14 | NASA-grounded parameters stay defensible | **Met** | 0 evidence-locked values changed (test-enforced); 0 UNVERIFIED values changed; the one abstraction changed (cold penalty) is justified by relative severity and WHO 2018 |
| 15 | Determinism intact | **Met** | Same seed → identical state hash, event stream, Black Box and Future Lens output in two separate processes; a 100-seed × 11-strategy sweep is identical with 2 workers and with 1, and identical to the same seeds of the 500-seed run; 8 v0.1.0 missions recorded on `9d0b00d` replay byte-identically ([Invariants…](#invariants-fuzzing-determinism-performance)) |
| 16 | All invariants intact | **Met** | Strict sweep: 5,500 missions, 1,301,800 states checked, **0 violations** |
| 17 | Fuzz / property tests clean | **Met** | `fuzz` profile, 75 tests, 0 failures: any decision sequence 500 / 500 (79 inputs discarded by filters), parameter perturbations 500 / 500, replay 500 / 500, Future Lens isolation 240 (input space exhausted) |

Brief envelopes **not** fully met, reported rather than tuned away:

* **High-risk "should sometimes succeed impressively": 0 %.** The probe never shelters from a
  *scheduled* solar particle event, so the radiation objective fails with certainty (median dose
  18.9 mSv vs the 15 mSv limit). That is a certainty, not a risk; making it succeed would need an
  easier storm or a different probe, both of which would be tuning to a target.
* **Naive-beginner "must not feel predetermined":** its missions vary (108 distinct final
  states per 500 seeds by the Phase 2 detector, was 18; radiation objective met in 94 %), but the
  outcome class is always partial: it never prepares for the night, so the battery always
  empties (the stability pillar).
* **Science-first never succeeds** (100 % partial): it never shelters and never saves power. The
  science-heavy *successful* style exists (the `expert` probe: 95.8 % exceptional with the most
  science of any strategy), so this is the probe's choice, not an impossibility.

## Outcome model before and after

| | v0.1.0 (before) | v0.2.0 (after) |
|---|---|---|
| Objectives | 5: crew survival (required); science ≥ 60 pts, data ≥ 1200 MB, dose < 15 mSv, end reserves (optional) | 10 in six pillars (primary, safety, stability, efficiency, science, discovery); see [SIMULATION_MODEL.md](SIMULATION_MODEL.md#310-objectives-and-outcomes-luna-01-v020) |
| Full success | crew alive + any 2 of 4 optional objectives | primary (crew alive, two campaigns, ≥ 800 MB) + safety + stability |
| Exceptional | — | success + efficiency + science quality |
| Partial | crew alive (anything else) | primary only |
| Mission failed | unreachable (0 of 5,000 missions, 10 probes × 500 seeds) | any primary objective failed, crew may be safe |
| Critical failure | crew loss | crew loss |
| What the ice-core campaign gave | **full success** with any one more optional objective: a second campaign (data ≥ 1200 MB) or sheltering (dose < 15 mSv) | `mission_failed` on its own (one campaign; tested); success still needs a second campaign, safety and stability |
| What doing nothing gave | partial (crew survival was free) | `mission_failed` |

Why the ice core dominated in v0.1.0: four optional objectives with a 50 % bar meant any two gave
success. The ice-core campaign was the only one that met the 60-point science objective on its
own (64 points), and every pair of campaigns that reached the 1200 MB data objective included it
(regolith + far crater return only 880 MB). So the ice core plus any second campaign was full
success with no attention to power or crew safety; removing the ice-core window turned
science-first from 100 % success to 100 % partial. The fix is in the rules (two campaigns plus
safety and stability), not a nerf of the ice core's points.

## Strategy distributions before and after

**Before: v0.1.0, commit `9d0b00d`, Phase 2 probes, 500 seeds each.** "End reserves met" uses
the v0.1.0 thresholds (≥ 1 day O₂/water, ≥ 5 % battery). End O₂/water days were recomputed on the
clean `9d0b00d` worktree (Phase 2 telemetry did not record them).

| Strategy | Success | Partial | Mission failed | Crew loss | Crew health ≥ 0.5 | Science completion p50 | Min battery p50 | End battery p50 | Battery empty | Min water days p50 | End O₂ / water days p50 | End reserves met | Radiation goal | Decisions p50 | Duration p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `passive` | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.00 | 0.00 | 0.00 | 100.0 | 2.40 | 12.8 / 2.4 | 0.0 | 0.0 | 0 | 240 |
| `survival_first` | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.00 | 0.00 | 0.00 | 100.0 | 2.57 | 13.3 / 2.6 | 0.0 | 98.2 | 9 | 240 |
| `science_first` | 100.0 | 0.0 | 0.0 | 0.0 | 98.8 | 1.00 | 0.00 | 0.00 | 100.0 | 2.30 | 12.5 / 2.3 | 0.0 | 0.0 | 4 | 240 |
| `balanced` | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 1.00 | 0.00 | 0.00 | 100.0 | 2.44 | 13.0 / 2.4 | 0.0 | 98.2 | 12 | 240 |
| `power_conservative` | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.67 | 0.00 | 0.00 | 100.0 | 2.63 | 13.5 / 2.6 | 0.0 | 98.2 | 12 | 240 |
| `high_risk` | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 1.00 | 0.00 | 0.00 | 98.0 | 2.88 | 13.1 / 2.9 | 2.0 | 0.0 | 6 | 226 |
| `naive_beginner` | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.67 | 0.00 | 0.00 | 100.0 | 2.40 | 12.8 / 2.4 | 0.0 | 98.2 | 6 | 240 |
| `random_valid` | 0.4 | 42.0 | 0.0 | 57.6 | 24.4 | 0.00 | 0.28 | 0.28 | 36.4 | 2.39 | 12.5 / 2.4 | 43.6 | 21.2 | 21 | 228 |
| `reserve_keeper` | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.67 | 0.13 | 0.13 | 0.2 | 2.65 | 9.7 / 2.6 | 99.4 | 98.2 | 44 | 240 |
| `always_shelter` | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.00 | 0.00 | 0.00 | 100.0 | 2.40 | 12.8 / 2.4 | 0.0 | 100.0 | 1 | 240 |

**After: v0.2.0, 500 seeds each.** "End reserves met" uses the v0.2.0 efficiency thresholds
(≥ 3 days O₂ and water, ≥ 15 % battery). `expert` is a Phase 3 existence probe.

| Strategy | Exceptional | Success | Partial | Mission failed | Critical (crew loss) | Crew health ≥ 0.5 | Science completion p50 | Min battery p50 | End battery p50 | Battery empty | Min water days p50 | End O₂ / water days p50 | End reserves met | Radiation goal | Decisions p50 | Duration p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `passive` | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 99.4 | 0.00 | 0.00 | 0.00 | 100.0 | 2.24 | 7.8 / 2.2 | 0.0 | 0.0 | 0 | 240 |
| `survival_first` | 0.0 | 97.2 | 0.0 | 2.8 | 0.0 | 100.0 | 0.67 | 0.50 | 0.50 | 0.0 | 3.75 | 5.1 / 3.8 | 97.6 | 100.0 | 15 | 240 |
| `science_first` | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 99.4 | 1.00 | 0.00 | 0.00 | 100.0 | 2.16 | 7.6 / 2.2 | 0.0 | 0.0 | 4 | 240 |
| `balanced` | 0.0 | 96.6 | 3.4 | 0.0 | 0.0 | 100.0 | 1.00 | 0.08 | 0.08 | 3.4 | 2.74 | 7.1 / 2.7 | 0.0 | 100.0 | 14 | 240 |
| `power_conservative` | 0.0 | 98.4 | 1.2 | 0.4 | 0.0 | 100.0 | 0.67 | 0.49 | 0.49 | 0.0 | 3.17 | 5.1 / 3.2 | 72.2 | 98.8 | 14 | 240 |
| `high_risk` | 0.0 | 0.0 | 98.2 | 0.0 | 1.8 | 0.0 | 1.00 | 0.00 | 0.00 | 100.0 | 2.14 | 7.5 / 2.1 | 0.0 | 0.0 | 7 | 240 |
| `naive_beginner` | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.67 | 0.00 | 0.00 | 100.0 | 2.24 | 7.8 / 2.2 | 0.0 | 94.0 | 6 | 240 |
| `random_valid` | 0.0 | 0.0 | 0.0 | 42.4 | 57.6 | 27.4 | 0.00 | 0.45 | 0.45 | 25.2 | 2.27 | 7.3 / 2.3 | 27.6 | 21.6 | 21 | 228 |
| `reserve_keeper` | 0.0 | 97.0 | 3.0 | 0.0 | 0.0 | 98.4 | 0.67 | 0.36 | 0.36 | 0.0 | 2.41 | 4.6 / 2.4 | 0.0 | 98.8 | 38 | 240 |
| `always_shelter` | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 99.6 | 0.00 | 0.00 | 0.00 | 100.0 | 2.24 | 7.8 / 2.2 | 0.0 | 100.0 | 1 | 240 |
| `expert` | 95.8 | 4.2 | 0.0 | 0.0 | 0.0 | 100.0 | 1.00 | 0.33 | 0.33 | 0.0 | 4.11 | 3.4 / 4.1 | 99.2 | 100.0 | 19 | 240 |

Columns: crew health ≥ 0.5 = share of missions where every crew member's health stayed at or
above 0.5 (crew safety); science completion = campaigns completed / 3; battery empty = share of
missions with at least one tick at 0 %; decisions = accepted decisions; duration in hours.

Objective achievement rates (v0.2.0, %):

| Strategy | Objective achievement rates |
|---|---|
| `passive` | crew_survival 100, science_return 0, data_return 0, radiation_safety 0, crew_health 99, power_continuity 0, life_support_stability 0, reserves_at_end 0, science_quality 0, full_survey 0 |
| `survival_first` | crew_survival 100, science_return 97, data_return 100, radiation_safety 100, crew_health 100, power_continuity 100, life_support_stability 100, reserves_at_end 98, science_quality 0, full_survey 0 |
| `science_first` | crew_survival 100, science_return 100, data_return 100, radiation_safety 0, crew_health 99, power_continuity 0, life_support_stability 0, reserves_at_end 0, science_quality 97, full_survey 95 |
| `balanced` | crew_survival 100, science_return 100, data_return 100, radiation_safety 100, crew_health 100, power_continuity 97, life_support_stability 100, reserves_at_end 0, science_quality 96, full_survey 95 |
| `power_conservative` | crew_survival 100, science_return 100, data_return 100, radiation_safety 99, crew_health 100, power_continuity 100, life_support_stability 100, reserves_at_end 72, science_quality 0, full_survey 0 |
| `high_risk` | crew_survival 98, science_return 100, data_return 100, radiation_safety 0, crew_health 0, power_continuity 0, life_support_stability 0, reserves_at_end 0, science_quality 97, full_survey 95 |
| `naive_beginner` | crew_survival 100, science_return 100, data_return 100, radiation_safety 94, crew_health 100, power_continuity 0, life_support_stability 0, reserves_at_end 0, science_quality 0, full_survey 0 |
| `random_valid` | crew_survival 42, science_return 0, data_return 2, radiation_safety 22, crew_health 27, power_continuity 75, life_support_stability 13, reserves_at_end 28, science_quality 0, full_survey 0 |
| `reserve_keeper` | crew_survival 100, science_return 100, data_return 100, radiation_safety 99, crew_health 98, power_continuity 100, life_support_stability 98, reserves_at_end 0, science_quality 0, full_survey 0 |
| `always_shelter` | crew_survival 100, science_return 0, data_return 0, radiation_safety 100, crew_health 100, power_continuity 0, life_support_stability 0, reserves_at_end 0, science_quality 0, full_survey 0 |
| `expert` | crew_survival 100, science_return 100, data_return 100, radiation_safety 100, crew_health 100, power_continuity 100, life_support_stability 100, reserves_at_end 99, science_quality 97, full_survey 95 |

## Battery, reserves and resources

* **Battery depletion is informative again.** It now separates strategies: 0 % for the planners
  (survival-first, power-conservative, expert, reserve-keeper), 3.4 % for balanced, 100 % for the
  strategies that never prepare for night (science-first, high-risk, naive, passive). v0.1.0:
  100 % for every scripted strategy.
* **Reserve profiles differ.** Median end battery: survival-first 0.50, power-conservative 0.49,
  reserve-keeper 0.36, expert 0.33, balanced 0.08, science-first / high-risk / naive 0.00.
  End-of-mission reserves (efficiency pillar) are met by survival-first in 97.6 %,
  power-conservative 72.2 %, expert 99.2 %, balanced 0 % (balanced ends with 2.7 days of water,
  below the 3-day bar, and 8 % battery).
* **Zero means something.** Every mission that empties the battery fails the stability pillar
  (forced load shedding), which blocks full success. Oxygen generation is no longer optional:
  stored oxygen covers 7.3 days of a 10-day mission (was 12.2).
* **Water** is the binding efficiency constraint for most strategies: median end water 2.1–2.7
  days for strategies that run water recovery at full power all mission, 3.2–4.1 days for those
  that manage it (survival-first, power-conservative, expert).

## Science and radiation

**Science.** Median science points (v0.2.0): science-first 129, high-risk 125, balanced 123,
expert 129, survival-first / power-conservative / naive / reserve-keeper 84–85, passive and
always-shelter 0. Two successful commanders can succeed differently: balanced (123 points, 8 %
battery at the end) and survival-first (85 points, 50 % battery) both succeed in ≥ 96 % of
missions (Pareto, tested).

**Radiation.** Phase 2 found 9 of 500 seeds where sheltering players still failed the radiation
objective, because nothing below the 0.5 mSv/h warning was visible and the remaining dose budget
was not exposed. v0.2.0 adds information, not leniency: a caution above 0.12 mSv/h, dose margin
and projected end-of-mission dose (using the *baseline* rate only, no knowledge of future
events), and dose-budget alerts. The flare-on-storm stacking (×200) is unchanged.

| Strategy (v0.2.0) | Uses | Radiation failures / 500 | Which seeds |
|---|---|---|---|
| balanced, survival-first, expert | caution alert + dose budget | **0** | — |
| power-conservative, reserve-keeper | caution alert only | 6 | 2, 12, 63, 259, 449, 482: the Phase 2 "background crosses the limit after a stacked flare" seeds |
| naive-beginner | caution alert, inconsistent attention | 30 | includes all 9 Phase 2 seeds |
| science-first, high-risk, passive | no sheltering | 500 | all |

Each piece of information fixes the failure mode it was designed for: the caution alert removes
the three "flare one tick before the storm" failures (seeds 39, 291, 297); the dose budget removes
the six "slow accumulation" failures. `tests/test_radiation_information.py` pins this for all
nine seeds.

## Dominant strategies and decisions, unreachable outcomes, free objectives, meaningless decisions

| Finding (Phase 2 → Phase 3) | v0.1.0 | v0.2.0 |
|---|---|---|
| Dominant single decision | Start ice-core sampling: full success | None. The best single decision (any campaign) ends `mission_failed`; the most decisive decisions (the second science campaign, the night preparations, sheltering and returning) are each necessary and none is sufficient |
| Dominant strategy | Science-first: 100 % success with 4 decisions | None among player probes: the best success rates (power-conservative 98.4 %, survival-first 97.2 %, balanced 96.6 %) come from different styles; only the `expert` existence probe reaches exceptional (95.8 %) |
| Unreachable outcomes | `mission_failed` (0 of 5,000) | `mission_complete_exceptional` for every player-style probe (0 of 5,000 missions); only the `expert` existence probe reaches it (95.8 %). Every other outcome occurs |
| Free objectives | crew survival (passive 100 %) | crew survival and crew health are still met by passive play (100 % / 99.4 %); they are necessary, not sufficient: passive fails the mission |
| Objectives never achieved | reserves (by any player probe) | None: every objective is achieved by at least one player-style probe (reserves: survival-first 97.6 %; science quality: balanced 96 %; discovery: balanced 95 %) |
| Meaningless decisions | All 500 power / thermal / rover / cleaning forks changed 0 outcomes | Power / thermal / rover / cleaning omission forks: 33 of 294 change the outcome. Still LOCAL: thermostat inside the comfort band, heater eco, array cleaning, maintenance ([D24](USER_DECISIONS_REQUIRED.md#d24-should-maintenance-be-a-major-decision)); REDUNDANT as a one-off: rover charger off when the rover is not charging |
| Universal alerts | habitat cold, radiation elevated, comms link down | radiation above background, radiation elevated (the scheduled storm), comms link down (the scheduled relay outage): unavoidable by design. Habitat cold is no longer universal |

## Failure causes

Which primary / safety / stability objectives failed in the missions that fell short of success
(v0.2.0, 500 seeds; one mission can fail several):

| Strategy | Missions short of success | Blocking pillar(s) among them (share) |
|---|---|---|
| `passive` | 500 | data_return 100%, life_support_stability 100%, power_continuity 100%, radiation_safety 100%, science_return 100%, crew_health 1% |
| `survival_first` | 14 | science_return 100% |
| `science_first` | 500 | life_support_stability 100%, power_continuity 100%, radiation_safety 100%, crew_health 1% |
| `balanced` | 17 | power_continuity 100% |
| `power_conservative` | 8 | radiation_safety 75%, science_return 25% |
| `high_risk` | 500 | crew_health 100%, life_support_stability 100%, power_continuity 100%, radiation_safety 100%, crew_survival 2% |
| `naive_beginner` | 500 | life_support_stability 100%, power_continuity 100%, radiation_safety 6% |
| `random_valid` | 500 | science_return 100%, data_return 98%, life_support_stability 87%, radiation_safety 78%, crew_health 73%, crew_survival 58%, power_continuity 25% |
| `reserve_keeper` | 15 | life_support_stability 60%, crew_health 53%, radiation_safety 40% |
| `always_shelter` | 500 | data_return 100%, life_support_stability 100%, power_continuity 100%, science_return 100%, crew_health 0% |
| `expert` | 0 | — |

Reading it: balanced falls short only by emptying the battery (17 missions); survival-first only
by not completing two campaigns (14); science-first, high-risk and naive always fail stability,
high-risk and science-first always fail radiation safety, and high-risk always fails crew health.

## Decision impact

Full model: [DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md).

| Measure | v0.1.0 | v0.2.0 |
|---|---|---|
| Omission forks (balanced, survival-first, science-first, power-conservative; 10 seeds), outcome changed | 22 of 376 | **137 of 508** |
| … objectives changed | 68 | 220 |
| … no measurable effect | 20 | 19 |
| Power / thermal / rover / cleaning forks: outcome changed | 0 of 500 | **33 of 294** |
| … objective changed | 0 | 70 |
| Closed-loop forks (strategy keeps playing): outcome changed | 0 of 376 | 0 of 508 |

Closed loop, the strategy re-issues the omitted decision a tick later, so "no effect" there
measures robustness, not the decision. Insertion audit (24 decisions × 4 ticks × 5 seeds × 3
reference strategies): HIGH for life-support modes, sheltering, science campaigns, night
preparation as a sequence; LOCAL for thermostat inside the comfort band, heater eco, cleaning,
maintenance; REDUNDANT for switching off an idle rover charger.

## Future Lens

| Measure | Phase 2 (v0.1.0) | Phase 3 (v0.2.0) |
|---|---|---|
| Predictions measured | 432 | 432 |
| Deterministic / isolated | yes / yes | yes / yes |
| Candidate-introduced warnings explained by the candidate | 21 of 27 (77.8 %) | **27 of 27 (100 %)** |
| Indistinguishable from the baseline over 24 h (end values) | 32.5 % | 35.0 % |
| … using every signal (end, worst, new warnings, objectives) | — | 35.0 % |
| Major choices indistinguishable (scrubber eco, O₂ off, water off, setpoint 15 °C, rations 80 %) | 0 % | 0 % |
| Minor choices indistinguishable (heater eco 100 %, idle rover charger off 100 %, comms eco 62.5 %, habitat core eco 62.5 %) | 100 / 87.5 / 62.5 / 62.5 % | 100 / 100 / 62.5 / 62.5 % |
| Shelter indistinguishable | 12.5 % | 25 % (6 of 24 states: 4 with the crew already sheltered for its dose budget; 2 with a crew member on EVA, who is not moved by a shelter order and holds the highest dose) |
| Confidence 6 / 24 / 72 / 144 h | 0.628 / 0.51 / 0.336 / 0.276 | 0.628 / 0.51 / 0.338 / 0.276 |
| Hidden-event projections: mean / max dose error | 3.335 / 10.67 mSv | 3.335 / 10.67 mSv |
| Hidden-event projections: max risk error | 0.021 | 0.602 |

Readings:

* **Honesty is unchanged.** `known_only` still hides the unforeseeable storm and flares; the dose
  error when they are in the horizon is identical. The risk error grew because the risk index
  now *contains* radiation (D22): when the hidden storm hits, the projected risk was too low,
  which is the correct consequence of not knowing the future.
* **Separation is physics, not tuning.** Habitat-core eco looks like doing nothing over 24 h in
  daylight (the battery is full, the saving is curtailed) and matters a lot at night (omitting it
  from balanced's dusk plan turns success into partial in 10 of 10 forks). The lens shows
  exactly that; no difference was amplified.
* **Explanation coverage** improved twice: introduced warnings are traced first, and a warning
  is traced at the tick the traced sample actually raised it (a warning's `first_tick` is the
  earliest across samples).

## Black Box

| Measure (v0.2.0) | Result |
|---|---|
| Failure cases traced | 32: 5 injected; up to 5 crew losses or mission failures from seeds 1–100 of high-risk (only 4 occur), random (5) and passive (5) play; up to 5 partials of balanced (only 3 occur), science-first (5) and naive (5) play. Crew loss 14, crew-safe mission failure 5, partial 13 |
| Cyclic chains, order violations, undeclared edges, missing context, unexplained, unstable | 0, 0, 0, 0, 0, 0 |
| Decision roots in raw traces | 94: verdicts `decision_worsened_target` 81, `decision_improved_target` 6, `no_effect` 7 (each verdict shown next to its decision) |
| Outcome analysis chains (failed objectives) | 194: 122 traced, 72 omission, 0 untraced |
| Decisions blamed by the outcome analysis | 55, **all** with a counterfactual "made it worse" verdict |
| On a causal path but no effect (reported, never blamed) | 11 |
| Regression fixtures | 7 pinned; 3 changed, each with a documented reason ([BLACK_BOX.md](BLACK_BOX.md#regression-fixtures-and-their-phase-3-changes)) |

Example (balanced seed 16, partial): power continuity failed; triggering condition `power.unmet_kw
> 0.05` at tick 240; root decision: a science start (counterfactual: without it, no load
shedding); intermediate effects: discretionary load → battery SOC; non-decision cause: the
setting Sun; consequence: blocked the *success* tier.

## Engineering Profile separation

Profiles are computed from behaviour only (ledger and reconstructed history), with the
unchanged provisional weights (D5). Means over 10 seeds:

| Strategy | Systems thinking | Resource efficiency | Crew safety | Scientific ambition | Risk preference | Crisis response | Long-term planning | Nearest (distance) |
|---|---|---|---|---|---|---|---|---|
| survival-first | 0.632 | 0.693 | 0.962 | 0.708 | 0.322 | 0.789 | 0.705 | power-conservative (0.088) |
| power-conservative | 0.563 | 0.699 | 0.962 | 0.710 | 0.357 | 0.755 | 0.730 | survival-first (0.088) |
| balanced | 0.561 | 0.676 | 0.961 | 1.000 | 0.468 | 0.606 | 0.639 | power-conservative (0.357) |
| science-first | 0.089 | 0.413 | 0.583 | 1.000 | 0.968 | 0.000 | 0.225 | high-risk (0.455) |
| high-risk | 0.262 | 0.495 | 0.458 | 1.000 | 0.973 | 0.155 | 0.586 | science-first (0.455) |
| naive-beginner | 0.178 | 0.502 | 0.932 | 0.700 | 0.603 | 0.462 | 0.135 | balanced (0.749) |
| passive | 0.000 | 0.419 | 0.588 | 0.000 | 0.590 | 0.000 | 0.000 | naive-beginner (0.938) |
| random | 0.509 | 0.520 | 0.560 | 0.000 | 0.706 | 0.595 | 0.626 | power-conservative (0.927) |

* Survival-first vs science-first: distance **1.369**. Balanced vs passive: **1.520**.
  High-risk vs balanced: 0.915.
* High-risk has the lowest crew safety (0.458) and the highest risk preference (0.973), but
  science-first is almost as high on risk preference (0.968): both refuse to shelter, so peak
  risk saturates. They differ on crew safety, systems thinking and planning (distance 0.455).
* **Survival-first and power-conservative are nearly identical (0.088):** after the Phase 3
  probe fix both conserve energy with the same night plan and do eco science. That is a true
  similarity of behaviour, not a profile defect.

## Parameter changes, and changes considered but rejected

**Changed** (full reasons and leave-one-out evidence:
[PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md#changes-in-v020)): battery 160 → 240 kWh,
array 15 → 12 kW, initial oxygen 40 → 24 kg, cold penalty 0.001 → 0.0004, component wear × 3; new
objectives, outcome tiers, dose limit, radiation caution and dose-budget alerts, a radiation risk
term, two severity scales.

**Scientific values protected:** all 7 EVIDENCE_LOCKED values (BVAD consumption rates,
electrolysis ratio, ISS water recovery, Chang'E-4 dose rate) and all UNVERIFIED story values
(polar sunset curve, CO₂ thresholds) are unchanged; `tests/test_parameter_governance.py`
enforces the first group and the search refuses both.

**Considered and rejected:**

| Change | Why rejected |
|---|---|
| Lower the ice core's science points | The dominance came from the outcome rule (two easy optional objectives), not the points. Nerfing would make another campaign dominant (brief §5) |
| Raise the dose limit, improve shielding, weaken the storm or stop flare stacking | Lowers radiation difficulty instead of giving information (brief §13). Information alone removed all 9 Phase 2 failures for budget-aware players |
| Touch CO₂ thresholds or the sunset curve | UNVERIFIED story values; must be sourced (D15), not tuned |
| Make high-risk play succeed sometimes | Needs an easier scheduled storm or a different probe: tuning to a target |
| Change profile weights to separate high-risk from science-first | Profile weights are a product decision (D5); the profile must derive from behaviour |
| Thermal conductance | Phase 2 showed a cliff (0.04 → crew loss); internal heat keeping the habitat warm is a correct lesson |
| Wear × 1 (v0.1.0) | Balanced success 100 % in 100 seeds, outcomes barely seed-dependent |
| Battery 200 / array 10.5 | Balanced probe success 0 % (sensitivity) |
| Battery 280 / array 13.5 (more margin) | Balanced probe 100 %, i.e. guaranteed; kept as the first alternative if playtests show v0.2.0 is too tight (D23) |
| Initial oxygen 40 kg | Oxygen generation off becomes a free, dominant action (success → exceptional in 20/20) |

**Sensitivity around v0.2.0** (50 seeds; balanced / survival-first success):

| Parameter | Values (shipped in bold) | Balanced success | Survival-first success |
|---|---|---|---|
| Battery kWh | 160 / 200 / **240** / 280 / 320 | 0 / 0 / **96** / 100 / 100 % | 94 % at every value |
| Array kW | 9 / 10.5 / **12** / 13.5 / 15 | 0 / 0 / **96** / 100 / 100 % | 0 / 94 / **94** / 94 / 94 % |
| Initial O₂ kg | 16 / 20 / **24** / 32 / 40 | 96 % at every value | 94 %; end reserves met 6 / 98 / 98 / 98 / 98 % |
| Cold penalty | 0.0002 / **0.0004** / 0.0007 / 0.001 | 96 % at every value | 94 % at every value |
| Habitat core kW | 1.0 / 1.25 / **1.5** / 1.75 / 2.0 | 100 / 100 / **96** / 0 / 0 % | 94 % at every value |
| O₂ generator kW | 0.75 / 1.1 / **1.5** / 2.0 / 2.5 | 100 / 100 / **96** / 0 / 0 % | 94 % at every value |
| Thermal conductance | 0.01 / **0.015** / 0.02 / 0.03 / 0.04 | 98 / **96** / 0 / 0 / 0 % | 94 / **94** / 94 / 0 / 0 % (partial) |
| Habitat shielding | 0.3 / 0.45 / **0.6** / 0.8 / 1.0 | 96 / 96 / **96** / 94 / 92 % | 100 / 96 / **94** / 0 / 0 % (mission failed: shelters so much it misses science) |
| Radiation limit mSv | 10 / 12.5 / **15** / 20 / 25 | 0 / 90 / **96** / 96 / 96 % | 0 / 92 / **94** / 94 / 94 % |
| Science payload kW | 0.6 / **1.2** / 1.8 / 2.4 | 98 / **96** / 90 / 16 % | 94 % at every value |
| SPE tick | 60 / 100 / **122** / 160 / 200 | 90 / 88 / **96** / 94 / 2 % | 92 / 96 / **94** / 98 / 100 % |

The balanced probe sits at a **cliff edge** for battery, array, habitat-core load, O₂-generator
load and conductance: it has a fixed night plan, so it either fits the night's energy budget or
does not. Survival-first is robust across almost the whole grid. This fragility of the balanced
*probe* is recorded under [D23](USER_DECISIONS_REQUIRED.md#d23-exact-values-of-the-v020-gameplay-parameters)
for playtesting.

## Resource trajectories

Backend-only CSV and JSON, one row per tick (34 columns: power, battery, O₂, CO₂, water, food,
habitat and sink temperature, dose rate, received rate, crew dose, projected dose margin, crew
health, science, data, link, rover battery, risk, phase, active science, crew locations, alerts,
decisions, events). Regenerate with
`python -m app.simulation.analysis.balancing trajectory --representative reports/trajectories`.

| Trajectory | Mission | Outcome | Battery min (tick) / end | Load-shed ticks | End O₂ / water days | Crew dose / min health | Science pts / campaigns | Decisions |
|---|---|---|---|---|---|---|---|---|
| balanced success | balanced seed 1 | success | 0.08 (240) / 0.08 | 0 | 7.1 / 2.7 | 11.9 mSv / 0.98 | 123 / 3 | 15 |
| science-heavy success | expert seed 1 | exceptional | 0.33 (240) / 0.33 | 0 | 3.4 / 4.1 | 11.9 / 0.98 | 129 / 3 | 21 |
| survival-first success | survival-first seed 1 | success | 0.50 (240) / 0.50 | 0 | 5.1 / 3.8 | 11.9 / 0.98 | 85 / 2 | 17 |
| survival-first, science sacrificed | survival-first seed 2 | mission failed | 0.50 (240) / 0.50 | 0 | 5.1 / 3.8 | 13.2 / 0.92 | 83 / 1 | 14 |
| beginner recovery | naive seed 1 | partial | 0.00 (226) / 0.00 | 15 | 7.8 / 2.2 | 12.1 / 0.91 | 84 / 2 | 6 |
| high-risk failure | high-risk seed 2 | crew loss | 0.00 (219) / 0.00 | 16 | 7.8 / 2.3 | 35.5 / 0.00 | 125 / 3 | 6 |
| passive mission failure | passive seed 1 | mission failed | 0.00 (226) / 0.00 | 15 | 7.8 / 2.2 | 19.3 / 0.86 | 0 / 0 | 0 |
| random failure | random seed 1 | crew loss | 0.65 (190) / 0.65 | 0 | 6.5 / 4.2 | 20.2 / 0.00 | 0 / 0 | 21 |

The brief asked for a "survival-first partial": in v0.2.0 survival-first never ends partial (0 of
500); its non-success mode is a crew-safe mission failure (a science campaign not completed), so
both its success and that failure are exported. The science-heavy success is the `expert` probe:
the science-first probe itself never succeeds.

## Invariants, fuzzing, determinism, performance

All runs on the final code (2 CPUs, CPython 3.13), 2026-10-12.

| Check | Result |
|---|---|
| Test suite with PostgreSQL 16 + Redis 7 | **540 passed**, 0 failed, 0 skipped (114 s) |
| Test suite without infrastructure | 534 passed, 6 skipped (the PostgreSQL / Redis tests), 0 failed |
| PostgreSQL / Redis tests alone | 6 passed |
| Replay, Future Lens, Black Box, cascades, compatibility (focused files) | 158 passed |
| Alembic `upgrade head` + `check`, PostgreSQL and SQLite | no drift on either |
| Server smoke over HTTP (create, decide, rewind to tick 50, run to 240, verify, Black Box, Future Lens) | health and readiness ok (database, Redis, scenarios); ledger and replay verify; 0 ERROR log lines |
| Invariant sweep (`--strict`, 11 strategies × 500 seeds) | 5,500 missions, 1,301,800 states, **0 violations** (Phase 2: 5,000 / 1,174,210 / 0) |

**Determinism.** Two separate processes, seed 12345, 240 ticks: final state hash
`da7349cb7f1d5c75`, event stream `158ed13bf3be9b29`, Black Box `796b8720f8f4380d`, Future Lens
(shelter candidate at tick 130) `2ac24fd86fafae49`, identical in both. A 100-seed sweep of 11
strategies (1,100 missions) is identical with 2 workers and with 1 (mission rows hash
`15af764c59d7`) and matches the same 1,100 missions of the 500-seed run field for field. The
eight v0.1.0 golden missions replay byte-identically (`test_scenario_compat.py`).

**Fuzzing** (`HYPOTHESIS_PROFILE=fuzz`, 500 examples per property; 75 tests, all passed, 399 s):

| Property | Examples passed | Failed | Time |
|---|---|---|---|
| Any decision sequence keeps the engine sound | 500 (79 generated inputs discarded as invalid by the strategy's filters) | 0 | 258 s |
| Parameter perturbations keep states valid | 500 | 0 | 63 s |
| Random decision sequences replay identically | 500 | 0 | 51 s |
| Future Lens isolation for any request | 240 (input space exhausted) | 0 | 24 s |

**Performance** (`bench`, compared with Phase 2):

| Measurement | Phase 2 (v0.1.0) | Phase 3 (v0.2.0) |
|---|---|---|
| Engine alone, 240 ticks | 39.7 ms | 43.1 ms |
| Mission with the `balanced` strategy / with invariants | 122.3 / 159.1 ms | 130.8 / 168.3 ms |
| Replay 240 ticks / with history | 51.1 / 134.1 ms | 59.3 / 145.7 ms |
| Future Lens default / 5 × 16 × 72 h | 91.1 ms / 2.94 s | 94.2 ms / 3.32 s |
| Black Box with counterfactuals, 5 cases (mean / max) | 106 / 234 ms | 162 / 461 ms |
| 100 missions, 1 worker / 2 workers | 123.3 / 71.0 ms per mission | 148.3 / 78.3 ms |
| 1,000 missions, 2 workers | 65.1 ms per mission (15.4 /s) | 74.7 ms per mission (13.4 /s) |
| Peak RSS parent / worker | 75 / 54 MB | 89 / 56 MB |

The engine slowdown comes from the scenario, not the code: on the same machine, 25 missions each,
Phase 3 code runs v0.1.0 in 37.1–39.3 ms (Phase 2 code: 36.2–37.9 ms, within noise) and v0.2.0
in 42.6–44.7 ms (four more metrics, three more alerts and five more objectives evaluated every
tick). The Black Box is slower because the outcome analysis adds counterfactual replays to verify
every blamed decision. All `test_performance.py` thresholds still pass.

## Remaining issues

* **Balanced probe on a cliff edge** (sensitivity above, D23).
* **High-risk never succeeds; naive is always partial; science-first never succeeds** (see
  [Success criteria](#success-criteria)).
* **Inert events:** removing the relay outage, the water-processor pump fault or the freeze damage
  changes no outcome or objective (the freeze event never fires for any scripted strategy).
* **Universal alerts:** the two radiation alerts and comms-link-down fire in every mission
  (scheduled storm and relay outage).
* **Maintenance is LOCAL** (D24); thermostat inside the comfort band is LOCAL (a modelled lesson).
* **Seed sensitivity** improved (distinct final states per 500 seeds, Phase 2 detector: survival-first 62 → 113,
  naive 18 → 108, power-conservative 23 → 74, science-first 27 → 66, high-risk 25 → 82, passive
  17 → 23; balanced 61 → no longer flagged) but six strategies are still flagged as
  seed-insensitive by the Phase 2 detector.
* Open decisions unchanged by Phase 3: D18 (end objectives after crew loss), D19 (EVA return),
  D20 (silent no-op decisions). D21 partly addressed (information), D22 provisionally (weight
  open), D23 and D24 new.

## Reproducing

```bash
L="uv run python -m app.simulation.analysis.balancing"
$L sweep --strategy all,reserve_keeper,always_shelter,expert --seeds 500 --strict --format json --output reports/phase3/strict-500.json
$L diagnose --seeds 500 --ablation-seeds 50 --impact-seeds 10 --sensitivity-seeds 50 --output-dir reports/phase3/diagnose-500
$L quality --lens-seeds 3 --failure-seeds 100 --failures-per-strategy 5 --profile-seeds 10 --output reports/phase3/quality.json
for r in balanced survival_first science_first; do $L audit --reference $r --seeds 5 --output reports/phase3/audit-$r.json; done
$L trajectory --representative reports/phase3/trajectories
$L search --seeds 30 --refine-seeds 100 --top 3 --param power.solar_rated_kw=11,12,13 \
    --param power.battery.capacity_kwh=200,240,280 --param "degradation.components.*.wear_per_tick*=1,3" \
    --output-dir reports/phase3/search
```

About 75 minutes on 2 cores. `reports/` is git-ignored: regenerate rather than commit results.


