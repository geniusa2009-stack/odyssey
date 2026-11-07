# Future Lens

"What happens if I do this?" Future Lens projects one or more candidate decisions forward on
**isolated copies** of the mission and compares them with a no-change baseline. It never
touches the real mission. Tests compare the real state's full JSON and hash before and after
every prediction, including property-based tests over arbitrary horizons and sample counts.
Predictions are not written to the ledger.

Implementation: `app/simulation/analysis/future_lens.py`. Endpoint:
`POST /mission-sessions/{id}/future-lens`.

## Request

| Field | Default | Meaning |
|---|---|---|
| `candidates` | (required, 1–4) | `{label, decisions: [up to 8 decisions applied now]}` |
| `include_baseline` | `true` | Also project "no change" |
| `horizon_ticks` | 24 | 1–240; clipped at the mission end (stated in `assumptions`) |
| `samples` | 4 | 1–16 independent random-fault samples |
| `knowledge_policy` | `known_only` | See below |
| `explain` | `true` | Attach root-cause traces for predicted warnings |

## Per-branch output

* `valid` / `rejection`: an invalid candidate (e.g. maintenance on a missing component) is
  reported, not raised, and other branches still run.
* `metrics`: for 11 key metrics (12 when the scenario declares a dose limit:
  `crew.projected_dose_margin_msv`): `start`, `end` (median across samples), `end_min`,
  `end_max`, `delta`, `worst` and `worst_tick` (in the metric's "bad" direction).
* `warnings`: alerts newly raised during the projection, first tick, and the fraction of samples
  in which they occur.
* `risk`: `end_risk` (median), `peak_risk`, `peak_risk_tick`, `critical_warning_fraction`.
* `vs_baseline`: end-value differences against the baseline.
* `confidence`: see below.
* `assumptions`: plain statements (no further decisions; horizon; sampling; model
  simplification; hidden events).
* `causal_explanation`: root-cause traces for predicted warnings: first every warning the
  candidate **introduces** (up to 5), then the earliest others (up to 3). The candidate decisions
  appear as `decision:lens:<label>:<i>` nodes, so the lens explains *why*. Only warnings that
  actually occur in the traced sample are explained, so every explanation is grounded in a
  recorded projection.
* `new_warnings` (Phase 3): alerts this candidate raises that the baseline does not, or raises
  earlier.
* `objective_outlook` (Phase 3): for every objective, its pillar, status now, projected status at
  the end of the horizon (sample 0) and the share of samples in which it ends FAILED / ACHIEVED.
  Shows a mission-level consequence (e.g. "life-support stability projected to fail") without
  revealing hidden events.
* `projected_outcome`, `projected_phase`, `concludes`, `ticks_projected`.

The result also carries `base_state_hash` (which state was projected) and `request_hash`
(state + request) for caching and auditing.

## Honesty: what the lens may know

* **`known_only` (default).** Scenario events marked `foreseeable: false` (LUNA-01: random
  flares, the solar particle event, the relay outage, the pump fault) that have not fired yet
  are **suppressed**, and random faults use seeds *derived* from the mission seed. The lens
  cannot leak the real mission's future surprises. Its predictions are what a mission
  planner with good models but no crystal ball would see. `excluded_events` lists what was
  hidden.
* **`omniscient`.** Nothing is suppressed and sample 0 uses the real seed, so it reproduces the
  actual future exactly (tested). Intended for teachers and debugging. Since Phase 4 it is
  refused (`403 PERMISSION_DENIED`, `omniscient_disabled`) on every Future Lens endpoint unless
  `ODYSSEY_FUTURE_LENS_OMNISCIENT_ENABLED=true`; restricting it to a teacher role is an open
  decision ([D6](USER_DECISIONS_REQUIRED.md#d6-future-lens-honesty-and-confidence)).

**Frontend view (Phase 4).** Clients use `POST .../future-lens/projections`, which returns a
projection of this result ([API_CONTRACT.md](API_CONTRACT.md#future-lens)). In `known_only` mode
it drops two indirect hints the raw result contains: `excluded_events` / the assumption line
naming the hidden events that were excluded, and the knowledge factor of the confidence score,
which in the raw result is lower only while hidden events remain within the horizon. The view
uses the excluded-case factor (0.85) always. The raw result stays available on the internal
endpoint for tooling. The simulation behaviour of the lens is unchanged.

## Confidence (provisional formula)

```
score = model_factor · horizon_factor · spread_factor · knowledge_factor
model_factor     = 0.8                    (simplified educational model)
horizon_factor   = 1 / (1 + horizon/72)   (further = less certain)
spread_factor    = 1 − (max − min of end risk across samples)
knowledge_factor = 0.85 if unforeseeable events were hidden, else 1.0
level            = high ≥ 0.6 > medium ≥ 0.35 > low
```

Every confidence object is flagged `provisional: true`.

## Measured quality (Phase 2)

Measured with `python -m app.simulation.analysis.balancing quality`. Full numbers are in
[BALANCING_FINDINGS.md](BALANCING_FINDINGS.md#future-lens-quality).

* Deterministic and isolated in every measured case.
* Confidence falls with horizon as designed. The sample-spread term is almost always 1, because
  random faults rarely change a 24–48 h projection, so in practice confidence ≈ horizon ×
  constants.
* About a third of single-decision candidates are indistinguishable from the baseline over
  24 h (heater eco: always; charger off: mostly).
* Phase 2 limitation (fixed in Phase 3): explanations covered the first three predicted
  warnings *by time*, which were often warnings the baseline also had, so a warning introduced
  by the candidate could go unexplained (6 of 27 cases). Explanations now trace introduced
  warnings first.
* Phase 2: `risk.mission` had no radiation term. LUNA-01 v0.2.0 adds the projected dose margin
  ([D22](USER_DECISIONS_REQUIRED.md#d22-what-the-mission-risk-index-includes)).

## Measured quality (Phase 3, LUNA-01 v0.2.0)

Full numbers: [PHASE3_BALANCE_REPORT.md](PHASE3_BALANCE_REPORT.md#future-lens).

* Still deterministic, isolated and blind to unforeseeable events (`known_only`): the honesty
  rules did not change.
* "Indistinguishable from the baseline" is now measured two ways: end-of-horizon resources only
  (the Phase 2 measure, kept for comparison) and **any signal the lens returns** (end values,
  worst values inside the horizon, new warnings, objective outlook). Major choices (as
  classified in [DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md)) are expected to differ;
  minor ones may correctly look like doing nothing over 24 h. Differences are reported, never
  amplified.

## Determinism and cost

Same state + same request → byte-identical result (tested across fresh engine instances).
Cost is `(branches) × samples × horizon` ticks. Measured: 5 branches × 4 samples × 48 ticks
≈ 0.5 s, run in a worker thread so the API stays responsive. The endpoint uses the
"expensive" rate-limit bucket.
