#!/usr/bin/env bash
# Condenses a failed Unreal build log into ONE short report to paste back:
# first compiler/UHT error with surrounding lines, every unique error (module, file, line),
# Unreal Build Tool exit code, last 100 log lines, environment summary.
#
#   bash Tools/Mac/collect_failure_report.sh [LOG] [EXIT_CODE]
# Defaults: Logs/build-editor-latest.log and Logs/build-editor-latest.exitcode.
# Output:   Logs/FAILURE_REPORT.txt (path printed on stdout).
set -o pipefail
# shellcheck source=Tools/Mac/lib.sh
. "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

LOGS="$(ody_log_dir)" || exit 1
LOG="${1:-$LOGS/build-editor-latest.log}"
EXIT_CODE="${2:-}"
if [ -z "$EXIT_CODE" ] && [ -f "$LOGS/build-editor-latest.exitcode" ] && [ "$LOG" = "$LOGS/build-editor-latest.log" ]; then
	EXIT_CODE="$(cat "$LOGS/build-editor-latest.exitcode")"
fi
if [ ! -f "$LOG" ]; then
	echo "no log to analyse: $LOG (run bash Tools/Mac/build_editor.sh first)" >&2
	exit 1
fi
REPORT="$LOGS/FAILURE_REPORT.txt"
HEAD_INFO="$(git -C "$ODYSSEY_ROOT" rev-parse HEAD 2>/dev/null || echo 'not a git checkout') $(git -C "$ODYSSEY_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ') changed paths"

python3 -I - "$LOG" "${EXIT_CODE:-unknown}" "$ODYSSEY_ROOT" "$LOGS/environment.txt" "$HEAD_INFO" >"$REPORT" <<'PY'
import os
import re
import sys

log_path, exit_code, root, env_path, head_info = sys.argv[1:6]
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
with open(log_path, encoding="utf-8", errors="replace") as f:
    lines = [ANSI.sub("", l.rstrip("\n")) for l in f]

SRC = r"(?:c|cc|cpp|cxx|h|hh|hpp|inl|m|mm)"
PATTERNS = [
    ("compile", re.compile(r"(?P<file>/[^:]+?\." + SRC + r"):(?P<line>\d+):(?:(?P<col>\d+):)? (?:fatal )?error: (?P<msg>.*)$")),
    ("uht", re.compile(r"(?P<file>/[^()]+?\.(?:h|cpp))\((?P<line>\d+)\)\s*:\s*Error\s*:\s*(?P<msg>.*)$")),
    ("buildcs", re.compile(r"(?P<file>/[^()]+?\.cs)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*error (?P<msg>CS\d+:.*)$")),
    ("link", re.compile(r"^(?P<msg>Undefined symbols for architecture \S+:)")),
    ("link", re.compile(r"^ld: (?:error: )?(?P<msg>.*(?:error|not found|duplicate symbol).*)$")),
    ("link", re.compile(r"(?P<msg>clang(?:\+\+)?: error: linker command failed.*)$")),
    ("ubt", re.compile(r"^(?:ERROR|Error): (?P<msg>.*)$")),
    ("ubt", re.compile(r"(?P<msg>Unhandled exception.*)$")),
    ("compile", re.compile(r"(?P<msg>.*\berror: .*)$")),  # fallback for anything else clang-like
]
ACTION = re.compile(r"^\[\d+/\d+\] (?:Compile|Link|Archive|Copy|Generate)[^\]]*\] (?P<obj>\S+)")

# basename -> module, from the repository's own sources (for errors without a path)
module_of_file = {}
for base_dir in ("Source", "Plugins"):
    for dirpath, _dirs, files in os.walk(os.path.join(root, base_dir)):
        m = re.search(r"(?:^|/)(?:Plugins/[^/]+/)?Source/([^/]+)", os.path.relpath(dirpath, root))
        if m:
            for fn in files:
                module_of_file.setdefault(fn, m.group(1))


def module_for(path, last_obj):
    if path:
        m = re.search(r"/(?:Plugins/[^/]+/)?Source/([^/]+)/", path)
        if m and "/Engine/" not in path:
            name = m.group(1)
            if name.endswith(".Build.cs") or name.endswith(".Target.cs"):
                return name.split(".")[0]
            return name
        m = re.search(r"/Engine/(?:Plugins/.+?/)?Source/(?:Runtime|Editor|Developer|Programs|ThirdParty)/([^/]+)/", path)
        if m:
            return "Engine:" + m.group(1)
        if path.endswith(".Build.cs"):
            return os.path.basename(path).split(".")[0]
        if os.path.basename(path) in module_of_file:
            return module_of_file[os.path.basename(path)]
    if last_obj:
        m = re.search(r"(?:Module\.|UnrealEditor-|libUnrealEditor-)([A-Za-z0-9_]+?)(?:\.\d+)?\.(?:cpp|dylib|a|o)", last_obj)
        if m:
            return m.group(1)
        if os.path.basename(last_obj) in module_of_file:
            return module_of_file[os.path.basename(last_obj)]
    return "unknown"


