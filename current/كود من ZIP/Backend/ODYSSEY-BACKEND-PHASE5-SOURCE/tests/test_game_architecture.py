"""Game domain boundaries (docs/GAMEPLAY_BACKEND_BOUNDARIES.md), enforced on imports."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.test_architecture import _imports, _py_files

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "app" / "game"

# The pure game core: no web framework, no database, no services, no Redis.
PURE = [
    GAME / "actions",
    GAME / "adapters",
    GAME / "campaign",
    GAME / "content",
    GAME / "contracts",
    GAME / "inventory",
    GAME / "progression",
    GAME / "runtime",
    GAME / "world",
]
PURE_FILES = [
    *(f for d in PURE for f in _py_files(d)),
    GAME / "realtime" / "derive.py",
    GAME / "application" / "turn.py",
    GAME / "application" / "memory.py",
    GAME / "application" / "ports.py",
    GAME / "application" / "readviews.py",
]
FORBIDDEN_IN_CORE = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "redis",
    "httpx",
    "app.api",
    "app.db",
    "app.services",
    "app.repositories",
    "app.realtime",
    "app.game.api",
    "app.game.persistence",
    "app.game.application.service",
)


@pytest.mark.parametrize("path", PURE_FILES, ids=lambda p: str(p.relative_to(GAME)))
def test_game_core_is_pure(path: Path) -> None:
    for module in _imports(path):
        assert not module.startswith(FORBIDDEN_IN_CORE), f"{path} imports {module}"


@pytest.mark.parametrize("path", _py_files(ROOT / "app" / "simulation"), ids=lambda p: p.name)
def test_simulation_does_not_know_the_game(path: Path) -> None:
    assert not any(m.startswith("app.game") for m in _imports(path)), path


def test_only_the_game_api_package_uses_the_web_framework() -> None:
    for path in _py_files(GAME):
        if "api" in path.relative_to(GAME).parts:
            continue
        for module in _imports(path):
            assert not module.startswith(("fastapi", "starlette")), f"{path} imports {module}"


def test_no_unreal_frontend_or_3d_files_in_the_repository() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    forbidden_ext = (
        ".uproject",
        ".uplugin",
        ".uasset",
        ".umap",
        ".cpp",
        ".hpp",
        ".fbx",
        ".obj",
        ".glb",
        ".gltf",
        ".blend",
        ".png",
        ".jpg",
        ".tsx",
        ".jsx",
        ".vue",
    )
    offenders = [p for p in tracked if p.lower().endswith(forbidden_ext)]
    assert offenders == []
    assert not any(p.startswith(("frontend/", "web/", "Unreal/", "Source/")) for p in tracked)
