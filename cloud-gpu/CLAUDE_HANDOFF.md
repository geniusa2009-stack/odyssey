# ODYSSEY Cloud GPU — execution handoff

Status as of 2026-11-14: **GPU provider not provisioned; game package not uploaded.** This branch is a preparation handoff, not evidence of a running stream.

## Source and safety
- Source: `geniusa2009-stack/odyssey`; the remote `main` is an older snapshot, not proof of the latest local game.
- Protected Git snapshot: `release/baseline-2026-11-14`.
- Public judges website: https://odyssey-judges-preview.onrender.com (Render static site, source branch `deploy/judges`).
- The local Apple Silicon UE 5.8.4 `OdysseyEditor` build with Pixel Streaming 2 succeeded, but the **8 GB Mac freezes running Unreal**. Do NOT launch Unreal locally or build/ cook/ package locally.
- No Windows executable nor GPU-cloud stream has been verified.
- Never expose licensed engine source, secrets, signing keys, or a remotely accessible Unreal editor to public visitors.

## Preferred deployment
- **Vagon Streams (Windows native Pixel Streaming)**: https://vagon.io/streams and https://docs.vagon.io/streams/unreal-engine-pixel-streaming
- Proposed session GPU: NVIDIA L4 24 GB, 16 GB system RAM (Starter G3). Verify quota and Unreal 5.8.4 + Pixel Streaming 2 compatibility with provider **before spending**.
- Provider pricing shown publicly at https://vagon.io/streams/pricing; GPU minutes and application maintenance may cost money. Do not initiate a paid session without express user approval.
- Vagon Streams hosts a **packaged application**; it is NOT a substitute for a remote Windows build machine.
- Follow official Vagon upload instructions: build folder ZIP including required dependencies with main .exe in archive root. Vagon configures TURN/WebRTC once compatible package is uploaded and streaming enabled.

## Build prerequisites
1. Determine which current ODYSSEY branch/worktree/assets are authoritative. Avoid presenting skeleton code as a finished playable game.
2. Acquire legitimately licensed Unreal Engine 5.8.4-compatible build environment on a **separate Windows build host**, if no suitable Windows package exists.
3. Confirm the exact `.uproject`, required assets/maps, plugins (PixelStreaming2), and Build/ Cook/ Package target. Validate a launchable Windows package on remote compatible hardware.
4. Upload the packaged ZIP via user's authenticated Vagon Streams dashboard. Do not request or print password/secret tokens.
5. Set cursor controls appropriate to actual gameplay, session duration limits, idle auto-off and regional placement. Start test sessions only after explicit paid-resource approval.
6. Test WebRTC outside build-host network, video/audio, keyboard/mouse, controls, appropriate mobile fallback, startup latency and resource limits.
7. Share live URL only after actual verification.

## Site integration
Edit `judges-site/content.json` in the **`deploy/judges`** branch, not main. Put the verified HTTPS URL into `liveDemoUrl` only after tested. Set `videoUrl` to a real 30-second demo if available. Render redeploys on branch commits. Preserve the current public site in case the stream fails.

## Alternative
Arcware Cloud has a free 15-day / 60-min trial and a 10GB package size limit; plugin and Unreal engine version support must be verified. https://www.arcware.com/pricing

## Current blocker
A verified playable Windows package, compatible GPU-stream provider account, provider confirmation for UE 5.8.4 / Pixel Streaming 2, and budget approval for paid resources.
