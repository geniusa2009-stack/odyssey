#!/usr/bin/env bash
# Generates the Xcode project files for Odyssey.uproject with Unreal Engine 5.8.
# Engine location: $UE_ROOT, else auto-detected (lib.sh). Log: Logs/generate-<timestamp>.log.
# Returns GenerateProjectFiles.sh's real exit code.
#
#   bash Tools/Mac/generate_project.sh
set -o pipefail
# shellcheck source=Tools/Mac/lib.sh
. "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

if ! UE="$(ody_find_ue)"; then
	ody_explain_missing_ue
	exit 2
fi
LOGS="$(ody_log_dir)" || exit 1
LOG="$LOGS/generate-$(ody_timestamp).log"
GEN="$UE/Engine/Build/BatchFiles/Mac/GenerateProjectFiles.sh"
if [ ! -f "$GEN" ]; then
	echo "missing $GEN" >&2
	exit 2
fi

echo "Generating project files"
echo "  engine:  $UE"
echo "  project: $ODYSSEY_PROJECT"
echo "  log:     $LOG"
{
	echo "# generate_project.sh $(date '+%Y-%m-%d %H:%M:%S')"
	echo "# $GEN -project=$ODYSSEY_PROJECT -game"
} >"$LOG"
bash "$GEN" -project="$ODYSSEY_PROJECT" -game 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}
echo "# exit code $STATUS" >>"$LOG"
cp "$LOG" "$LOGS/generate-latest.log"
if [ "$STATUS" -eq 0 ]; then
	echo "Project files generated (exit 0)."
else
	echo "Project generation FAILED (exit $STATUS). Full log: $LOG" >&2
fi
exit "$STATUS"
