#!/usr/bin/env python3
"""Export the JSON Schema of the odyssey.game.v1 WebSocket frames from the backend models.

OpenAPI does not describe WebSocket messages, so the backend's frozen openapi-game-v1.json has no
schema for the realtime control frames (CONNECTED / RESUMED / RESYNC_REQUIRED / PONG). This tool
reads the backend's own pydantic models (app.game.contracts.protocol: GameControlFrame,
GameEventEnvelope) and writes them in the same components/schemas layout as the OpenAPI file,
so the client tests validate realtime frames with the same validator.

    <backend>/.venv/bin/python Tools/Contract/export_realtime_schema.py --backend ../odyssey --write
    <backend>/.venv/bin/python Tools/Contract/export_realtime_schema.py --backend ../odyssey --check

Read-only with respect to the backend.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Tests" / "Schemas" / "odyssey.game.v1" / "realtime-frames.schema.json"
MODELS = ("GameControlFrame", "GameEventEnvelope")


def build(backend: Path) -> str:
    sys.path.insert(0, str(backend))
    from pydantic.json_schema import models_json_schema  # noqa: PLC0415

    from app.game.contracts import protocol  # noqa: PLC0415

    models = [(getattr(protocol, name), "validation") for name in MODELS]
    _, schema = models_json_schema(models, ref_template="#/components/schemas/{model}")
    commit = subprocess.run(
        ["git", "-C", str(backend), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    doc = {
        "x-odyssey-generated-from": {
            "backend_commit": commit,
            "models": [f"app.game.contracts.protocol:{m}" for m in MODELS],
            "tool": "Tools/Contract/export_realtime_schema.py",
        },
        "components": {"schemas": schema.get("$defs", {})},
    }
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = build(args.backend.resolve())
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        print(f"{OUT.relative_to(ROOT)} is out of date with the backend models; run --write")
        return 1
    print("realtime frame schema matches the backend models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
