#!/usr/bin/env bash
# Builds the OdysseyEditor target (Mac, Development, arm64) with Unreal Build Tool.
# Nothing is filtered: the full stdout+stderr is shown and saved to Logs/build-editor-<timestamp>.log
# (and copied to Logs/build-editor-latest.log). UBT's own Log.txt is copied next to it.
# Returns Unreal Build Tool's real exit code. Extra arguments are passed to Build.sh.
#
#   bash Tools/Mac/build_editor.sh [extra UBT args]
set -o pipefail
# shellcheck source=Tools/Mac/lib.sh
. "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

if ! UE="$(ody_find_ue)"; then
	ody_explain_missing_ue
	exit 2
fi
LOGS="$(ody_log_dir)" || exit 1
TS="$(ody_timestamp)"
LOG="$LOGS/build-editor-$TS.log"
BUILD="$UE/Engine/Build/BatchFiles/Mac/Build.sh"

echo "Building OdysseyEditor Mac Development (arm64)"
echo "  engine:  $UE"
echo "  project: $ODYSSEY_PROJECT"
echo "  log:     $LOG"
{
	echo "# build_editor.sh $(date '+%Y-%m-%d %H:%M:%S')"
	echo "# $BUILD OdysseyEditor Mac Development -Project=$ODYSSEY_PROJECT -architecture=arm64 -WaitMutex $*"
} >"$LOG"
START=$(date +%s)
"$BUILD" OdysseyEditor Mac Development -Project="$ODYSSEY_PROJECT" -architecture=arm64 -WaitMutex "$@" 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}
ELAPSED=$(( $(date +%s) - START ))
echo "# exit code $STATUS after ${ELAPSED}s" >>"$LOG"

cp "$LOG" "$LOGS/build-editor-latest.log"
printf '%s\n' "$STATUS" >"$LOGS/build-editor-latest.exitcode"
UBT_LOG="$HOME/Library/Application Support/Epic/UnrealBuildTool/Log.txt"
if [ -f "$UBT_LOG" ]; then
	cp "$UBT_LOG" "$LOGS/ubt-$TS.txt"
fi

if [ "$STATUS" -eq 0 ]; then
	echo "OdysseyEditor build SUCCEEDED in ${ELAPSED}s."
else
	echo "OdysseyEditor build FAILED with exit code $STATUS after ${ELAPSED}s. Full log: $LOG" >&2
	echo "Summarise it with: bash Tools/Mac/collect_failure_report.sh" >&2
fi
exit "$STATUS"
