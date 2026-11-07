# NASA Data Options

**Status: no final dataset has been selected.** This is a product decision
([D10](USER_DECISIONS_REQUIRED.md#d10-final-nasa-datasets)). The backend ships the
architecture, offline fixtures and one optional live adapter so nothing depends on the choice.

## How data enters ODYSSEY

* The **engine never calls a provider.** Providers feed scenario authoring (numbers end up
  versioned in scenario YAML), the evidence registry and explanations. A NASA outage can
  therefore never break a mission.
* Interfaces (`app/nasa/providers.py`): `LunarEnvironmentProvider`,
  `SolarEnvironmentProvider`, `MarsEnvironmentProvider`, `MissionReferenceProvider`,
  `ScienceEvidenceProvider`.
* Every result is a `DataEnvelope` with a `NASADataSource`: source name, dataset/product, URL,
  retrieval timestamp, licence/provenance notes, variables used, transformation notes, origin
  (`fixture` / `remote` / `cache`) and `is_real_data` (false for synthetic placeholders).
* Fallback chain: **cache → live provider (if enabled) → local fixture**, flagged with
  `fallback_used` and a warning. Caches: in-memory, file (hashed names) or Redis.

## What is wired today

| Provider | Implementation | Data | Real? |
|---|---|---|---|
| Lunar temperatures | `FixtureLunarEnvironmentProvider` | LRO Diviner published summary values (~400 K equatorial noon, < 100 K night, ~25 K polar cold traps) | Real (quoted values) |
| Radiation baseline | same | Chang'E-4 LND 1369 µSv/day = 0.057 mSv/h (Zhang et al. 2020, *Science Advances*) | Real, **non-NASA** |
| Solar particle events | `DonkiSolarEnvironmentProvider` (live, opt-in) with `FixtureSolarEnvironmentProvider` fallback | NASA DONKI `/DONKI/SEP` | Live: real. Fixture: **synthetic, labelled** |
| Mission reference values | `EvidenceReferenceProvider` | Evidence registry (BVAD life-support values, ISS water recovery, stoichiometry) | Real (see verification status) |
| Mars | `UnavailableMarsProvider` | None selected | n/a |

Enable DONKI: `ODYSSEY_NASA_REMOTE_ENABLED=true` and a free key in `ODYSSEY_NASA_API_KEY`
(from api.nasa.gov). The key is never logged.

## Candidate datasets

Verify the access route and licence of each before final selection. Notes reflect public
information at the time of writing.

| Need in ODYSSEY | Candidate | What it gives | Integration effort | Notes |
|---|---|---|---|---|
| Polar solar availability (the "last light" curve) | **LRO LOLA** polar illumination / topography products (PDS) | Fraction of time sunlit at south-polar sites | Medium: precompute a profile for a chosen site offline → scenario keyframes | Strongest scientific anchor for LUNA-01's core mechanic. Replaces the `unverified` illumination evidence |
| Surface/sink temperatures | **LRO Diviner** (PDS Geosciences; Diviner team pages) | Gridded brightness/bolometric temperatures | Low (summary values) to medium (gridded extraction) | Already used as summary values |
| Space weather events | **DONKI** (CCMC via api.nasa.gov) | SEP, flare and CME catalogue | Done (SEP). FLR/CME are a small extension | Event timings could seed scenario variants based on real historical storms |
| Lunar radiation environment | **LRO CRaTER** (PDS) | Measured dose/LET spectra in lunar orbit | Medium | NASA alternative/complement to the Chang'E-4 surface value (orbital ≠ surface; needs a documented transformation) |
| Landing site context | **Artemis III candidate regions** (NASA announcements), **LROC** imagery, **Moon Trek** (JPL Solar System Treks) | Named south-polar regions, imagery, map layers | Low (metadata) | Useful for narrative grounding. Visuals are frontend scope |
| Life-support baselines | **NASA BVAD** (NTRS) | O₂/CO₂/water/food per crew-day | Low | Upgrade current secondary citations to the primary report |
| ECLSS performance | NASA ISS ECLSS publications (NTRS) | Water recovery, CO₂ removal performance | Low | Supports `iss_water_recovery` and scrubber parameters |
| Mars (future scenarios) | MSL REMS / MSL RAD (PDS); InSight weather archive | Surface weather and radiation | Medium | No Mars scenario exists. InSight is no longer operating, so archive only |

## Recommended default

For the Space Apps submission: **LOLA illumination (south pole) + Diviner + DONKI**, with
evidence citations upgraded to primary NASA reports. That covers LUNA-01's three core
mechanics (light, cold, radiation) with NASA sources. Keep Chang'E-4 LND as a cited, clearly
non-NASA surface value or replace it with a CRaTER-derived estimate.

## Attribution

Record attribution in `NASADataSource.license_notes` and the evidence registry. US-government
NASA data is generally not subject to copyright, but NASA asks for credit. Non-NASA results
(Chang'E-4) must be cited as publications. All of it is surfaced via `GET /nasa/sources` and
`GET /science/evidence` for the frontend's credits screen.
