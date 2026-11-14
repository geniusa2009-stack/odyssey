# ODYSSEY live stream (Pixel Streaming 2) — deploy kit

Status: **prepared, not deployed.** Running it needs a paid cloud GPU, which has not been approved yet.
Nothing in this folder runs on the Mac, and the Unreal Editor is never launched locally.

## What it does
1. `build_linux_package.sh` runs on a rented Linux build host (about 32 vCPU, 64 GB RAM, 400 GB disk). It builds stock UE `5.8.4-release` from `EpicGames/UnrealEngine`, then cooks and packages this branch for Linux (Development) and writes `odyssey-linux-<date>-<rev>.tar.gz` plus its sha256.
2. `setup_stream_host.sh` runs on an NVIDIA GPU host (AWS `g4dn.xlarge`, T4, Ubuntu 22.04 with the NVIDIA driver). It installs and starts:
   - the backend in Docker on `127.0.0.1:8000`, with mock AI and SQLite, matching `DefaultEnvironment=development`;
   - the game rendering off-screen (`-RenderOffscreen -PixelStreamingURL=ws://127.0.0.1:8888`);
   - Epic's Wilbur signalling server (`EpicGamesExt/PixelStreamingInfrastructure`, branch `UE5.8`);
   - coturn for STUN/TURN, with a generated credential;
   - Caddy for HTTPS with an automatic certificate. Optional basic auth (user `judge`) is enabled with `ACCESS_PASSWORD`.
3. Releases are kept under `/opt/odyssey/releases/<version>`, and `/opt/odyssey/current` is a symlink. To roll back, point `current` at the previous release and run `systemctl restart odyssey-game`.

The project change on this branch enables `PixelStreaming2` for the Linux and Win64 targets only, so the Mac editor is unaffected, and adds Linux to `TargetPlatforms`.

## Firewall
Open only these ports:
- TCP 80, 443, 3478 and 5349;
- UDP 3478 and 49152–65535.

The backend (8000), the signalling server's player port (8080) and its streamer port (8888) stay on localhost.

## Connecting the judges site
After the stream URL has been checked from an outside network (it loads, the game renders, keyboard and mouse work), set `liveDemoUrl` in `judges-site/content.json` on `deploy/judges`. Render then redeploys the site. If the stream is down, the site keeps working, because the button only opens a separate tab.

## Cost (AWS on-demand, approximate)
| Item | Cost |
|---|---|
| Build host, a few hours, one-off | about $10–15 |
| `g4dn.xlarge` stream host | about $0.53/h, or about $13/day while running, plus disk |

Stop the instance when it isn't needed.

## Known risks to check on first run
- The local engine is a fork; this kit builds against the stock 5.8.4 tag. The project sources do not reference the fork's changes, but a first Linux compile may surface platform-specific fixes.
- One game instance serves one shared session. Several judges at once would share control; scale with more instances behind the SFU or a matchmaker if needed.
