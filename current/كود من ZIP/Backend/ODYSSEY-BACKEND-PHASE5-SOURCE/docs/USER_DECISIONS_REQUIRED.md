# User Decisions Required

These are product, gameplay or policy choices the backend deliberately did **not** make. For
each one the backend ships a *generic mechanism* plus a clearly marked **provisional default**,
so nothing is blocked. Changing a default is a data/configuration change unless stated
otherwise.

Status legend: **Mechanism ready**: change data/config only. **Partial**: some code is needed.
**Not started**: intentionally out of scope until decided.

| # | Decision | Status |
|---|---|---|
| D1 | [Scenario balancing (all LUNA-01 numbers)](#d1-scenario-balancing) | Provisional v0.2.0 (Phase 3) |
| D2 | [Mission length and time model](#d2-mission-length-and-time-model) | Mechanism ready |
| D3 | [Objectives and outcome thresholds](#d3-objectives-and-outcome-thresholds) | Provisional v0.2.0 (Phase 3) |
| D4 | [Final scoring (if any)](#d4-final-scoring) | Not started |
| D5 | [Engineering profile weights](#d5-engineering-profile-weights) | Mechanism ready |
| D6 | [Future Lens honesty and confidence](#d6-future-lens-honesty-and-confidence) | Mechanism ready; omniscient off by default (Phase 4) |
| D7 | [Player control surface](#d7-player-control-surface) | Partial |
| D8 | [Multiplayer role permissions](#d8-multiplayer-role-permissions) | Mechanism ready |
| D9 | [Authentication and identity](#d9-authentication-and-identity) | Not started |
| D10 | [Final NASA datasets](#d10-final-nasa-datasets) | Partial |
| D11 | [ORION production provider and personality](#d11-orion-provider-and-personality) | Mechanism ready |
| D12 | [Mission DNA gene set](#d12-mission-dna-gene-set) | Partial |
| D13 | [Student data retention and erasure](#d13-student-data-retention-and-erasure) | Mechanism ready |
| D14 | [Rover charger behaviour after an energy transfer](#d14-rover-charger-behaviour-after-an-energy-transfer) | Mechanism ready |
| D15 | [Unverified scientific evidence](#d15-unverified-scientific-evidence) | Partial |
| D16 | [Project licence](#d16-project-licence) | Not started |
| D17 | [Leaderboards, achievements, branding, copy](#d17-leaderboards-achievements-branding-copy) | Not started |
| D18 | [End-of-mission objectives after an early conclusion](#d18-end-of-mission-objectives-after-an-early-conclusion) | Mechanism ready |
| D19 | [Where an EVA crew member returns during a radiation event](#d19-where-an-eva-crew-member-returns-during-a-radiation-event) | Partial |
| D20 | [Decisions that have no effect while a load is shed](#d20-decisions-that-have-no-effect-while-a-load-is-shed) | Partial |
| D21 | [Overlapping radiation events](#d21-overlapping-radiation-events) | Partly addressed (Phase 3: information) |
| D22 | [What the mission risk index includes](#d22-what-the-mission-risk-index-includes) | Provisional (b), weight open |
| D23 | [Exact values of the v0.2.0 gameplay parameters](#d23-exact-values-of-the-v020-gameplay-parameters) | **PLAYTEST-FROZEN** (Phase 4): battery 240 kWh, array 12 kW |
| D24 | [Should maintenance be a major decision?](#d24-should-maintenance-be-a-major-decision) | **Resolved** (Phase 4): LOCAL / CUMULATIVE |
| D25 | [Should players see upcoming phase names?](#d25-should-players-see-upcoming-phase-names) | **Resolved** (Phase 4): general phase visibility rule |

Decisions D18–D22 and the measured notes under D1, D3 and D6 come from the Phase 2 Balancing Lab
runs. Phase 3 (LUNA-01 v0.2.0) acted on D1, D3, D21 and D22 under the Phase 3 brief and added
D23–D24; its evidence is in [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md) and
[PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md). Evidence: [BALANCING_FINDINGS.md](BALANCING_FINDINGS.md).

---

## D1. Scenario balancing

**Decision.** Every numeric constant in `app/simulation/scenarios/data/luna-01.yaml` (battery
size, solar rating, dust rate, fault probabilities, health penalties, event timings, science
windows...).

**Why it matters.** Balancing decides whether the mission is trivial, fair or impossible, and
which trade-offs students actually feel.

**What the provisional numbers currently do** (measured, seeds 1/7/42, no player decisions):

* Every run ends `mission_complete_partial`: crew survives, but the battery reaches 0 % in the
  final low-power phase, science return is 0 and the radiation-safety objective fails because
  of the tick-122 solar particle event (crew dose ≈ 19 mSv vs a 15 mSv limit).
* Internal heat from running equipment exceeds habitat heat loss for most of the mission, so
  turning heaters *off* mid-mission produces no thermal warning within 48 h. Thermal pressure
  only appears once load shedding starts near lunar night. If thermal management should be a
  central trade-off earlier, conductance or internal-heat fraction needs tuning.

**Measured in Phase 2** (Balancing Lab, 8 scripted strategies × 500 seeds; nothing was tuned):

* Outcomes are binary per strategy. Balanced, power-conservative, naive-beginner and
  science-first succeed in 100 % of seeds; survival-first and passive are partial in 100 %;
  high-risk loses the crew in 100 %. Only random play produces a mix (0.4 % success, 42.0 %
  partial, 57.6 % crew loss).
* The battery reaches 0 % in **100 %** of missions for every scripted strategy, and the
  `reserves_at_end` objective is never met by them. A dedicated existence probe
  (`reserve_keeper`) shows it *is* reachable (100 % success, reserves met in 99.4 %), so this
  is a strategy-and-tuning question, not an impossibility.
* Randomness barely matters: 17–62 distinct results from 500 seeds per scripted strategy.
* `crew_survival` is met by doing nothing; `oxygen_critical` never fires; `habitat_cold`,
  `radiation_elevated` and `comms_link_down` fire in every scripted mission.
* The strongest single parameters are habitat thermal conductance, battery capacity, O₂
  generator power, habitat shielding and the radiation limit. The full table, with every
  value tried, is in [BALANCING_FINDINGS.md](BALANCING_FINDINGS.md#sensitivity).

**Phase 3 (v0.2.0, provisional).** Five numbers changed, each with a stated reason and a
leave-one-out experiment: battery 160 → 240 kWh, array 15 → 12 kW, initial oxygen 40 → 24 kg, cold
penalty 0.001 → 0.0004, component wear × 3
([PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md#changes-in-v020)). No evidence-locked or
unverified value changed. Result (500 seeds): balanced 96.6 % success, survival-first 97.2 %,
power-conservative 98.4 %, science-first 100 % partial, high-risk 0 % success (crew hurt in
100 %, crew loss 1.8 %), passive 100 % mission failed; battery depletion 0–3.4 % for planners,
100 % for strategies that never prepare for night
([PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md)). The exact values are open as
[D23](#d23-exact-values-of-the-v020-gameplay-parameters).

**Options.** (a) Tune by hand-playtesting; (b) tune with scripted "player archetype" sweeps
(the deterministic engine makes this cheap: about 40 ms per full mission); (c) both.

**Technical consequences.** None in code. Scenario content is hashed and pinned per session,
so existing sessions keep replaying with their original numbers after a re-balance. Bump
`version` in the YAML when you change it.

**Recommended default.** (c): keep the current values as the playtest baseline and re-run the
Balancing Lab (`python -m app.simulation.analysis.balancing diagnose`) after every change.

**Implementation status.** Mechanism ready. `ScenarioDefinition.provisional: true` flags the
current numbers. The Balancing Lab ([BALANCING_LAB.md](BALANCING_LAB.md)) can try any change
with `--set path=value` without editing the shipped scenario.

## D2. Mission length and time model

**Decision.** Tick duration (currently 1 h), mission length (240 ticks = 10 days), and whether
time advances by player request (current API: `POST /advance`), on a wall-clock timer, or both.

**Why it matters.** Pacing, classroom session length, and how stressful crises feel.

**Options.** Player-driven advance (default); server timer per session; client-driven timer.

**Technical consequences.** `time.tick_hours` and `time.max_ticks` are scenario data. A server
timer would need a worker that calls the same service method (`MissionService.advance`); no
engine change.

**Recommended default.** Keep player/teacher-driven advance; let the frontend offer
"advance 1 h / 6 h / to next event".

**Implementation status.** Mechanism ready (no timer worker exists).

## D3. Objectives and outcome thresholds

**Decision.** Which objectives exist, which are required, their thresholds (science ≥ 60 points,
data ≥ 1200 MB, dose < 15 mSv, end reserves ≥ 1 day O₂/water and ≥ 5 % battery), and the outcome
rules (complete = all required + ≥ 50 % optional; partial = all required; crew loss ends the
mission immediately).

**Why it matters.** It defines what "winning" means and therefore what students optimise.

**Measured in Phase 2.** With four optional objectives and a 50 % bar, *any two* optional
objectives give full success. In practice:

* Science and data always come together: both depend on the ice-core window (removing that
  one event drops data return to 0 for every strategy). So "do the ice-core science" alone is
  a complete success, which is why science-first (no sheltering, no power saving, median 4
  decisions) succeeds in 100 % of seeds while failing radiation safety in 100 %.
* `crew_survival` is the only required objective, and the `crew_loss` outcome already catches
  its failure, so the `fallback` outcome (`mission_failed`) is unreachable (0 of 4,000
  missions).
* Survival-first meets radiation safety (98.2 %) but no second objective, so a careful,
  science-free mission is always "partial".

**Phase 3 (v0.2.0, provisional), decided under the Phase 3 brief.** Ten objectives in six
pillars and tiered outcomes: crew loss = critical failure; any primary objective failed = mission
failed (crew may be safe); primary = partial; + safety + stability = success; + efficiency +
science = exceptional (new code `mission_complete_exceptional`). Primary science needs two
completed campaigns, so no single action completes it. Thresholds chosen: two campaigns,
800 MB, dose < 15 mSv, crew health ≥ 0.5, unmet power ≤ 0.05 kW, CO₂ ≤ 10,500 ppm and ≥ 1 day O₂
and water and habitat ≥ 5 °C, end reserves ≥ 3 days O₂ and water and ≥ 15 % battery, ≥ 100
points. Mechanism and backward compatibility:
[SIMULATION_MODEL.md](SIMULATION_MODEL.md#310-objectives-and-outcomes-luna-01-v020). Still
open: the thresholds themselves, and whether exceptional should be reachable by more than
deliberate expert play (0 of 5,000 player-probe missions, 95.8 % for the `expert` probe).

**Options.** Keep the current tiers; add more tiers; make thresholds difficulty-dependent.

**Technical consequences.** All are declarative `objectives` / `outcomes` entries in the
scenario. The last outcome rule must stay an unconditional catch-all (validated).

**Recommended default.** Keep the current structure and tune thresholds together with D1.

**Implementation status.** Mechanism ready.

## D4. Final scoring

**Decision.** Whether ODYSSEY shows a numeric score at all and, if so, its formula.

**Why it matters.** Scores change behaviour (and comparisons between students).

**Options.** No score (outcome + profile only); a composite score; per-dimension badges.

**Technical consequences.** A score would be a pure function of `MissionRecord` (like the
profile) plus a new endpoint; no engine change.

**Recommended default.** No numeric score for the hackathon; show outcome, objectives and the
descriptive engineering profile.

**Implementation status.** Not started (intentionally).

## D5. Engineering profile weights

**Decision.** How features combine into the seven dimensions (systems thinking, resource
efficiency, crew safety, scientific ambition, risk preference, crisis response, long-term
planning).

**Why it matters.** The profile tells students *how* they engineered. Weights decide what each
label means.

**Options.** Keep the provisional weights; derive weights from playtest data; let teachers
pick presets.

**Technical consequences.** Weights live in `app/simulation/analysis/profile_weights.yaml`
(versioned; the version is stored with every persisted profile). Feature definitions are
documented in `profile.py`.

**Recommended default.** Keep `provisional-0.1` until playtesting, then revise once.

**Implementation status.** Mechanism ready.

## D6. Future Lens honesty and confidence

**Decision.** (1) What students may foresee: `known_only` (default: unforeseeable scripted
events such as the solar particle event are hidden and random faults are sampled with
*derived* seeds) vs `omniscient` (shows the real future; intended for teachers/debugging).
(2) The confidence formula and labels (`high`/`medium`/`low`). (3) Defaults for horizon
(24 ticks) and samples (4).

**Why it matters.** An omniscient lens turns the game into reading the answer key. The
confidence label shapes how much students trust predictions.

**Technical consequences.** Both policies exist. The API currently allows any caller to request
`omniscient`; restricting it needs D8/D9 (roles/auth) or a setting. Since Phase 2 the Future
Lens call passes through `MissionService._authorize(..., FUTURE_LENS, knowledge_policy)`, so a
role policy can refuse `omniscient` without new plumbing.

**Measured in Phase 2** ([details](BALANCING_FINDINGS.md#future-lens-quality)):

* About a third of single-decision candidates are indistinguishable from the baseline over
  24 h. Whether to say "no visible effect" or hide such a candidate is a UX choice.
* Explanations cover the first three predicted warnings *by time*, so a warning introduced by
  the candidate can go unexplained when earlier baseline warnings exist. Alternative: rank
  warnings by "new versus the baseline" first.
* The sample-spread factor is almost always 1, so the confidence label is effectively a
  function of the horizon. Whether that is acceptable or the formula should change is part
  of (2).

**Phase 3.** Explanations now trace candidate-introduced warnings first and at the tick the
traced sample raised them: 27 of 27 explained (Phase 2: 21 of 27). New output: `new_warnings`
and `objective_outlook` (projected objective status, no hidden events revealed). The confidence
formula is unchanged and still effectively horizon-driven (sample spread ≤ 0.025).

**Recommended default.** `known_only` for students; expose `omniscient` only to a teacher role
once roles exist.

**Implementation status.** Mechanism ready; access restriction pending D8/D9.

**Phase 4.** Omniscient projections are now refused on every Future Lens endpoint unless the
server switch `ODYSSEY_FUTURE_LENS_OMNISCIENT_ENABLED=true` is set (default off); the role policy
still applies on top. The frontend-safe Future Lens view also removes two indirect hints that
the raw result gave in `known_only` mode: the assumption line naming which hidden events were
excluded, and a confidence knowledge factor that dropped only when hidden events remained.
Still open: who may switch omniscient on (teacher role, D8/D9), and (2)/(3) above.

## D7. Player control surface

**Decision.** Which of the nine engine decision types the product exposes, in which phases,
and with what UX (`set_subsystem_mode`, `set_thermal_setpoint`, `set_ration_level`,
`schedule_maintenance`, `set_crew_location`, `start/stop_science_activity`, `rover_command`,
`clean_solar_array`).

**Why it matters.** The control surface *is* the game design.

**Options.** Expose all; expose a subset per phase; unlock progressively.

**Technical consequences.** Restricting by phase would add a scenario field (e.g.
`allowed_decisions` per phase) checked in `SimulationEngine.apply_decision`, which is a
small engine change. Restricting by role is already possible through the permission policy
(D8).

**Recommended default.** Expose all nine; revisit after playtesting.

**Implementation status.** Partial (all types implemented; no per-phase gating).

## D8. Multiplayer role permissions

**Decision.** What Commander, Power Engineer, Life Support and Science Officer may each do.

**Why it matters.** Defines cooperative play.

**Technical consequences.** `PermissionPolicy` is pluggable. `RoleTablePolicy` takes a
`{role: {action: [decision types]}}` table and is covered by tests. The default
`AllowAllPolicy` allows everything (single-player behaviour).

**Recommended default.** Keep `AllowAllPolicy` until multiplayer is designed.

**Implementation status.** Mechanism ready.

## D9. Authentication and identity

**Decision.** Whether and how users sign in (school SSO, teacher-issued codes, anonymous).

**Why it matters.** Without auth, anyone holding a session id can act on that session, and
`participant_id` is a self-asserted claim. That is fine for a local hackathon demo, but not
for a public deployment with real students.

**Options.** Anonymous session codes; OAuth/OIDC via a hosted IdP; school SSO.

**Technical consequences.** Add an auth dependency that resolves the caller to a participant
and passes it to `MissionService._authorize`. Every write path already goes through it.

**Recommended default.** Anonymous join codes for the hackathon; OIDC before any public
deployment.

**Implementation status.** Not started. No identity product was invented (per spec). Phase 2
verified that the absence of auth cannot corrupt the simulation architecture and documented the
integration point ([ARCHITECTURE.md](ARCHITECTURE.md#authentication-seam),
`tests/test_auth_seam.py`).

**Phase 4.** The application contract keeps the seam explicit: every route resolves the caller
through one dependency (`app/api/deps.py::get_principal`, "anonymous" today) and idempotency
keys are scoped by that principal, so an auth layer replaces one function without touching
mission logic. In production the raw engine endpoints and session seeds are hidden by default
(`ODYSSEY_INTERNAL_ENDPOINTS_ENABLED`), but holding a session id still grants full control of
that session until this decision is made.

## D10. Final NASA datasets

**Decision.** Which NASA products feed scenario authoring and evidence. See
[NASA_DATA_OPTIONS.md](NASA_DATA_OPTIONS.md).

**Why it matters.** Credibility with Space Apps judges, and licence/attribution obligations.

**Technical consequences.** Provider interfaces exist; only DONKI has a live adapter (off by
default). Any new dataset is a new provider class plus fixtures.

**Recommended default.** LRO Diviner (temperatures), DONKI (space weather), and LOLA/LRO
illumination products for polar solar availability.

**Implementation status.** Partial.

## D11. ORION provider and personality

**Decision.** Production model provider (Gemini, OpenRouter, Ollama...), its cost, and ORION's
voice and personality.

**Why it matters.** Cost, latency, privacy (mission context leaves the server), tone.

**Technical consequences.** Any OpenAI-compatible endpoint works via configuration. A native
Gemini adapter would be a ~60-line `AIProvider` subclass. Grounding validation applies to every
provider, and ungrounded answers fall back to the deterministic mock.

**Recommended default.** Mock in development; local Ollama for free demos; decide a hosted
provider only if needed.

**Implementation status.** Mechanism ready. Personality is not tuned (per spec).

## D12. Mission DNA gene set

**Decision.** Which characteristics count as "major" (currently shelter, rover, science starts,
maintenance, array cleaning, rationing), bucket boundaries, and the code format
`LUNA01-<outcome>-<10 base32 chars>`.

**Why it matters.** It decides when two missions count as "the same story", which matters for
sharing and comparison.

**Technical consequences.** Changing genes changes codes. `DNA_VERSION` is part of the hash
and stored with each record, so old and new codes never collide silently.

**Recommended default.** Keep version 1 for the hackathon.

**Implementation status.** Partial (visual representation out of scope by spec). Phase 3 added
the outcome tag `MX` for `mission_complete_exceptional` (it was mis-tagged `IP`, "in progress");
codes of the other outcomes are unchanged.

## D13. Student data retention and erasure

**Decision.** How long sessions are kept, and how erasure requests are honoured, given that
the decision ledger is append-only by design.

**Why it matters.** Privacy obligations for minors vary by jurisdiction.

**Technical consequences.** The database refuses UPDATE/DELETE on `mission_decisions`. On
PostgreSQL a deliberate retention job can delete inside a transaction that sets
`SET LOCAL odyssey.allow_ledger_delete = 'on'` (see [DATABASE.md](DATABASE.md)). The ledger
holds no names: participant handles live in `mission_participants`.

**Recommended default.** Keep handles pseudonymous; delete whole sessions after a fixed period
(e.g. one school term).

**Phase 4.** Two additive tables hold derived data: `mission_realtime_events` (realtime
envelopes, pruned to the last 64 state versions per timeline) and `idempotency_records` (stored
command responses, kept indefinitely today). Neither contains names; both cascade or can be
deleted freely (they are not the ledger). An expiry for idempotency records (e.g. 24 h) belongs
to the same retention decision.

**Implementation status.** Mechanism ready; no retention job scheduled.

## D14. Rover charger behaviour after an energy transfer

**Decision.** After a rover → habitat energy transfer ends, the rover charger (a normal,
lowest-priority load) starts recharging the rover from the habitat bus on the **next** tick
unless the player turns the charger off or stows the rover.

**Why it matters.** A student who drains the rover to save the habitat may be surprised when
the habitat later feeds it back.

**Options.** Keep (realistic: chargers are automatic); auto-set charger mode to `off` when a
transfer starts; emit an explicit warning event.

**Technical consequences.** Small change in `power.py` or a decision-triggered scenario event.

**Recommended default.** Keep the physics, and have the frontend/ORION point it out.

**Implementation status.** Mechanism ready. (A *same-tick* two-way flow was a bug and has been
fixed. This decision is about the following ticks.)

## D15. Unverified scientific evidence

**Decision.** Accept, replace or source two evidence items marked `unverified`
(`co2_crew_limits`, `lunar_polar_illumination`), and upgrade `verified_secondary` items to
primary NASA sources (e.g. NTRS for BVAD).

**Why it matters.** Every scientific assumption should be traceable (spec §16).

**Technical consequences.** Edit `app/science/data/evidence.yaml`. Tests check every evidence
reference resolves.

**Recommended default.** Source both before judging. The BVAD report itself (on NASA NTRS) and LOLA
illumination products are the natural primary sources.

**Implementation status.** Partial. Phase 2 audited every entry
([SCIENCE_EVIDENCE_AUDIT.md](SCIENCE_EVIDENCE_AUDIT.md)): 8 verified, 3 unverified, plus two
registry corrections to make (a source date and the attribution of the food value). Nothing was
changed in the registry.

## D16. Project licence

**Decision.** Open-source licence (e.g. MIT, Apache-2.0) or proprietary.

**Why it matters.** Space Apps submissions are usually public. Dataset licences may impose
attribution.

**Technical consequences.** `pyproject.toml` currently says "not yet chosen".

**Recommended default.** Apache-2.0 (patent grant, common for NASA-adjacent projects).

**Implementation status.** Not started.

## D17. Leaderboards, achievements, branding, copy

**Decision.** Leaderboard mechanics, achievement rules, branding, and the user-facing text for
every `message_key` (events, alerts, phases, objectives, outcomes).

**Why it matters.** Product and frontend scope.

**Technical consequences.** The backend emits stable `message_key`s and never ships dialogue.
Leaderboards would read `mission_outcomes` / `mission_dna`.

**Recommended default.** None. Out of backend scope.

**Implementation status.** Not started (out of scope by spec).

## D18. End-of-mission objectives after an early conclusion

**Decision.** When the crew is lost before the scheduled end, should `evaluate: at_end`
objectives (currently `reserves_at_end`) still be evaluated on the final state?

**Why it matters.** Today they are. A mission that ends early with crew loss can "achieve"
end reserves simply because it stopped consuming them. Measured: high-risk play meets
`reserves_at_end` in 2.0 % of 500 seeds, all of them crew-loss missions; in random play 39 of
the 46 seeds that meet it in the 100-seed set end early with crew loss. The outcome is still
`mission_failed_crew_loss`, but per-objective reports and the engineering profile see a
"success".

**Options.** (a) Keep (objectives are facts about the final state); (b) mark at-end objectives
`not_evaluated` when the mission ends before `max_ticks`; (c) evaluate them as failed.

**Technical consequences.** (b) or (c) is a few lines in the end-of-tick objective evaluation
plus a new objective status; replays of old sessions would show different objective statuses
(the scenario hash pins numbers, not engine rules), so bump the engine version.

**Recommended default.** (b), because it is the most honest wording for students.

**Implementation status.** Mechanism ready (current behaviour is (a)); nothing changed.

## D19. Where an EVA crew member returns during a radiation event

**Decision.** A shelter order skips crew who are on EVA. When their EVA ends, they return to
the **habitat**, even if the rest of the crew is in the shelter and the radiation event is
still running. Should the engine send them to the shelter instead?

**Why it matters.** A student who ordered "everyone to the shelter" may not expect one member
to come back to the habitat (shielding 0.6 instead of 0.15) and keep accumulating dose until
they re-issue the order. Measured with an SPE moved to tick 200 (during a cleaning EVA): the
highest crew dose was 16.87 mSv with the order re-issued as soon as the member returned (most of
it from the EVA itself), versus 22.0 mSv when the order was not re-issued. (The Balancing Lab's own strategies originally made
exactly this mistake; that was a probe bug, fixed in Phase 2.)

**Options.** (a) Keep (explicit orders only); (b) return to the shelter while a shelter order
is active; (c) keep, but emit an event or alert "crew member returned to the habitat during a
radiation event" so the UI or ORION can point it out.

**Technical consequences.** (b) needs a small piece of state ("shelter order active") and a
change in `crew.py`; (c) is a scenario alert or an engine event. Both change replays of
affected sessions, so bump the engine version.

**Recommended default.** (c): keep the physics explicit and make the consequence visible.

**Implementation status.** Partial: behaviour documented in
[SIMULATION_MODEL.md](SIMULATION_MODEL.md); no change made.

## D20. Decisions that have no effect while a load is shed

**Decision.** The engine accepts mode changes for a consumer that is currently receiving no
power. Example (balanced, seed 1): CO₂ scrubber set to `boost` at tick 227 with the battery
empty. Its demand rises from 0.60 to 0.84 kW but its allocation stays 0.0 kW for the rest of
the mission, and CO₂ keeps rising (5,317 → 17,710 ppm by tick 240). The Balancing Lab flags
this as a "no-op decision": removing it changes nothing.

**Why it matters.** A student's emergency action silently does nothing. That is physically
right (no power, no scrubbing) but may feel unfair without feedback.

**Options.** (a) Keep, silently; (b) accept but return a warning in the decision response
("subsystem currently unpowered"); (c) reject with a code (`subsystem_unpowered`).

**Technical consequences.** (b) is an additive field in the decision response and does not
change the ledger; (c) changes which decisions are valid, so replays of old sessions could
fail validation: bump the engine version.

**Recommended default.** (b).

**Implementation status.** Partial: the measurement exists (`impact.py`, `diagnostics.py`);
behaviour unchanged.

## D21. Overlapping radiation events

**Decision.** Radiation multipliers from concurrent events multiply. A random minor flare (×5)
that overlaps the scripted solar particle event (×40) gives ×200 for the overlap. Is that the
intended difficulty?

**Measured.** With the probes' reactive sheltering (shelter when the dose rate exceeds
0.3 mSv/h), the radiation objective fails in **9 of 500 seeds (1.8 %)** for every sheltering
strategy (max dose 18.7 mSv). Forked replays of those 9 seeds show two mechanisms, and that
**neither is strictly unavoidable**:

* 3 seeds (39, 291, 297): a flare starts one tick before the SPE. Its ×5 reading (0.285 mSv/h)
  is below both the probe threshold and the `radiation_elevated` alert (0.5 mSv/h), so the crew
  spends the SPE's first hour at ×200 in the habitat (6.84 mSv). Sheltering on *any* reading
  above the 0.057 mSv/h baseline avoids all three.
* 6 seeds (2, 12, 63, 259, 449, 482): the flare overlaps the SPE while the crew is already
  sheltered, leaving 12–15 mSv. Background dose in the habitat then crosses 15 mSv before the
  end. Spending 36 extra hours in the shelter after the event fixes 5 of them; seed 2 needs
  about 60.

So avoiding it needs a player who reacts to readings below the warning alert and tracks a
cumulative dose budget. Whether that is a good lesson or an unfair hidden requirement is a design
call.

**Options.** (a) Keep multiplicative stacking; (b) take the maximum multiplier instead of the
product; (c) keep stacking but forbid random flares during scripted events; (d) keep, and make
the dose budget visible (an alert on cumulative dose, ORION/Black Box explanations of the
overlap).

**Technical consequences.** (b) is a change in how modifiers combine (engine rule, version
bump). (c) needs a small schema addition (random triggers have no "not during event X"
condition today), or, as pure data, splitting the flare's random window so it excludes the
ticks around the SPE. (d) is scenario data (an alert on `crew.max_dose_msv`).

**Recommended default.** (d), since the Black Box already traces the flare as a cause; revisit
with D1.

**Phase 3.** Information was added, difficulty was not lowered: a `radiation_above_background`
caution (> 0.12 mSv/h), dose margin and projected end-of-mission dose (baseline rate only) and
dose-budget alerts. Budget-aware sheltering (balanced, survival-first, expert) now fails 0 of
500 seeds; probes that only react to the caution fail exactly the 6 "slow accumulation" seeds;
stacking itself is unchanged. Options (b)–(d) remain open.

**Implementation status.** Partly addressed (information); stacking rule unchanged.

## D22. What the mission risk index includes

**Decision.** `risk.mission` is a weighted sum of seven terms (oxygen, CO₂, water, food,
temperature, battery, crew health; weights in `analysis.risk_terms`). It has **no radiation
term**, so neither the risk index nor Future Lens confidence reflects radiation exposure until
it shows up as lost health.

**Why it matters.** The risk curve shown to students stays flat through the solar particle
event, the scenario's main radiation crisis.

**Options.** (a) Keep; (b) add a term for crew dose or received dose rate; (c) show radiation as
a separate indicator.

**Technical consequences.** (b) is scenario data only (`risk_terms` entry plus a weight).
Choosing the weight is a scoring decision, which is why it was not done here.

**Recommended default.** (c), keeping the index about life support, or (b) with a weight chosen
during playtesting.

**Implementation status.** Provisionally resolved with (b) in LUNA-01 v0.2.0: risk term
`crew.projected_dose_margin_msv`, weight 0.6 (same scale as habitat temperature and water). The
weight is open. Effect: the risk index now rises with radiation, so a hidden storm produces a
larger risk error in Future Lens (max 0.60 instead of 0.02), which is the honest consequence.

## D23. Exact values of the v0.2.0 gameplay parameters

**Decision.** Phase 3 changed five LUNA-01 numbers: battery 160 → 240 kWh, array 15 → 12 kW,
initial oxygen 40 → 24 kg, cold penalty 0.001 → 0.0004, component wear × 3. Each has a stated
reason and a leave-one-out experiment ([PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md#changes-in-v020)).
The *direction* of each change is evidence-based; the exact value is a choice within a family.

**Why it matters.** The bounded search (`reports/phase3/search/`) ranks the shipped values first
but finds neighbours that pass the same 13 diagnostic envelopes (array 13 kW or battery 280 kWh,
each with 9× the v0.1.0 wear). More importantly, the sensitivity sweep shows that **balanced play
sits at a cliff edge** near the shipped values: battery 200 kWh or array 10.5 kW → balanced
success 0 %; 240 kWh / 12 kW → 96 %; 280 kWh or 13.5 kW → 100 %. The scripted balanced probe has a
fixed night plan, so it either fits the night's energy budget or it does not; real players adapt,
but the margin for a typical student is unknown until playtests. Picking the margin is a
difficulty decision, not a scientific one.

**Options.** (a) Keep v0.2.0; (b) pick another configuration from the search report after
playtesting; (c) offer two scenario versions (e.g. a gentler classroom variant) as separate,
version-pinned scenarios.

**Technical consequences.** Data only (`luna-01.yaml`, bump `version`). Sessions keep the
scenario version they started with.

**Recommended default.** (a) until human playtests, then (b) at most once. If playtesters
without Future Lens practice often run the battery empty, move one step towards more margin
(battery 280 kWh or array 13.5 kW): balanced probe 100 %, still not trivial for the other styles.

**Resolution (Phase 4): PLAYTEST-FROZEN at battery 240 kWh and array 12 kW** (option (a)). These
values are frozen for development and playtesting: no tuning, no automated search to replace
them, and no change because another configuration scores better on the scripted probes. This is
**not** a permanent final decision: a future adjustment requires **human playtest evidence**
(e.g. how often real players run the battery empty, by experience level), recorded here
together with the new values, then a new scenario version so that existing sessions keep v0.2.0.
The other three v0.2.0 changes (initial oxygen, cold penalty, wear) stay as shipped under the
same rule. Phase 4 re-ran the representative 500-seed checks and found the distributions
unchanged ([PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md) remains current).

**Implementation status.** PLAYTEST-FROZEN (v0.2.0 shipped; `provisional: true` stays set on the
scenario because the values await playtest evidence).

## D24. Should maintenance be a major decision?

**Decision.** The Phase 3 brief gives "skipping maintenance → temporary efficiency → more
degradation later" as an example decision chain. In v0.2.0, scheduling maintenance is measured as
**LOCAL** impact (it measurably changes component health, but changes no objective or outcome
tier in the decision audit), with or without the × 3 wear change.

**Why it matters.** If maintenance is presented to students as a major engineering trade-off,
it should be one; if it stays a small operational action, the UI and ORION should frame it so.

**Options.** (a) Keep maintenance a local action; (b) make faults consequential, e.g. a fault
that takes a life-support component offline until maintained; (c) make wear depend on load or
temperature so that neglect compounds.

**Technical consequences.** (a) none. (b) and (c) are engine changes in `degradation.py` (opt-in
scenario fields, so earlier scenario versions replay unchanged) plus re-balancing.

**Recommended default.** (a) for the hackathon, framed honestly in the UI; revisit (b) after
playtests.

**Resolution (Phase 4): (a). Maintenance is not a major gameplay decision; it stays a LOCAL /
CUMULATIVE operational mechanic.** Maintenance affects degradation, efficiency, fault probability
and resilience over time, and does not independently determine mission success in ordinary
play. The engine is unchanged (no bug was found). The frontend contract reports maintenance
options with `impact: "local"`, and ORION/UI copy should frame it as routine upkeep. Options (b)
and (c) remain possible future scenario versions if playtests ask for it.

**Implementation status.** Resolved; measured in [DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md).

## D25. Should players see upcoming phase names?

**Decision.** LUNA-01's 13 phases advance on a fixed clock (e.g. `scientific_opportunity` →
`environmental_emergency` at tick 120, `communication_loss` at 140, `resource_cascade` at 160).
Before Phase 4 was frozen, the frontend contract exposed every phase name
(`bootstrap.scenario.phases`) and the next phase (`snapshot.phase.next_phase`): at tick 100 the
snapshot announced `environmental_emergency` before the unforeseeable solar particle event
(tick 122), and Future Lens `projected_phase` named `communication_loss` before the relay outage.
That leaked future mission information even though Future Lens correctly hid the events
themselves.

**Resolution (Phase 4): RESOLVED by a general phase visibility rule in the frontend-safe
projection layer** (`app/read_models/visibility.py`; [API_CONTRACT.md](API_CONTRACT.md#phase-visibility)).
The simulation, the scenario, its hash, the hidden event schedule and the phase engine are
unchanged. The rule is computed from the scenario's phase schedule and event foreseeability,
never from names, so it applies to any future scenario:

* The **current** phase, phases already **entered** and `conclusion`/`analysis` phases are always
  visible.
* A **future** simulated phase is announced only if (1) its start is on the clock (a chain of
  `time.tick` conditions from the first phase), (2) a planned milestone — a foreseeable
  scheduled event — lies in its window, and (3) no unforeseeable event can only fire inside its
  window. Otherwise it is **withheld until entered**: `next_phase: null` with
  `next_phase_withheld: true`, `{"id": null, "withheld": true}` in the bootstrap phase list,
  `projected_phase: null` with `projected_phase_withheld: true` in known-only Future Lens, and
  omitted from the session-independent phase lists of the provisional session and mission views.
* Condition (2) is positive on purpose: if withholding were decided only by the presence of an
  unforeseeable event, a `null` would itself announce "something hidden happens next". With (2),
  a chapter without a planned milestone is withheld whether or not anything unforeseeable happens
  in it (in LUNA-01 `power_management` is withheld for this reason), and a test checks that the
  same phases are withheld when the unforeseeable events are removed.

LUNA-01 v0.2.0 (and v0.1.0): `power_management`, `environmental_emergency`, `communication_loss`
and `resource_cascade` are withheld until entered; the other transitions are announced.

**Remaining by design.** A phase becomes visible when it becomes current: `environmental_emergency`
is the current phase from tick 120, two ticks before the solar particle event (tick 122), and the
`PHASE_CHANGED` event says so. Avoiding that would need a change to the scenario's phase schedule
or names (a new scenario version), which is out of scope for the frozen v0.2.0; it is a content
choice for a later scenario version, not a contract leak.

**Implementation status.** Resolved; tested in `tests/test_phase_visibility.py` (rule,
independence from hidden events and from names, every frontend-safe REST response and realtime
frame scanned for not-yet-known names, Future Lens engine output unchanged).
