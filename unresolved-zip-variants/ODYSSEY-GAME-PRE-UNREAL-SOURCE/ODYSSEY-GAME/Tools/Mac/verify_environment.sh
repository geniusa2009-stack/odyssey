#!/usr/bin/env bash
# Checks that this Mac can build ODYSSEY with Unreal Engine 5.8 and reports the environment.
# Exit 0 = every required item present (warnings allowed); exit 1 = something required is missing.
# Also writes the summary to Logs/environment.txt (used by collect_failure_report.sh).
#
#   bash Tools/Mac/verify_environment.sh
set -o pipefail
# shellcheck source=Tools/Mac/lib.sh
. "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

MIN_FREE_GB=20      # below this: fail (project build + DerivedDataCache)
WARN_FREE_GB=60
WARN_RAM_GB=16

FAILS=0
WARNS=0
SUMMARY=""
line() { SUMMARY="${SUMMARY}$1"$'\n'; printf '%s\n' "$1"; }
ok() { line "$(printf '  %-5s %-22s %s' OK "$1" "$2")"; }
warn() { WARNS=$((WARNS + 1)); line "$(printf '  %-5s %-22s %s' WARN "$1" "$2")"; }
fail() { FAILS=$((FAILS + 1)); line "$(printf '  %-5s %-22s %s' FAIL "$1" "$2")"; }

line "ODYSSEY macOS environment check ($(date '+%Y-%m-%d %H:%M:%S'))"

# ---------------------------------------------------------------- OS / CPU / memory
if [ "$(uname -s)" != "Darwin" ]; then
	fail "macOS" "this is $(uname -s), not macOS"
else
	ok "macOS" "$(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null) ($(sw_vers -buildVersion 2>/dev/null))"
fi

ARCH="$(uname -m)"
TRANSLATED="$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)"
CPU="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
if [ "$TRANSLATED" = "1" ]; then
	fail "Apple Silicon" "$CPU — this shell runs under Rosetta (x86_64); open a native arm64 Terminal"
elif [ "$ARCH" = "arm64" ]; then
	ok "Apple Silicon" "$CPU, arm64 native"
else
	fail "Apple Silicon" "architecture is $ARCH (arm64 required)"
fi

MEM_BYTES="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
MEM_GB=$((MEM_BYTES / 1073741824))
if [ "$MEM_GB" -le 0 ]; then
	warn "RAM" "unknown"
elif [ "$MEM_GB" -lt "$WARN_RAM_GB" ]; then
	warn "RAM" "${MEM_GB} GB (below ${WARN_RAM_GB} GB: expect slow editor builds; close other apps)"
else
	ok "RAM" "${MEM_GB} GB"
fi

# ---------------------------------------------------------------- Xcode toolchain
DEV_DIR="$(xcode-select -p 2>/dev/null || true)"
if command -v xcodebuild >/dev/null 2>&1 && XCODE_VER="$(xcodebuild -version 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')" && [ -n "$XCODE_VER" ]; then
	ok "Xcode" "$XCODE_VER"
else
	fail "Xcode" "full Xcode not available (xcodebuild -version failed). Install Xcode from the App Store, open it once, then: sudo xcodebuild -license accept"
fi
case "$DEV_DIR" in
	"") fail "Developer directory" "xcode-select -p returned nothing" ;;
	*CommandLineTools*) fail "Developer directory" "$DEV_DIR — only Command Line Tools selected; run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" ;;
	*) ok "Developer directory" "$DEV_DIR" ;;
esac
for tool in clang++ make python3 git; do
	if command -v "$tool" >/dev/null 2>&1; then
		ok "$tool" "$(command -v "$tool")"
	else
		fail "$tool" "not found (provided by Xcode / Command Line Tools)"
	fi
done

# ---------------------------------------------------------------- Unreal Engine
if UE="$(ody_find_ue)"; then
	ok "Unreal Engine" "$(ody_ue_version_of "$UE") at $UE"
else
	fail "Unreal Engine" "$ODYSSEY_UE_VERSION not found (details below)"
	ody_explain_missing_ue 2>&1 | sed 's/^/        /'
fi

# ---------------------------------------------------------------- disk
FREE_KB="$(df -Pk "$ODYSSEY_ROOT" 2>/dev/null | awk 'NR == 2 { print $4 }')"
FREE_GB=$(( ${FREE_KB:-0} / 1048576 ))
if [ "$FREE_GB" -lt "$MIN_FREE_GB" ]; then
	fail "Disk space" "${FREE_GB} GB free on the project volume (need at least ${MIN_FREE_GB} GB)"
elif [ "$FREE_GB" -lt "$WARN_FREE_GB" ]; then
	warn "Disk space" "${FREE_GB} GB free (DerivedDataCache can grow large; ${WARN_FREE_GB} GB+ recommended)"
else
	ok "Disk space" "${FREE_GB} GB free"
fi

# ---------------------------------------------------------------- repository
if git -C "$ODYSSEY_ROOT" rev-parse HEAD >/dev/null 2>&1; then
	ok "git HEAD" "$(git -C "$ODYSSEY_ROOT" rev-parse HEAD) ($(git -C "$ODYSSEY_ROOT" branch --show-current 2>/dev/null || echo detached))"
	DIRTY="$(git -C "$ODYSSEY_ROOT" status --porcelain | wc -l | tr -d ' ')"
	if [ "$DIRTY" = "0" ]; then
		ok "git status" "clean"
	else
		warn "git status" "$DIRTY changed/untracked paths (the build uses the working tree as it is)"
		while IFS= read -r l; do line "          $l"; done <<EOF
$(git -C "$ODYSSEY_ROOT" status --porcelain | head -n 15)
EOF
	fi
else
	warn "git HEAD" "$ODYSSEY_ROOT is not a git repository (copied without .git?)"
fi
if [ -f "$ODYSSEY_PROJECT" ]; then
	ok "Project" "$ODYSSEY_PROJECT"
else
	fail "Project" "$ODYSSEY_PROJECT not found"
fi

line ""
if [ "$FAILS" -gt 0 ]; then
	line "RESULT: FAIL — $FAILS required item(s) missing, $WARNS warning(s)."
else
	line "RESULT: OK — $WARNS warning(s)."
fi

if LOGS="$(ody_log_dir)"; then
	printf '%s' "$SUMMARY" >"$LOGS/environment.txt"
fi
[ "$FAILS" -eq 0 ]
