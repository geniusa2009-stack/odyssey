# macOS Unreal 5.8 verification runner

**Where the project lives:** anywhere on the Mac's internal disk (e.g. `~/dev/ODYSSEY-GAME`), with
`Odyssey.uproject` at its root. Avoid iCloud-synced folders (Desktop/Documents with iCloud Drive on).
Unreal Engine 5.8 is found automatically (Epic Games Launcher install); otherwise set `UE_ROOT`.

**Run (one command, from the project folder):**

```bash
bash Tools/Mac/first_compile.sh
# engine somewhere unusual:
UE_ROOT="/path/to/UE_5.8" bash Tools/Mac/first_compile.sh
```

It checks the environment, runs the native protocol tests (baseline 26/26), generates the project
files, then builds `OdysseyEditor` (Mac, Development, arm64). It stops at the first failing step
and says why. Each step also runs alone: `verify_environment.sh`, `run_native_tests.sh`,
`generate_project.sh`, `build_editor.sh`, `collect_failure_report.sh`.

**Logs:** `Logs/` in the project folder (not committed) — `build-editor-latest.log` (full,
unfiltered UBT output), `environment.txt`, `native-tests-latest.log`, `generate-latest.log`,
`first-compile-summary.txt`, and a copy of UBT's own `Log.txt` (`ubt-<time>.txt`).

**If the build fails, send back one file:** `Logs/FAILURE_REPORT.txt`.
