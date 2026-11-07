"""ODYSSEY game backend domain (Unreal Engine client): the authoritative mission/campaign brain.

The simulation engine (``app/simulation``) stays the source of physical/mission truth. This
package adds the open-world game layer on top of it: versioned content, a semantic world
model, semantic actions, campaign progression, capabilities and certification, inventory,
cargo and modules, knowledge and discoveries, a server-authoritative mission clock, saves,
realtime protocol ``odyssey.game.v1`` and adapters for Future Lens, Black Box and Rewind.

Unreal owns movement, physics, animation, rendering and presentation; nothing here receives
per-frame data. See docs/GAME_BACKEND_ARCHITECTURE.md.
"""

GAME_PROTOCOL = "odyssey.game.v1"
