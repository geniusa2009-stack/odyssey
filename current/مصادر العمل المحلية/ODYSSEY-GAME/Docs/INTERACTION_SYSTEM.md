# Interaction system

> UNREAL_EDITOR_VERIFICATION_REQUIRED for every class on this page.

```
physical object ── UOdysseyInteractableComponent ── FOdysseySemanticIntent ── UOdysseyBackendSubsystem
       ▲                                                                               │
       └──── presentation (lights, panel, HUD prompt) ◀── mirror view ◀── authoritative result / events
```

## Components

| Class | Role |
|---|---|
| `UOdysseyInteractorComponent` (player) | every 0.1 s picks the interactable in range, inside a 35° view cone, with line of sight; focuses it. Local only. |
| `UOdysseyInteractableComponent` | target id (or the owner's binding), presented actions, local requirements (range, line of sight), prompt state, `RequestAction` |
| `AOdysseyPowerConsole` | a physical console with data-defined controls (map definition): Engineering power bus B (DIAGNOSTIC → `system.inspect`, BREAKER SERVICE → `repair.perform`); Training simulator and Laboratory sample analyzer (DIAGNOSTIC, LOAD OFF → `system.set_mode mode=off`, LOAD NOMINAL → `mode=nominal`) |
| `AOdysseySystemActor` | generic placeable system (battery, thermal plant, telescope, lockers, LUNA-01) |
| `UOdysseyObjectPresentationComponent` | the world's reaction: light groups (room ceiling lights, indicators, warning) whose intensity is `odyssey::presentation::Evaluate(rule, backend power/mode/status, incident)` — rules from the map definition (`room_load`, `equipment`, `bus_room`, `warning`); Blueprint hook for art |

## Who decides what

* **Legal actions and reasons:** the backend. The panel shows each control as offered/available/
  unavailable with the backend's safe reason (`fault_not_diagnosed`, `not_at_location`, …).
  `GetOfferedActions()` filters the backend's list; it never adds to it.
* **Whether an action happens:** the backend. A press is sent even if the mirror says unavailable
  (the mirror may be a moment old); the backend answers with a safe reason and the panel shows it.
* **What a press looks like:** Unreal (panel animation, sound, stance).

Prompt states: `Hidden`, `Available`, `Unavailable`, `Refreshing` (between `interactions.changed`
and the backend refresh), `Pending` (sent, awaiting the result), `Offline` (no ready session).

No "correct/wrong answer", "quiz" or "lesson complete" vocabulary exists anywhere in code or UI
text: only system states and their consequences.

## Input (Enhanced Input)

| Action | Default | Effect |
|---|---|---|
| IA_Move / IA_Look | WASD / mouse, sticks | movement and camera (held while a panel is engaged) |
| IA_Run | Shift / L3 | 190 → 430 cm/s |
| IA_Interact | E / A | engage the focused object; on an active panel press the selected control |
| IA_Cycle | Tab / D-pad | next control |
| IA_Back | Esc / B | release the panel |

Assets live in `/Game/Systems/Input/` and are created in the editor (see CONTENT_PIPELINE.md).

## Zones

`AOdysseySemanticZone` reports `world.zone_entered` after a 0.35 s dwell, once per entry, and only
when the backend's semantic location differs. Refusals (e.g. restricted access) come back as
`rejected` with the backend's reason; the player's physical position is never corrected by the
backend.

Parameterised actions (`system.set_mode` needs `mode`) are always performed through a console
control that carries the parameter; the generic interactable only sends parameterless actions.
A native test requires a physical control for every step of both incident strategies.

## Adding a new interactable

1. Place an `AOdysseySystemActor` (or a Blueprint child), pick its id in **Semantic Binding**.
2. Optionally list **Presented Actions** (empty = everything the backend offers).
3. Add lights/meshes; tune **Power/Status Intensity Scale** on the presentation component.
No code, no new strings: availability, legality and consequences already come from the backend.
