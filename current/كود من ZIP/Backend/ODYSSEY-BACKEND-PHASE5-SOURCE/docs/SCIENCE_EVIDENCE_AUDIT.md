# Science Evidence Audit

Audit date: 2026-10-07. Scope: every entry in `app/science/data/evidence.yaml`, every NASA
data source record (`app/nasa/providers.py`), and every scientific constant in
`app/simulation/scenarios/data/luna-01.yaml` that influences the simulation.

**Method.** For each cited source I fetched the page during this audit and compared the
quoted value with the registry. A source that could not be fetched is marked *not re-checked*.
I did not add, replace or upgrade any evidence. Discrepancies are reported, not corrected.
Final dataset selection remains an open decision
([D10](USER_DECISIONS_REQUIRED.md#d10-final-nasa-datasets)).

## Classification

| Class | Meaning |
|---|---|
| **VERIFIED** | Value checked in this audit against the cited source (primary or secondary), or derived from first principles with the arithmetic re-done |
| **UNVERIFIED** | No source confirmed, or the cited source could not be checked in this audit |
| **FIXTURE_ONLY** | Data that exists only as a local fixture: either synthetic, or real values quoted into a fixture with no live retrieval |
| **PROVISIONAL** | A gameplay or engineering placeholder with no evidence claim. It is a balancing decision, not science ([D1](USER_DECISIONS_REQUIRED.md#d1-scenario-balancing)) |

## 1. Evidence registry (11 entries)

| Evidence id | Value | Registry status | Audit class | What was checked | Issue found |
|---|---|---|---|---|---|
| `bvad_o2_consumption` | 0.818 kg/CM-d | verified_secondary | **VERIFIED** (secondary) | [Ichimura & Yamashiki, *Frontiers in Space Technologies*](https://www.frontiersin.org/journals/space-technologies/articles/10.3389/frspt.2024.1461389/full) lists "0.818 kg/CM-d (Anderson et al., 2018)" | Registry notes call it a 2024 article; the page is dated 15 Jan 2025. Primary BVAD (NTRS) link still missing |
| `bvad_co2_production` | 1.04 kg/CM-d | verified_secondary | **VERIFIED** (secondary) | Same article: "1.040 kg/CM-d (Anderson et al., 2018)" | Same as above |
| `bvad_water_total` | 4.35 kg/CM-d | verified_secondary | **VERIFIED** (secondary) | Same article: "4.350 kg/CM-d", drinking "2.000 kg/CM-d" (Anderson et al., 2018) | Same as above |
| `bvad_food_mass` | 1.51 kg/CM-d | verified_secondary | **VERIFIED** (value, secondary) | Same article lists 1.510 kg/CM-d for food consumed without packaging | **Attribution mismatch:** the article attributes 1.510 to a 2014 study, not to Anderson et al. 2018 (BVAD) as the registry states |
| `iss_water_recovery` | 0.93 | verified_secondary | **VERIFIED** (secondary) | [Space.com, 25 Jun 2023](https://space.com/astronaut-pee-iss-water-recycling-98-percent-milestone) quotes NASA's ECLSS water subsystems manager: "Before the BPA, our total water recovery was between 93 and 94%" | Popular-press secondary source; a NASA primary (NTRS/ICES paper) would be stronger |
| `change4_lnd_dose_rate` | 0.057 mSv/h | verified_secondary | **VERIFIED** (secondary) | [Sci.News, 28 Sep 2020](https://www.sci.news/space/radiation-dose-rates-lunar-surface-08893.html): "average dose equivalent of 1,369 μSv/day", citing Zhang et al. 2020, *Science Advances* 6(39) eaaz1334. 1369/24 = 57.0 µSv/h | Primary DOI not re-checked (fetch not permitted in this audit). Non-NASA instrument (stated in the registry) |
| `diviner_surface_temperature` | ~400 K / <100 K / ~25 K | verified_primary | **VERIFIED** (primary) | [UCLA Diviner science page](https://www.diviner.ucla.edu/science): "almost 400K … at noon", "below 100K … during the night", "as low as 25K" | None for the claim. Its *use* (sink-temperature keyframes) is an abstraction, see §3 |
| `electrolysis_stoichiometry` | 1.125 kg H₂O/kg O₂ | verified_primary | **VERIFIED** (first principles) | 2 H₂O → 2 H₂ + O₂: 2 × 18.015 / 31.998 = 1.126 | None (1.125 is the rounded value) |
| `donki_sep_events` | (existence of a catalogue) | verified_secondary | **UNVERIFIED** (not re-checked) | api.nasa.gov could not be fetched in this audit | Supports only that an SEP catalogue exists; LUNA-01's SEP timing and ×40 magnitude are scripted (PROVISIONAL, §3) |
| `lunar_polar_illumination` | — | unverified | **UNVERIFIED** | No source cited; registry names LOLA studies as a *candidate* | The core "last light" mechanic rests on this |
| `co2_crew_limits` | — | unverified | **UNVERIFIED** | No source cited; candidate NASA SMAC / ISS flight rules | Thresholds 5300 / 10500 ppm drive health penalties and alerts |

## 2. NASA data source records (3)

| Source id | Audit class | Notes |
|---|---|---|
| `lro_diviner_summary` | **FIXTURE_ONLY** (real values) | Real published summary values quoted into the fixture provider; no live retrieval. Values match the Diviner page (§1) |
| `change4_lnd` | **FIXTURE_ONLY** (real values) | Real published value in a fixture; non-NASA mission |
| `donki_sep_sample` | **FIXTURE_ONLY** (synthetic) | Invented placeholder events in DONKI's response shape, flagged `is_real_data: false`. The live DONKI adapter exists but is off by default and was not called in this audit |

## 3. Scientific constants that influence the simulation

Each constant below changes outcomes. "Adequate?" asks whether the provenance is good enough
for an educational simulation that claims to be NASA-grounded.

| Scenario path | Value | Evidence | Audit class | Adequate? |
|---|---|---|---|---|
| `life_support.o2_consumption_kg_per_crew_day` | 0.818 | `bvad_o2_consumption` | VERIFIED | Yes, add BVAD primary link |
| `life_support.co2_production_kg_per_crew_day` | 1.04 | `bvad_co2_production` | VERIFIED | Yes, add BVAD primary link |
| `life_support.water_use_kg_per_crew_day` | 4.35 | `bvad_water_total` | VERIFIED | Yes, add BVAD primary link |
| `food.consumption_kg_per_crew_day` | 1.51 | `bvad_food_mass` | VERIFIED (value) | **Partly**: fix the attribution |
| `life_support.water_per_kg_o2` | 1.125 | `electrolysis_stoichiometry` | VERIFIED | Yes |
| `life_support.water_recovery_nominal` | 0.93 | `iss_water_recovery` | VERIFIED | Yes for a hackathon; prefer a NASA primary |
| `environment.radiation_dose_rate_msv_h` (baseline) | 0.057 | `change4_lnd_dose_rate` | VERIFIED | Yes, with the non-NASA caveat already recorded |
| `life_support.co2_ppm_per_kg` | 5500 | none (YAML comment: 100 m³ cabin, ideal gas) | PROVISIONAL (derivation re-done: 1 kg CO₂ = 22.72 mol × 0.02422 m³/mol = 0.550 m³ in 100 m³ = 5503 ppm) | Arithmetic is right; the **100 m³ cabin volume is an assumption** |
| `crew_health.co2_warning_ppm` / `co2_critical_ppm` | 5300 / 10500 | `co2_crew_limits` | UNVERIFIED | **No** |
| `environment.solar_availability` keyframes | 0.85 → 0 over ticks 40–210 | `lunar_polar_illumination` | UNVERIFIED | **No**, and it is the scenario's central mechanic |
| `environment.sink_temp_c` keyframes | −45 → −185 °C | `diviner_surface_temperature` (context only) | PROVISIONAL (informed by verified extremes) | Acceptable if presented as an abstraction |
| `events.solar_particle_event` (tick 122, ×40, 8 h) | | `donki_sep_events` (existence only) | PROVISIONAL | Magnitude/timing are gameplay values |
| `events.minor_flare` (×5, 3 h, p = 0.003/tick) | | none | PROVISIONAL | Gameplay value |
| `radiation.*_shielding_factor` | 0.6 / 0.15 / 1.0 | none | PROVISIONAL | Gameplay value |
| `radiation.health_threshold_msv_per_hour`, `health_penalty_per_msv` | 0.5, 0.02 | none | PROVISIONAL | Acute-harm abstraction, **not** physiology |
| `objectives.radiation_safety` limit | 15 mSv | none | PROVISIONAL | Gameplay threshold; no regulatory limit is claimed |
| `crew_health.*` penalties and cold threshold (15 °C) | | none | PROVISIONAL | Abstract health index |
| `life_support.o2_generation_capacity_kg_per_hour`, `co2_removal_capacity_kg_per_hour` | 0.16, 0.22 | none | PROVISIONAL | Engineering placeholders sized above 4-crew demand (0.136 kg O₂/h, 0.173 kg CO₂/h) |
| `power.*` (array 15 kW, battery 160 kWh, loads, efficiencies 0.95, dust rate) | | none | PROVISIONAL | Engineering placeholders |
| `thermal.*` (UA, capacitance, internal heat fraction) | | none | PROVISIONAL | Engineering placeholders |
| `rover.*`, `science.*`, `degradation.*` | | none | PROVISIONAL | Gameplay values |

## 4. Summary

* Evidence entries: **8 VERIFIED** (1 primary, 1 first-principles, 6 secondary),
  **3 UNVERIFIED** (2 never sourced, 1 not re-checkable in this audit).
* NASA source records: **3 FIXTURE_ONLY** (2 real values, 1 synthetic).
* Of the constants with an evidence claim, the life-support mass balance is well grounded.
  The two weakest links are the ones that matter most for LUNA-01's story: **polar solar
  availability** (the "last light") and the **CO₂ health thresholds**.
* Corrections the registry needs (not made here, by instruction): the publication date of the
  secondary BVAD source, and the attribution of the 1.51 kg/CM-d food value.

Recommended next steps are listed as decision
[D15](USER_DECISIONS_REQUIRED.md#d15-unverified-scientific-evidence).

## 5. Phase 3 addendum (LUNA-01 v0.2.0)

* No evidence entry and no EVIDENCE_LOCKED value changed. `tests/test_parameter_governance.py`
  asserts that every scenario value linked to a numeric evidence entry still equals it, and the
  balance search refuses those paths. Classification of every parameter:
  [PARAMETER_GOVERNANCE.md](PARAMETER_GOVERNANCE.md).
* One source was consulted to judge a health-model abstraction (not added to the registry):
  [WHO Housing and Health Guidelines (2018), chapter 4](https://www.ncbi.nlm.nih.gov/books/NBK535294/),
  checked on 2026-10-12: "18 °C has been proposed as a safe and well-balanced indoor
  temperature"; blood-pressure risk higher below 16 °C (OR 4.92); "current evidence is
  insufficient to establish the precise temperature below which adverse health effects are
  likely to occur". It supports the existing 15 °C cold threshold and the reduction of the cold
  penalty rate (cold homes harm health; they do not kill within days). The penalty rate itself
  remains an EDUCATIONAL_ABSTRACTION, not a physiological value.
