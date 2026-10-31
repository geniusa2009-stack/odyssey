#!/usr/bin/env bash
# Shared helpers for the macOS Unreal verification toolkit. Sourced, not executed.
# Compatible with the bash 3.2 that ships with macOS (no bash 4 features) and BSD userland.
#
# Overrides (environment):
#   UE_ROOT            Unreal Engine 5.8 root (the folder that contains Engine/)
#   ODYSSEY_LOG_DIR    where logs/reports go (default: <repo>/Logs)

ODYSSEY_MAC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ODYSSEY_ROOT="$(cd "$ODYSSEY_MAC_DIR/../.." && pwd -P)"
ODYSSEY_PROJECT="$ODYSSEY_ROOT/Odyssey.uproject"
ODYSSEY_LOG_DIR="${ODYSSEY_LOG_DIR:-$ODYSSEY_ROOT/Logs}"
ODYSSEY_UE_VERSION="5.8"
export ODYSSEY_MAC_DIR ODYSSEY_ROOT ODYSSEY_PROJECT ODYSSEY_LOG_DIR ODYSSEY_UE_VERSION

ody_timestamp() { date +%Y%m%d-%H%M%S; }

ody_log_dir() {
	mkdir -p "$ODYSSEY_LOG_DIR" || { echo "cannot create log directory $ODYSSEY_LOG_DIR" >&2; return 1; }
	printf '%s\n' "$ODYSSEY_LOG_DIR"
}

ody_info() { printf '  %-6s %s\n' "$1" "$2"; }

# Prints "MAJOR.MINOR" from <root>/Engine/Build/Build.version, or nothing.
ody_ue_version_of() {
	local f="$1/Engine/Build/Build.version" major minor
	[ -f "$f" ] || return 1
	major="$(grep -E '"MajorVersion"' "$f" | grep -oE '[0-9]+' | head -n 1)"
	minor="$(grep -E '"MinorVersion"' "$f" | grep -oE '[0-9]+' | head -n 1)"
	[ -n "$major" ] && [ -n "$minor" ] || return 1
	printf '%s.%s\n' "$major" "$minor"
}

# A usable engine root: right version and the macOS build scripts present.
ody_is_ue58() {
	local root="$1"
	[ -n "$root" ] && [ -d "$root/Engine" ] || return 1
	[ -x "$root/Engine/Build/BatchFiles/Mac/Build.sh" ] || return 1
	[ "$(ody_ue_version_of "$root")" = "$ODYSSEY_UE_VERSION" ] || return 1
}

# Candidate engine roots, one per line, most specific first. No machine-specific path is assumed:
# explicit UE_ROOT, then the Epic Games Launcher's install manifest, then the usual locations.
ody_ue_candidates() {
	if [ -n "${UE_ROOT:-}" ]; then
		printf '%s\n' "$UE_ROOT"
	fi
	local manifest="$HOME/Library/Application Support/Epic/UnrealEngineLauncher/LauncherInstalled.dat"
	if [ -f "$manifest" ]; then
		grep -oE '"InstallLocation"[[:space:]]*:[[:space:]]*"[^"]+"' "$manifest" |
			sed -E 's/^"InstallLocation"[[:space:]]*:[[:space:]]*"//; s/"$//; s#\\/#/#g'
	fi
	local base
	for base in "/Users/Shared/Epic Games" "$HOME/Epic Games" "/Applications/Epic Games" "$HOME/UnrealEngine"; do
		[ -d "$base" ] || continue
		printf '%s\n' "$base/UE_$ODYSSEY_UE_VERSION"
		find "$base" -maxdepth 1 -type d -name "UE_${ODYSSEY_UE_VERSION}*" 2>/dev/null
	done
}

# Prints the first usable UE 5.8 root; returns 1 if none.
ody_find_ue() {
	local c
	while IFS= read -r c; do
		[ -n "$c" ] || continue
		if ody_is_ue58 "$c"; then
			(cd "$c" && pwd -P)
			return 0
		fi
	done <<EOF
$(ody_ue_candidates)
EOF
	return 1
}

# Explains exactly what is missing when no engine is found (stderr).
ody_explain_missing_ue() {
	{
		echo "Unreal Engine $ODYSSEY_UE_VERSION was not found."
		if [ -n "${UE_ROOT:-}" ]; then
			if [ ! -d "$UE_ROOT/Engine" ]; then
				echo "  UE_ROOT=$UE_ROOT has no Engine/ folder."
			elif [ ! -x "$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh" ]; then
				echo "  UE_ROOT=$UE_ROOT has no Engine/Build/BatchFiles/Mac/Build.sh (not a macOS engine install?)."
			else
				echo "  UE_ROOT=$UE_ROOT is version $(ody_ue_version_of "$UE_ROOT" || echo unknown), not $ODYSSEY_UE_VERSION."
			fi
		fi
		echo "  Searched: \$UE_ROOT, the Epic Games Launcher manifest, /Users/Shared/Epic Games, ~/Epic Games,"
		echo "            /Applications/Epic Games, ~/UnrealEngine (folders named UE_$ODYSSEY_UE_VERSION*)."
		echo "  Fix: install Unreal Engine $ODYSSEY_UE_VERSION with the Epic Games Launcher, or point to an existing"
		echo "       install:   UE_ROOT=\"/path/to/UE_$ODYSSEY_UE_VERSION\" bash Tools/Mac/first_compile.sh"
	} >&2
}
