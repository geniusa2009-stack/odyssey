# ODYSSEY Android Judge Build

Branch: `feature/android-judge-build`
Base: `feature/odyssey-space-experience` @ `e102d34a9e115ce8871162431c2314d53d67154e`

## Goal
Produce a sideloadable Android judge build without changing the desktop/PC experience.

## Non-negotiables
- Android changes must be platform-specific where possible.
- Preserve the existing desktop Lumen/Nanite/VSM configuration.
- Preserve startup flow: logo -> menu -> Earth Command / Solar Transit.
- ARM64.
- Prefer Vulkan; add GLES fallback only if it materially improves device coverage without breaking content.
- Add touch controls for movement, camera, interaction, menu and destination selection.
- Optimize Android texture residency and shader cost; do not globally downgrade source assets.
- Keep backend integration intact. If the real game backend is unreachable, the APK must fail gracefully and still provide a judge-safe offline/demo path using only already-validated project data.
- Do not commit secrets, signing passwords, local AndroidFileServer tokens, SDK paths, Saved, Intermediate, DerivedDataCache or generated Build junk.

## Current project facts
- UE 5.8 project.
- `Odyssey.uproject` currently lists only Mac and Windows target platforms.
- Default map: `/Game/Space/Maps/L_Odyssey_SolarTransit`.
- Desktop renderer uses Lumen software GI, reflections and Virtual Shadow Maps.
- Production backend host in `DefaultGame.ini` is still a reserved `.invalid` placeholder.

## Deliverables
1. First installable APK.
2. Exact APK size and SHA-256.
3. Tested device/model + Android version if a device is available.
4. Startup, menu, Solar Transit, Earth Command/exploration smoke results.
5. Touch control validation.
6. Measured FPS and memory on device if possible.
7. List of Android-only visual compromises.
8. Git commit(s) pushed to this branch.
9. A short install note for judges.
