# Capability and Certification

Progression is **demonstrated capability**, not XP. Content:
`content/data/progression.yaml`, `readiness.yaml`; logic: `app/game/progression/capabilities.py`;
read views: `GET /capabilities`, `/readiness/{profile}`, `/expansion-map`.

## Capability graph

Each capability has a stable id, name, description, domain (transportation, habitation, power,
life support, logistics, communications, autonomy, robotics, mobility, ISRU, science,
infrastructure), prerequisites (other capabilities at a stage), **its own configurable stage
ladder**, the evidence required per stage, a provenance classification, gameplay effects and
unlock consequences.

Example (`power.load_management`): `DISCOVERED` ← *a station power fault was diagnosed and
repaired*; `PROTOTYPE_TESTED` ← *critical loads stayed powered* **and** *the reserve never
reached its critical level*; `LUNAR_DEMONSTRATED` ← *outpost power managed through lunar night*;
`DEEP_SPACE_QUALIFIED` and `MARS_CERTIFIED` have no evidence yet (deferred content), so they
cannot be reached.

## Qualification pipeline

Stages: `DISCOVERED → LAB_VALIDATED → PROTOTYPE_TESTED → LUNAR_DEMONSTRATED →
DEEP_SPACE_QUALIFIED → MARS_CERTIFIED`. Not every capability uses every stage (the ladder is per
capability), and Mars certification is never hard-coded into unrelated technologies.
*Discovery is not engineering readiness*: an insight never advances a stage, and a discovery
at most contributes pending evidence that counts only when its mission completes — stages are
derived from committed evidence alone.

A stage is **derived**, never set:

* Evidence ids are produced in play as *pending* items on the timeline (mission completion
  evidence rules, e.g. "no `critical_load_lost` fact during the power incident").
* At mission completion the pending evidence is committed to the campaign once.
* `derive_stages` walks capabilities in prerequisite order: stage *k* is reached when the
  evidence of every stage up to *k* is committed **and** the capability's prerequisites are met.
  A locked capability keeps its evidence but gets no stage until its prerequisites are met
  (`locked capability cannot become certified without prerequisites` — tested).
* Committed evidence only grows, so stages are monotonic (fuzz-checked).

## Certifications

A certification requires capabilities at stages and is granted on completion of named missions:
`cert.earth_command.station_operations` (power load management ≥ DISCOVERED, on Earth Command)
and `cert.luna01.lunar_surface_operations` (load management and radiation sheltering ≥
LUNAR_DEMONSTRATED, on LUNA-01). Grants happen inside the completion transaction, at most once
(repeated commands, idempotent retries, rewinds and replays cannot duplicate them — tested).
Module qualification (`module.qualification`) and vehicle qualification use the same stage
checks (`module_qualification_missing`).

## Readiness gates and the Mars lock

A readiness profile is a list of explicit gates (category, critical flag, required capability
stages, optional certifications). `readiness()` returns gates met/total, the percentage, every
missing gate with the missing capability ids and current vs required stage, and `locked` with a
`lock_code`. **Any missing critical gate locks the profile regardless of the percentage.**
`MARS_01` is gated by `mars_01_human_mission`; starting it answers `DECISION_UNAVAILABLE`
`mars_mission_locked` with `details.lock_code = "MARS_MISSION_LOCKED"`, `missing_gates` and
`missing_capabilities`.

## Human Expansion Map

`GET /expansion-map` returns real nodes — phases, missions, capabilities (with their stage),
certifications, readiness gates, infrastructure types and discoveries — and edges that say
exactly which prerequisite links them (`requires`, `unlocks`, `qualifies`, `certifies`,
`gates`, `contains`), each with a one-line dependency `explanation` and whether it is
`satisfied`. Nodes carry their state, progress evidence, related mission/capability and NASA
evidence references where they exist. There are no meaningless percentages: the only percentage is a
readiness profile's `gates_met / gates_total`, always shown with the missing critical gates.

## Provenance

Every capability, certification, item, module, vehicle class, infrastructure type, discovery and
insight carries a provenance classification exposed to the client:
`verified_evidence` (with `evidence_refs` into the existing science evidence registry),
`educational_abstraction`, `gameplay_parameter`, `story_assumption` or `unverified`. Unreal must
not present an assumption as verified science; the classification is in every view.

## Knowledge (insights) and WHY?

Insights unlock when the player experiences something (an incident start, an alert such as
`load_shedding`, a metric crossing, an inspection, a discovery). Each has: what was observed,
the engineering concept, a short explanation, where it matters later, the simulation
simplification and provenance. No quizzes. `GET /insights/{id}/why` traces the insight's metric
through the engine's dependency graph with **current** values only (no forecasts, no hidden
events); unknown and not-yet-unlocked insights are indistinguishable (`insight_not_unlocked`).
Knowledge is campaign-global and survives rewinds (it carries no gameplay power — see
[SAVE_RESTORE.md](SAVE_RESTORE.md#timeline-ownership)).
