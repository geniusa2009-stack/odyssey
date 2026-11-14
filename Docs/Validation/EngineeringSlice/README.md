# Engineering slice — validation records (2026-11-13/14)

Copied from the working session's scratch folder so they survive outside /tmp.

- `COMPILE_FIXES.md` — every Unreal-side compile fix (pre-existing vs Engineering-slice), with exact errors.
- `ENGINEERING_VALIDATION_RUNBOOK.md` — commands used for build, map generation, screenshots, live test, regression gates.
  Paths in it point at the original session scratch folder (`$S`); substitute your own.
- `automation_report_Odyssey.Slice.Engineering.json` — UE automation report: `Odyssey.Slice.Engineering` Success (35.4 s).
- `slice_summary.txt` — readable summary of that run (zone entry, console intents, incident lighting, resolution).
- `engineering_assets_report.json` — proxy/kit mesh validation (bounds, collision, UVs) from map generation.
- `backend_snapshot_manifest.sha256` — sha256 manifest of the read-only backend snapshot (336 files), unchanged by this work.
- `editor_queue_tools/` — persistent-editor job queue used for captures and map generation.

Known results at backup time: native protocol 26/26 (959 checks), live harness 60/60, greybox dry run OK,
proxy geometry check PASSED. Visual production pass is NOT complete; generated room is the structural skeleton.
