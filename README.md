# ODYSSEY-GAME

Unreal Engine 5.8 client for ODYSSEY — **Phase 6: vertical slice foundation (Earth Command)**.

> **Checkpoint status: integration scaffold, pending Unreal Editor verification.**
> The protocol core is verified natively and against a live backend; all Unreal-dependent code,
> config and scripts are marked `UNREAL_EDITOR_VERIFICATION_REQUIRED` and have not been compiled
> or run. See [Docs/STATUS.md](Docs/STATUS.md).

Backend: `odyssey` (separate repository), protocol `odyssey.game.v1`, protected checkpoint
`4f7be839a21b054b83d34151c56510fa45ba18a4`.

## Layout

```
Odyssey.uproject                 UE 5.8 project (8 game modules + OdysseyAPI plugin)
Source/Odyssey{Core,Realtime,Backend,World,Interaction,UI,Player,Debug}/
Plugins/OdysseyAPI/              engine-independent odyssey.game.v1 protocol core + shared tests
Config/                          per-environment backend settings (no secrets), engine, input
Content/                         folder plan + the generated semantic id registry JSON (no .uasset yet)
Tests/Fixtures/odyssey.game.v1/  the backend's recorded contract (vendored, hash-pinned)
Tests/Schemas/odyssey.game.v1/   realtime frame schema exported from the backend models
Tools/Contract/                  fixture sync, realtime schema export
Tools/SemanticIds/               registry generator (backend content → DataTable JSON)
Tools/ProtocolCore/              native test runner, live backend harness
Tools/Editor/                    editor Python: registry import, Earth Command greybox
Docs/                            architecture, integration, ids, interaction, realtime, testing, pipeline …
```

## Quick start (no Unreal needed)

```bash
make -C Tools/ProtocolCore test                                  # 22 cases against the real fixtures
ODYSSEY_BACKEND=../odyssey Tools/ProtocolCore/run_live.sh        # live backend, fault injection
python3 Tools/Contract/sync_fixtures.py --backend ../odyssey --check
```

## With Unreal Engine 5.8 (Apple Silicon)

Follow [Docs/VERIFICATION_CHECKLIST.md](Docs/VERIFICATION_CHECKLIST.md) step by step and bring
back the observed results.

## Documentation

[Architecture](Docs/ARCHITECTURE.md) · [Backend integration](Docs/BACKEND_INTEGRATION.md) ·
[Semantic ids](Docs/SEMANTIC_IDS.md) · [Interaction system](Docs/INTERACTION_SYSTEM.md) ·
[Realtime](Docs/REALTIME.md) · [Testing](Docs/TESTING.md) · [Content pipeline](Docs/CONTENT_PIPELINE.md) ·
[Protocol generation](Docs/PROTOCOL_GENERATION.md) · [Greybox spec](Docs/EARTH_COMMAND_GREYBOX.md) ·
[Status](Docs/STATUS.md)
