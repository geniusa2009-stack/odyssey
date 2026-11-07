#!/usr/bin/env bash
# One command for the first real Unreal compile on a Mac:
#   1 environment check → 2 native tests (baseline) → 3 project generation → 4 OdysseyEditor build
#   → 5 failure report if the build fails.
# Stops at the first failing step with the reason. Exit code: 0 success, otherwise the failing
# step's code (the Unreal Build Tool exit code when the compile fails).
#
#   bash Tools/Mac/first_compile.sh
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck source=Tools/Mac/lib.sh
. "$HERE/lib.sh"

LOGS="$(ody_log_dir)" || exit 1
SUMMARY="$LOGS/first-compile-summary.txt"
: >"$SUMMARY"
note() { printf '%s\n' "$1" | tee -a "$SUMMARY"; }
step() { printf '\n==== %s\n' "$1"; printf '%s ... ' "$1" >>"$SUMMARY"; }

note "ODYSSEY first compile — $(date '+%Y-%m-%d %H:%M:%S') — $ODYSSEY_ROOT"

step "1/5 environment"
if ! bash "$HERE/verify_environment.sh"; then
	note "FAILED"
	if ! ody_find_ue >/dev/null; then
		echo
		ody_explain_missing_ue
	fi
	note "Stopped: a required item is missing (see the FAIL lines above; also in $LOGS/environment.txt). Nothing was built."
	exit 1
fi
note "ok"

step "2/5 native tests"
if ! bash "$HERE/run_native_tests.sh"; then
	note "FAILED"
	note "Stopped before Unreal: the native protocol baseline does not pass on this Mac (log: $LOGS/native-tests-latest.log)."
	exit 1
fi
note "ok"

step "3/5 generate project files"
bash "$HERE/generate_project.sh"
GEN_STATUS=$?
if [ "$GEN_STATUS" -ne 0 ]; then
	note "FAILED (exit $GEN_STATUS)"
	REPORT="$(bash "$HERE/collect_failure_report.sh" "$LOGS/generate-latest.log" "$GEN_STATUS")" &&
		note "Report: $REPORT — send this file back."
	exit "$GEN_STATUS"
fi
note "ok"

step "4/5 build OdysseyEditor (Mac, Development, arm64)"
bash "$HERE/build_editor.sh"
BUILD_STATUS=$?
if [ "$BUILD_STATUS" -eq 0 ]; then
	note "ok"
	step "5/5 failure report"
	note "not needed"
	note ""
	note "OdysseyEditor compiled. Next: open Odyssey.uproject and continue with Docs/VERIFICATION_CHECKLIST.md step 5."
	exit 0
fi
note "FAILED (Unreal Build Tool exit $BUILD_STATUS)"

step "5/5 failure report"
if REPORT="$(bash "$HERE/collect_failure_report.sh" "$LOGS/build-editor-latest.log" "$BUILD_STATUS")"; then
	note "written"
	note ""
	note "Build failed. Send back this one file: $REPORT"
else
	note "FAILED to write — send $LOGS/build-editor-latest.log instead"
fi
exit "$BUILD_STATUS"
