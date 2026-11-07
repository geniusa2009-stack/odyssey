#!/usr/bin/env bash
# Single-quoted `bash -c '…' _ args` checks expand their positional parameters inside the child shell
# on purpose (SC2016 is the intended behaviour here).
# shellcheck disable=SC2016
# Tests for the macOS verification runner WITHOUT a Mac or Unreal: macOS commands (uname, sw_vers,
# sysctl, xcodebuild, xcode-select) are stubs on PATH, Unreal Engine 5.8 is a fake install whose
# Build.sh / GenerateProjectFiles.sh record their arguments and replay a failure log, HOME and the
# log directory are sandboxed. The native protocol tests run for real.
#
#   bash Tools/Mac/tests/test_toolkit.sh
set -o pipefail
TESTS="$(cd "$(dirname "$0")" && pwd -P)"
MAC="$(cd "$TESTS/.." && pwd -P)"
ROOT="$(cd "$MAC/../.." && pwd -P)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/odyssey-mac-tests.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

PASS=0
FAIL=0
check() {  # check "description" <command...>
	local what="$1"
	shift
	if "$@"; then
		PASS=$((PASS + 1))
		printf '  ok    %s\n' "$what"
	else
		FAIL=$((FAIL + 1))
		printf '  FAIL  %s\n' "$what"
	fi
}
has() { grep -qF -- "$2" "$1"; }   # has FILE TEXT
lacks() { ! grep -qF -- "$2" "$1"; }

# ---------------------------------------------------------------- sandbox
STUBS="$SANDBOX/bin"
mkdir -p "$STUBS" "$SANDBOX/home"
cat >"$STUBS/uname" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
	-s) echo "${FAKE_OS:-Darwin}" ;;
	-m) echo "${FAKE_ARCH:-arm64}" ;;
	*) echo "${FAKE_OS:-Darwin}" ;;
esac
EOF
cat >"$STUBS/sw_vers" <<'EOF'
#!/usr/bin/env bash
case "$1" in
	-productName) echo macOS ;;
	-productVersion) echo 15.1 ;;
	-buildVersion) echo 24B83 ;;
esac
EOF
cat >"$STUBS/sysctl" <<'EOF'
#!/usr/bin/env bash
case "$2" in
	hw.memsize) echo "${FAKE_MEM:-34359738368}" ;;
	sysctl.proc_translated) echo "${FAKE_TRANSLATED:-0}" ;;
	machdep.cpu.brand_string) echo "Apple M2" ;;
