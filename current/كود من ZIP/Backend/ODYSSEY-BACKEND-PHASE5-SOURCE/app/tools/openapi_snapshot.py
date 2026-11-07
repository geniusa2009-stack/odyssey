"""Normalised OpenAPI snapshot of API v1 (``tests/fixtures/contract/openapi-v1.json``).

``python -m app.tools.openapi_snapshot --check`` (exit 1 and list differences when it changed)
``python -m app.tools.openapi_snapshot --write`` (update after a reviewed API change)

Any change to the OpenAPI schema — breaking or additive — shows up as a difference, so every
API change is reviewed against docs/API_FREEZE_V1.md before the snapshot is updated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "contract" / "openapi-v1.json"


def current_schema() -> dict[str, Any]:
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        log_json=False,
        redis_url=None,
    )
    schema = create_app(settings).openapi()
    normalized: dict[str, Any] = json.loads(json.dumps(schema, sort_keys=True))
    return normalized


def differences(old: Any, new: Any, path: str = "") -> list[str]:
    """Human-readable list of differences between two JSON values (empty when equal)."""
    if isinstance(old, dict) and isinstance(new, dict):
        out: list[str] = []
        for key in sorted(set(old) | set(new)):
            where = f"{path}/{key}"
            if key not in new:
                out.append(f"removed: {where}")
            elif key not in old:
                out.append(f"added: {where}")
            else:
                out.extend(differences(old[key], new[key], where))
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [f"changed: {path} (list length {len(old)} → {len(new)})"]
        out = []
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            out.extend(differences(a, b, f"{path}[{i}]"))
        return out
    if old != new:
        return [f"changed: {path or '/'}: {json.dumps(old)[:80]} → {json.dumps(new)[:80]}"]
    return []


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAPI snapshot of API v1")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    schema = current_schema()
    if args.write:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(render(schema), encoding="utf-8")
        print(f"wrote {FIXTURE.relative_to(ROOT)}")
        return 0
    if not FIXTURE.exists():
        print(f"missing {FIXTURE.relative_to(ROOT)}; run with --write")
        return 1
    diff = differences(json.loads(FIXTURE.read_text(encoding="utf-8")), schema)
    if diff:
        print("OpenAPI schema changed:")
        print("\n".join(diff))
        return 1
    print("OpenAPI schema unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
