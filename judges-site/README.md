# ODYSSEY — Judges website

This is a static educational project overview, NOT a live Unreal Pixel Streaming session.

- Public branch: `deploy/judges`
- Baseline snapshot: `release/baseline-2026-11-14`
- Main project: untouched by website deployment

## Updating demo media

Edit `judges-site/content.json`. Add a real HTTPS video link to `videoUrl`, or add a verified cloud-streaming URL to `liveDemoUrl`. Do not use placeholder URLs. After a validated commit to `deploy/judges`, Render automatically redeploys the site.

The two engineering choice responses are simplified representations of the existing Earth Command design document; no Unreal runtime is invoked.

## Checking locally

Run `python3 scripts/validate.py` from the repository root.

## Production security

Do not commit tokens, credentials, database contents, or private judge invitations. No backend or admin console is exposed by this static site. The separate Unreal package and GPU streaming service must be secured and tested before publishing a playable link.