esac
EOF
cat >"$STUBS/xcodebuild" <<'EOF'
#!/usr/bin/env bash
[ -n "${FAKE_NO_XCODE:-}" ] && { echo "xcode-select: error: tool 'xcodebuild' requires Xcode" >&2; exit 1; }
printf 'Xcode 16.1\nBuild version 16B40\n'
EOF
cat >"$STUBS/xcode-select" <<'EOF'
#!/usr/bin/env bash
echo "${FAKE_DEVDIR:-/Applications/Xcode.app/Contents/Developer}"
EOF
chmod +x "$STUBS"/*

make_ue() {  # make_ue DIR MINOR
	local dir="$1" minor="$2"
	mkdir -p "$dir/Engine/Build/BatchFiles/Mac"
	printf '{\n\t"MajorVersion": 5,\n\t"MinorVersion": %s,\n\t"PatchVersion": 0\n}\n' "$minor" >"$dir/Engine/Build/Build.version"
	cat >"$dir/Engine/Build/BatchFiles/Mac/Build.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$FAKE_RECORD/build-args"
if [ -n "${FAKE_BUILD_LOG:-}" ]; then cat "$FAKE_BUILD_LOG"; fi
echo "stderr line from the compiler" >&2
mkdir -p "$HOME/Library/Application Support/Epic/UnrealBuildTool"
echo "ubt internal log" >"$HOME/Library/Application Support/Epic/UnrealBuildTool/Log.txt"
exit "${FAKE_BUILD_EXIT:-0}"
EOF
	cat >"$dir/Engine/Build/BatchFiles/Mac/GenerateProjectFiles.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$FAKE_RECORD/gen-args"
echo "Generating project files…"
exit "${FAKE_GEN_EXIT:-0}"
EOF
	chmod +x "$dir/Engine/Build/BatchFiles/Mac/"*.sh
}
UE58="$SANDBOX/engines/UE_5.8"
make_ue "$UE58" 8
make_ue "$SANDBOX/engines/UE_5.7" 7

export FAKE_RECORD="$SANDBOX/record"
mkdir -p "$FAKE_RECORD"
BASE_PATH="$STUBS:$PATH"
fresh() {  # clean per-test state
	rm -rf "${SANDBOX:?}/logs" "${FAKE_RECORD:?}"/* "${SANDBOX:?}/home"
	mkdir -p "$SANDBOX/home"
}
run() {  # run OUTFILE script [args] — sandboxed environment, returns the script's exit code
	local out="$1"
	shift
	env -u UE_ROOT PATH="$BASE_PATH" HOME="$SANDBOX/home" ODYSSEY_LOG_DIR="$SANDBOX/logs" \
		${T_UE_ROOT:+UE_ROOT="$T_UE_ROOT"} \
		bash "$@" >"$out" 2>&1
}
O="$SANDBOX/out.txt"

echo "verify_environment.sh"
fresh
T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "passes on a complete (stubbed) Mac" [ $? -eq 0 ]
check "reports macOS version" has "$O" "macOS 15.1 (24B83)"
check "reports Apple Silicon arm64" has "$O" "Apple M2, arm64 native"
check "reports RAM" has "$O" "32 GB"
check "reports Xcode version" has "$O" "Xcode 16.1 Build version 16B40"
check "reports developer directory" has "$O" "/Applications/Xcode.app/Contents/Developer"
check "reports the UE 5.8 path" has "$O" "5.8 at $UE58"
check "reports free disk space" grep -qE 'Disk space +[0-9]+ GB free' "$O"
check "reports git HEAD" has "$O" "$(git -C "$ROOT" rev-parse HEAD)"
check "reports git status" grep -qE 'git status' "$O"
check "writes Logs/environment.txt" has "$SANDBOX/logs/environment.txt" "RESULT: OK"

fresh
run "$O" "$MAC/verify_environment.sh"
check "fails when UE 5.8 is missing" [ $? -eq 1 ]
check "  …and says exactly what is missing" has "$O" "Unreal Engine 5.8 was not found."
check "  …and how to fix it (UE_ROOT)" has "$O" 'UE_ROOT="/path/to/UE_5.8"'

fresh
T_UE_ROOT="$SANDBOX/engines/UE_5.7" run "$O" "$MAC/verify_environment.sh"
check "rejects a UE 5.7 install given as UE_ROOT" [ $? -eq 1 ]
check "  …naming the wrong version" has "$O" "is version 5.7, not 5.8"

fresh
FAKE_TRANSLATED=1 T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "fails under Rosetta" [ $? -eq 1 ]
check "  …with the reason" has "$O" "runs under Rosetta"
fresh
FAKE_ARCH=x86_64 T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "fails on x86_64" [ $? -eq 1 ]
fresh
FAKE_DEVDIR=/Library/Developer/CommandLineTools T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "fails with only Command Line Tools selected" [ $? -eq 1 ]
check "  …and gives the xcode-select fix" has "$O" "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
fresh
FAKE_NO_XCODE=1 T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "fails without full Xcode" [ $? -eq 1 ]
fresh
FAKE_OS=Linux T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "fails on a non-Mac" [ $? -eq 1 ]
fresh
FAKE_MEM=8589934592 T_UE_ROOT="$UE58" run "$O" "$MAC/verify_environment.sh"
check "8 GB RAM is a warning, not a failure" [ $? -eq 0 ]
check "  …reported as WARN" grep -qE 'WARN +RAM +8 GB' "$O"

echo "engine discovery (no hardcoded machine path)"
fresh
mkdir -p "$SANDBOX/home/Library/Application Support/Epic/UnrealEngineLauncher"
printf '{\n\t"InstallationList": [\n\t\t{ "InstallLocation": "%s", "AppName": "UE_5.7" },\n\t\t{ "InstallLocation": "%s", "AppName": "UE_5.8" }\n\t]\n}\n' \
	"$(printf '%s' "$SANDBOX/engines/UE_5.7" | sed 's#/#\\/#g')" "$(printf '%s' "$UE58" | sed 's#/#\\/#g')" \
	>"$SANDBOX/home/Library/Application Support/Epic/UnrealEngineLauncher/LauncherInstalled.dat"
run "$O" "$MAC/verify_environment.sh"
check "finds UE 5.8 through the Epic Games Launcher manifest (escaped paths, 5.7 skipped)" has "$O" "5.8 at $UE58"
fresh
mkdir -p "$SANDBOX/home/Epic Games"
cp -R "$UE58" "$SANDBOX/home/Epic Games/UE_5.8"
run "$O" "$MAC/verify_environment.sh"
check "finds UE 5.8 under ~/Epic Games" has "$O" "5.8 at $SANDBOX/home/Epic Games/UE_5.8"

echo "generate_project.sh"
fresh
T_UE_ROOT="$UE58" run "$O" "$MAC/generate_project.sh"
check "exit 0 when generation succeeds" [ $? -eq 0 ]
check "passes the absolute project path" has "$FAKE_RECORD/gen-args" "-project=$ROOT/Odyssey.uproject"
check "passes -game" has "$FAKE_RECORD/gen-args" "-game"
check "saves the log" has "$SANDBOX/logs/generate-latest.log" "Generating project files"
fresh
FAKE_GEN_EXIT=3 T_UE_ROOT="$UE58" run "$O" "$MAC/generate_project.sh"
check "returns the real exit code (3)" [ $? -eq 3 ]
fresh
run "$O" "$MAC/generate_project.sh"
check "stops cleanly without UE (exit 2)" [ $? -eq 2 ]

echo "build_editor.sh"
fresh
FAKE_BUILD_EXIT=6 FAKE_BUILD_LOG="$TESTS/fixtures/ubt_failure.log" T_UE_ROOT="$UE58" run "$O" "$MAC/build_editor.sh"
check "returns UBT's real exit code (6)" [ $? -eq 6 ]
for a in OdysseyEditor Mac Development "-Project=$ROOT/Odyssey.uproject" -architecture=arm64 -WaitMutex; do
	check "UBT argument $a" grep -qxF -- "$a" "$FAKE_RECORD/build-args"
done
LATEST="$SANDBOX/logs/build-editor-latest.log"
check "full log saved under Logs/" [ -f "$LATEST" ]
check "log keeps stderr" has "$LATEST" "stderr line from the compiler"
check "log is unfiltered (every fixture line present)" bash -c 'while IFS= read -r l; do grep -qxF -- "$l" "$1" || exit 1; done <"$2"' _ "$LATEST" "$TESTS/fixtures/ubt_failure.log"
check "records the exit code" grep -qx 6 "$SANDBOX/logs/build-editor-latest.exitcode"
check "copies UBT's own Log.txt" bash -c 'ls "$1"/ubt-*.txt >/dev/null 2>&1' _ "$SANDBOX/logs"
check "timestamped log kept as well" bash -c 'ls "$1"/build-editor-2*.log >/dev/null 2>&1' _ "$SANDBOX/logs"
fresh
FAKE_BUILD_EXIT=0 T_UE_ROOT="$UE58" run "$O" "$MAC/build_editor.sh"
check "exit 0 on success" [ $? -eq 0 ]

echo "collect_failure_report.sh"
fresh
mkdir -p "$SANDBOX/logs"
echo "RESULT: OK — stub environment" >"$SANDBOX/logs/environment.txt"
run "$O" "$MAC/collect_failure_report.sh" "$TESTS/fixtures/ubt_failure.log" 6
check "writes the report" [ $? -eq 0 ]
R="$SANDBOX/logs/FAILURE_REPORT.txt"
check "UBT exit code" has "$R" "UBT exit code:  6"
check "UBT result line" has "$R" "Result: Failed (OtherCompilationError)"
check "first error is the UHT error (first in the log)" bash -c 'grep -A2 "^FIRST ERROR" "$1" | grep -q "\[uht\] module OdysseyDebug  Source/OdysseyDebug/Public/OdysseyDebugSubsystem.h:41"' _ "$R"
check "surrounding lines include the UHT invocation" has "$R" "Running Internal UnrealHeaderTool"
check "clang error: module, file, line" has "$R" "[compile] OdysseyRealtime | Source/OdysseyRealtime/Private/OdysseyEventRouter.cpp:118 (x2)"
check "duplicate errors are merged (x2)" has "$R" ":118 (x2)"
check "second clang error in the same file is separate" has "$R" "OdysseyEventRouter.cpp:157"
check "backend module error" has "$R" "OdysseyBackend | Source/OdysseyBackend/Private/OdysseyBackendSubsystem.cpp:301"
check "engine header error attributed to the engine module" has "$R" "Engine:Online"
check "Build.cs C# error with module and line" has "$R" "[buildcs] OdysseyWorld | Source/OdysseyWorld/OdysseyWorld.Build.cs:11"
check "fatal error (missing include)" has "$R" "'Debug/DebugDrawService.h' file not found"
check "linker error attributed via the Link action" has "$R" "[link] OdysseyInteraction"
check "undefined symbol named" has "$R" "UOdysseyInteractableComponent::GetSemanticIdOptions()"
check "warnings are counted, not listed" bash -c '! grep -q "unused variable" "$1" || grep -q "LAST 100 LOG LINES" "$1"' _ "$R"
check "Build.cs warning is not reported as an error" bash -c '! sed -n "/^ALL UNIQUE ERRORS/,/^LAST 100/p" "$1" | grep -q CS0618' _ "$R"
check "unique error count" grep -qE 'errors: [0-9]+ \(10 unique\)' "$R"
check "per-module summary" grep -q "^ERRORS PER MODULE: .*OdysseyRealtime 2" "$R"
check "last 100 lines section" has "$R" "LAST 100 LOG LINES"
check "environment section from Logs/environment.txt" has "$R" "RESULT: OK — stub environment"
check "report is concise (< 200 lines for this log)" [ "$(wc -l <"$R")" -lt 200 ]
printf 'Building OdysseyEditor...\nKilled: 9\n' >"$SANDBOX/odd.log"
run "$O" "$MAC/collect_failure_report.sh" "$SANDBOX/odd.log" 137
check "unrecognised failures still produce a report" has "$R" "No compiler/UHT/linker/UBT error line was recognised"
check "  …with the tail of the log" has "$R" "Killed: 9"
run "$O" "$MAC/collect_failure_report.sh" "$SANDBOX/missing.log"
check "missing log → clear error" [ $? -eq 1 ]

echo "run_native_tests.sh (real native tests)"
fresh
run "$O" "$MAC/run_native_tests.sh"
check "baseline passes (26/26)" [ $? -eq 0 ]
check "  …parsed from the real output" has "$O" "Native baseline OK: 26/26 cases passed"
check "  …fixtures intact" has "$O" "fixtures intact"
fresh
ODYSSEY_NATIVE_BASELINE=27 run "$O" "$MAC/run_native_tests.sh"
check "a different case count is reported, not accepted" [ $? -eq 1 ]
check "  …explaining the baseline" has "$O" "known baseline is 27/27"

echo "first_compile.sh"
fresh
FAKE_BUILD_EXIT=0 T_UE_ROOT="$UE58" run "$O" "$MAC/first_compile.sh"
check "success path exits 0" [ $? -eq 0 ]
check "  …ran all steps in order" bash -c 'grep -q "1/5 environment ... ok" "$1" && grep -q "2/5 native tests ... ok" "$1" && grep -q "3/5 generate project files ... ok" "$1" && grep -q "4/5 build OdysseyEditor (Mac, Development, arm64) ... ok" "$1"' _ "$SANDBOX/logs/first-compile-summary.txt"
fresh
FAKE_BUILD_EXIT=6 FAKE_BUILD_LOG="$TESTS/fixtures/ubt_failure.log" T_UE_ROOT="$UE58" run "$O" "$MAC/first_compile.sh"
check "build failure returns UBT's exit code (6)" [ $? -eq 6 ]
check "  …and writes the failure report" has "$SANDBOX/logs/FAILURE_REPORT.txt" "UBT exit code:  6"
check "  …and names the one file to send back" has "$O" "Send back this one file: $SANDBOX/logs/FAILURE_REPORT.txt"
fresh
FAKE_GEN_EXIT=4 T_UE_ROOT="$UE58" run "$O" "$MAC/first_compile.sh"
check "generation failure stops before the build (exit 4)" [ $? -eq 4 ]
check "  …Build.sh never ran" [ ! -f "$FAKE_RECORD/build-args" ]
fresh
run "$O" "$MAC/first_compile.sh"
check "without Unreal: stops cleanly (exit 1)" [ $? -eq 1 ]
check "  …explains exactly what is missing" has "$O" "Unreal Engine 5.8 was not found."
check "  …nothing was built or generated" bash -c '[ ! -f "$1/build-args" ] && [ ! -f "$1/gen-args" ]' _ "$FAKE_RECORD"
check "  …native tests not started" [ ! -f "$SANDBOX/logs/native-tests-latest.log" ]

echo "portability (macOS bash 3.2 / BSD userland) and lint"
NOT_32='declare -A|mapfile|readarray|\$\{[A-Za-z_]+(,,|\^\^)|&>>|\|&|coproc|local -n|readlink -f|sed -i|stat -c|date -d|grep -P|\bsort -V'
check "no bash 4 / GNU-only constructs" bash -c '! grep -nE "$1" "$2"/*.sh' _ "$NOT_32" "$MAC"
check "scripts are executable (except the sourced lib.sh)" bash -c 'for f in "$1"/*.sh; do case "$f" in */lib.sh) [ ! -x "$f" ] || exit 1 ;; *) [ -x "$f" ] || exit 1 ;; esac; done' _ "$MAC"
if command -v shellcheck >/dev/null 2>&1; then
	check "shellcheck clean ($(shellcheck --version | sed -n 's/^version: //p'))" shellcheck -x -s bash "$MAC"/*.sh "$TESTS"/*.sh
else
	echo "  skip  shellcheck not installed"
fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
