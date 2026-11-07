# Inventory, Cargo and Hardware Modules

Content: `content/data/catalog.yaml` and the `container` / `installed_modules` /
`vehicle_class` / `infrastructure_type` fields of world objects. Logic (pure, atomic):
`app/game/inventory/containers.py`, `modules.py`.

## Items

Stable id, category (`spare`, `tool`, `sample`, `consumable`, `cargo`, `module`, `equipment`),
mass (kg), volume (L), stack rules (`stackable`, `max_stack`), `unique`, tags (mission and
compatibility), provenance, and — for modules — a module spec. No coins, loot or rarity.
Condition lives in the world state (installed module state, component health in the engine).

## Containers and cargo manifests

A container is a world object with a `container` spec: mass limit, volume limit, accepted
categories and initial contents. Roles in the client view: `inventory` (the player kit),
`cargo` (a container whose parent is a vehicle, e.g. `earth.command.hangar.luna01.cargo_hold`)
or `storage`. Each view reports mass and volume against their limits.

A vehicle's **payload** is the mass of its cargo containers plus modules installed in payload
slots; it is checked against the vehicle class's `cargo_mass_limit_kg` on every transfer and
installation. Required cargo is expressed as authorization requirements (Earth Command needs two
water tanks and a habitat spares kit in the LUNA-01 hold); optional cargo is anything else that
fits. Adding shielding, science equipment, water or spares therefore has real mass consequences.

`cargo.transfer` / `inventory.move` (`item`, `quantity`, `from` → target container):

* validate everything first — both containers exist and are reachable (player at their location
  or the player kit; host vehicle not locked/restricted), category accepted, stack limit, unique
  items, container mass and volume limits, vehicle payload limit (a move inside one vehicle does
  not change its payload) — then mutate. A failed transfer leaves no partial state.
* invariants (property-based + fuzz tests, in memory and through the API): quantities are never
  negative or zero-but-present, **mass and units are conserved by every transfer**, unique items
  exist at most once per timeline, and an installed module is never also in a container.
* repeated transfers with one idempotency key apply once; racing transfers of the same unit on
  one state version: exactly one wins (SQLite and PostgreSQL race tests).

Cargo crosses missions only through explicit **carry rules** committed at completion (Earth
Command's LUNA-01 hold → the ASTERIA lander hold).

## Hardware modules

Module spec: `category` (power, storage, life support, science, communications, mobility,
radiation protection, cargo, robotics, ISRU), `mount`, optional `power_bus` / `data_bus`,
`environment_rating`, `mission_rating`, optional capability `qualification`, `provides`.

Hosts are vehicles (slots from the vehicle class: id, mount, buses, accepted categories,
`required_for_mission`, `payload`) and infrastructure (accepted categories from
`requires_modules`). `module.install` (`slot`, `item`, `from`) checks, and reports **every**
failed interface in `details.incompatible` (the first is the reason):

| Interface | Reason |
|---|---|
| slot accepts the module category | `module_category_incompatible` |
| same mount type | `mount_incompatible` |
| same power bus / data bus (when the module needs one) | `power_bus_incompatible`, `data_bus_incompatible` |
| module rated for every environment of the vehicle | `environment_rating_insufficient` |
| shares a mission rating | `mission_rating_mismatch` |
| payload slot within the vehicle mass budget | `vehicle_mass_limit_exceeded` |
| capability qualification reached | `module_qualification_missing` |
| slot free / slot exists | `slot_occupied`, `unknown_slot` |

A good component in an incompatible system is not a valid installation: the ISRU oxygen pilot
plant exists in the hangar and even fits LUNA-01's external payload slot mechanically (same
mount, power bus and data bus), but it is refused — it is not rated for cislunar transit, it is
rated for a different mission, and `isru.oxygen_extraction` has not reached `LAB_VALIDATED`.
Installation removes the item from its container and records it in the host slot in one step;
`module.remove` (`slot`, `to`) reverses it with the same container checks.

Module states: `stored`, `installed`, `operational`, `offline`, `damaged`,
`maintenance_required`; the client view derives `operational` for modules in working
infrastructure. Qualified/certified status comes from the capability stages.

## Vehicles (shipyard preparation)

`GET /vehicles/{id}` is the systems-level shipyard view: vehicle class and mission role, crew
capacity, environment/mission ratings, payload mass vs limit, power budget, life-support
crew-days, slots with what is installed, cargo containers, qualification requirements with
their status, `ready` and the exact `blockers` (`slot_empty:<slot>`, `payload_over_limit`,
`qualification_missing:<capability>`). No CAD, no orbital mechanics, no geometry: Unreal owns the
3D assembly visuals.

## Infrastructure

See [WORLD_SEMANTIC_STATE.md](WORLD_SEMANTIC_STATE.md#infrastructure) for states and
persistence.
