"""Architecture rules enforced by tests (layer boundaries the spec makes non-negotiable)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

FORBIDDEN_IN_SIMULATION = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "redis",
    "httpx",
    "asyncpg",
    "aiosqlite",
    "uvicorn",
    "anyio",
    "app.api",
    "app.db",
    "app.services",
    "app.repositories",
    "app.ai",
    "app.realtime",
    "app.nasa",
    "app.schemas",
    "app.telemetry",
    "app.core",
)
ALLOWED_THIRD_PARTY_IN_SIMULATION = {"pydantic", "yaml"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _py_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _py_files(APP / "simulation"), ids=lambda p: p.name)
def test_simulation_is_standalone(path: Path) -> None:
    for module in _imports(path):
        assert not module.startswith(FORBIDDEN_IN_SIMULATION), f"{path} imports {module}"
        top = module.split(".")[0]
        if top not in ("app", "__future__") and top not in ALLOWED_THIRD_PARTY_IN_SIMULATION:
            # Remaining imports must be standard library.
            import sys

            assert top in sys.stdlib_module_names, f"{path} imports third-party {module}"


def test_canonical_module_is_pure_stdlib() -> None:
    import sys

    for module in _imports(APP / "simulation" / "canonical.py"):
        assert module.split(".")[0] in sys.stdlib_module_names | {"__future__"}


@pytest.mark.parametrize("path", _py_files(APP / "ai"), ids=lambda p: p.name)
def test_ai_layer_has_no_write_path(path: Path) -> None:
    """ORION may read engine outputs but never import the engine, DB, services or replay."""
    for module in _imports(path):
        assert not module.startswith(
            (
                "app.db",
                "app.services",
                "app.repositories",
                "app.simulation.engine.engine",
                "app.simulation.replay.replay",
                "sqlalchemy",
            )
        ), module


def test_api_layer_does_not_touch_the_database_directly() -> None:
    """Routes go through the service layer (no raw ORM models / SQL in route handlers)."""
    for path in _py_files(APP / "api" / "v1"):
        for module in _imports(path):
            assert module != "app.db.models", f"{path} imports ORM models"


def test_no_frontend_artifacts_in_repository() -> None:
    suspicious = [
        p
        for p in ROOT.rglob("*")
        if p.suffix in {".tsx", ".jsx", ".css", ".scss", ".vue", ".svelte"}
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
    ]
    assert suspicious == []