def rel(path):
    if path and path.startswith(root + "/"):
        return path[len(root) + 1:]
    if path:
        m = re.search(r"/(Source|Plugins|Config)/.*$", path)
        if m and "/Engine/" not in path:
            return m.group(0)[1:]
    return path or "-"


errors = []  # dicts in log order
last_obj = None
for i, text in enumerate(lines):
    a = ACTION.search(text)
    if a:
        last_obj = a.group("obj")
        continue
    for kind, rx in PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        g = m.groupdict()
        if kind == "compile" and "file" not in g and ("warning" in text.split("error:")[0]):
            break
        msg = g.get("msg", "").strip()
        if kind == "link" and msg.startswith("Undefined symbols"):
            syms = []
            for nxt in lines[i + 1:i + 8]:
                s = nxt.strip()
                if s.startswith('"') or s.startswith("_"):
                    syms.append(s)
            if syms:
                msg += " " + " | ".join(syms[:4])
        path = g.get("file")
        errors.append({
            "index": i, "kind": kind, "file": path, "line": g.get("line") or "-",
            "module": module_for(path, last_obj), "msg": msg,
        })
        break

# a fallback match on a line already matched by a more specific pattern is impossible (break),
# but drop pure duplicates of the summary line clang prints after an error count
unique = {}
order = []
for e in errors:
    key = (e["kind"], e["file"], e["line"], e["msg"])
    if key not in unique:
        unique[key] = dict(e, count=0)
        order.append(key)
    unique[key]["count"] += 1

warnings = sum(1 for l in lines if re.search(r"\bwarning: ", l))
result_line = next((l.strip() for l in reversed(lines) if l.strip().startswith("Result: ")), "-")
ubt_log = next((l.split("Log file:", 1)[1].strip() for l in lines if "Log file:" in l), "-")

out = []
w = out.append
w("ODYSSEY UNREAL BUILD FAILURE REPORT")
w("=" * 72)
w(f"Log:            {log_path}")
w(f"UBT exit code:  {exit_code}")
w(f"UBT result:     {result_line}")
w(f"UBT Log.txt:    {ubt_log}")
w(f"Repository:     {head_info}")
w(f"Log lines:      {len(lines)}   errors: {len(errors)} ({len(order)} unique)   warnings: {warnings}")
w("")
if errors:
    first = errors[0]
    w("FIRST ERROR")
    w("-" * 72)
    w(f"[{first['kind']}] module {first['module']}  {rel(first['file'])}:{first['line']}")
    w(f"  {first['msg']}")
    w("")
    w(f"Surrounding log lines ({max(0, first['index'] - 6) + 1}-{min(len(lines), first['index'] + 11)}):")
    for j in range(max(0, first["index"] - 6), min(len(lines), first["index"] + 11)):
        w(("> " if j == first["index"] else "  ") + lines[j][:400])
    w("")
    by_module = {}
    for k in order:
        by_module[unique[k]["module"]] = by_module.get(unique[k]["module"], 0) + 1
    w("ERRORS PER MODULE: " + ", ".join(f"{m} {n}" for m, n in sorted(by_module.items())))
    w("")
    w(f"ALL UNIQUE ERRORS ({len(order)})")
    w("-" * 72)
    for n, k in enumerate(order[:80], 1):
        e = unique[k]
        times = f" (x{e['count']})" if e["count"] > 1 else ""
        w(f"{n:3d}. [{e['kind']}] {e['module']} | {rel(e['file'])}:{e['line']}{times}")
        w(f"     {e['msg'][:300]}")
    if len(order) > 80:
        w(f"     … {len(order) - 80} more unique errors in the full log")
else:
    w("FIRST ERROR")
    w("-" * 72)
    w("No compiler/UHT/linker/UBT error line was recognised. The build may have been interrupted,")
    w("or failed in a step that prints a different format — see the last log lines below.")
w("")
w("LAST 100 LOG LINES")
w("-" * 72)
for l in lines[-100:]:
    w(l[:400])
w("")
w("ENVIRONMENT")
w("-" * 72)
if os.path.isfile(env_path):
    with open(env_path, encoding="utf-8", errors="replace") as f:
        out.extend(l.rstrip("\n") for l in f)
else:
    w("(no Logs/environment.txt — run: bash Tools/Mac/verify_environment.sh)")
w("")
w("Send this whole file back (Logs/FAILURE_REPORT.txt).")
print("\n".join(out))
PY
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
	echo "failure report generation failed (python3 exit $STATUS)" >&2
	exit "$STATUS"
fi
printf '%s\n' "$REPORT"
