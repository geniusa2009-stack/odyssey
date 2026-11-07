"""Process-wide game dependencies (created once in the application lifespan)."""

from __future__ import annotations

from dataclasses import dataclass

from app.game.application.identity import GameIdentityProvider
from app.game.content.loader import LoadedContent
from app.game.realtime.bus import GameBus
from app.game.runtime.clock import Clock


@dataclass
class GameRuntime:
    content: LoadedContent
    bus: GameBus
    clock: Clock
    identity: GameIdentityProvider
    event_retention: int = 2000
    auto_checkpoint_every: int = 25
    auto_checkpoints_kept: int = 10
