#!/usr/bin/env bash
# Runs the engine-independent protocol tests (no Unreal needed) and checks the known baseline
# before any Unreal compile is attempted. Also checks the vendored backend fixtures are intact.
# The result is parsed from the real test output; exit 0 only if every case passed and the case
# count equals the baseline (override: ODYSSEY_NATIVE_BASELINE=<n>).
#
#   bash Tools/Mac/run_native_tests.sh
set -o pipefail
# shellcheck source=Tools/Mac/lib.sh
. "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

BASELINE="${ODYSSEY_NATIVE_BASELINE:-26}"
LOGS="$(ody_log_dir)" || exit 1
LOG="$LOGS/native-tests-$(ody_timestamp).log"
echo "Native protocol tests (baseline ${BASELINE}/${BASELINE}); log: $LOG"

make -C "$ODYSSEY_ROOT/Tools/ProtocolCore" test 2>&1 | tee "$LOG"
MAKE_STATUS=${PIPESTATUS[0]}
RESULT="$(grep -E '^[0-9]+/[0-9]+ cases passed' "$LOG" | tail -n 1)"
PASSED="$(printf '%s' "$RESULT" | sed -E 's#^([0-9]+)/([0-9]+).*#\1#')"
TOTAL="$(printf '%s' "$RESULT" | sed -E 's#^([0-9]+)/([0-9]+).*#\2#')"

python3 "$ODYSSEY_ROOT/Tools/Contract/sync_fixtures.py" --check 2>&1 | tee -a "$LOG"
FIXTURE_STATUS=${PIPESTATUS[0]}
cp "$LOG" "$LOGS/native-tests-latest.log"

if [ -z "$RESULT" ]; then
	echo "NATIVE TESTS FAILED: no result line (make exit $MAKE_STATUS) — the test runner did not build or run." >&2
	exit 1
fi
if [ "$MAKE_STATUS" -ne 0 ] || [ "$PASSED" != "$TOTAL" ]; then
	echo "NATIVE TESTS FAILED: $RESULT (make exit $MAKE_STATUS)." >&2
	exit 1
fi
if [ "$TOTAL" != "$BASELINE" ]; then
	echo "NATIVE TESTS: $RESULT, but the known baseline is ${BASELINE}/${BASELINE} — the test set changed; update ODYSSEY_NATIVE_BASELINE only if that is intended." >&2
	exit 1
fi
if [ "$FIXTURE_STATUS" -ne 0 ]; then
	echo "NATIVE TESTS: $RESULT, but the vendored backend fixtures failed their integrity check." >&2
	exit 1
fi
echo "Native baseline OK: $RESULT; fixtures intact."
