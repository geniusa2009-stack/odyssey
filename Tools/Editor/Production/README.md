# Engineering recovery sources — WORK IN PROGRESS

Engineering is not complete. No final screenshot set is accepted. The Mac was locked during the latest real-editor capture, preventing native recovery and validation.

The actual project already contains imported production assets and saved materials. Its main map was not explicitly saved over the original structural map. The live visual layer was also autosaved; the inspected 01:58 Cairo autosave is backed up in this archive.

This is an additive source/recovery package for the existing ODYSSEY project, not a standalone project or release build.

## Resume safely

1. Unlock the Mac manually. Do not disable lock/security controls.
2. Allow the pending capture to recover. If the editor is responsive, run Tools/Editor/Production/recover_interrupted_capture.py through Unreal's Python facility. It restores the authored warning intensity and clears the task's temporary capture camera/pilot state. It does not save the map.
3. If reopening is necessary, use Unreal's normal autosave recovery workflow. The backed-up Auto5 map may include a temporary camera and a preview warning intensity of zero; run the recovery script before gameplay validation or saving.
4. If reconstructing from the original structural map instead, load L_EarthCommand_Slice and run Tools/Editor/Production/build_visual_pass.py in Unreal. The structural/gameplay foundation must be validated first. The entry point recreates the visual layer without overwriting the map or claiming visual acceptance.
5. Inspect new actual Unreal overview, console front/back, ceiling and service renders. Continue refinement until the approved reference and quality criteria pass.
6. Run Tools/Editor/Production/start_gameplay_validation.py in the real editor with the development backend available. Preserve the Odyssey.Slice.Engineering result. This post-production run has not yet been performed.
7. End PIE, restore screen percentage as appropriate, profile the Mac, capture the accepted final views, then save/reopen the map and audit cooked dependencies.

## Reproduction and dependencies

Production sources are preserved in the project under Tools/Editor/Production, with source inputs under ArtSource/OdysseyProduction. These scripts use normal Unreal Python APIs; the temporary scratch queue is not required.

The original project, its compiled gameplay modules and the existing ArtSource/OdysseyAssetPack library/GLBs are prerequisites. No engine upgrade or new plugin installation is required by these sources.

Microfinish and UI/decal PNG inputs are included alongside editable SVGs. Sharp was used only to rasterize SVGs during authoring; it is not a runtime game dependency. Original supplied console GLB and audit are preserved, with a separate PNG-backed derivative for import.

The source scripts were syntax-checked, and the individual editor stages recorded in the evidence were executed. The newly assembled all-in-one rebuild/recovery entry points still require an end-to-end run in a responsive unlocked editor.

## Validation status

- Supported structural dry run: passed, 7 areas / 133 actors / 22 bindings.
- Pack GLB authoring checks: 15/15 passed.
- Native protocol suite: 26/26 cases, 959 checks passed using the documented project-root argument.
- Existing earlier Engineering integration run: success with one missing-development-save warning; preserved separately.
- Seven equipment imports, corrected console and 18 finish modules: editor import stages completed.
- Latest refined screenshot, new gameplay run, performance profile, save/reopen and final visual acceptance: pending.

See Tooling_Report.md for versions, licensing, source material corrections, runtime dependency notes and release cleanup.
