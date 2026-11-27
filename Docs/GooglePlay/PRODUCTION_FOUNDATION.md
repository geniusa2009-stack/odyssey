# ODYSSEY production line: technical foundation

Branch: `feature/google-play-production`, based on `59570273bd79d709f8f02600e2fe1e877a0ba97d`. This is a separate product from the judge builds: the judge releases, tags and assets are never changed.

## Engine / API 36 decision
**UE 5.8.4 targets Android 16 (API 36) cleanly, with no engine upgrade and no manifest workaround.**

The evidence:
- **Engine requirements:** the engine's `Engine/Config/Android/Android_SDK.json` declares platform `android-36`, build-tools `36.0.0` and NDK `r27c`.
- **Engine defaults:** `BaseEngine.ini` defaults to `TargetSDKVersion=36` and `MinSDKVersion=26`.
- **Shipped builds:** the judge APKs built with this toolchain report `targetSdkVersion=36` and `compileSdkVersion=36` (Android 16), with `minSdkVersion=26`. That comes from `aapt2 dump badging` and the compiled manifest.

**Toolchain:** UE 5.8.4 source build, Android SDK platform 36, build-tools 36.0.0, CMake 3.22.1, NDK 27.2.12479018 (r27c), JDK 17. It's the same toolchain as the judge builds; nothing about them changes.

## Production identity
| | Value |
|---|---|
| Package | `com.odyssey.space`. Availability can only be confirmed in Play Console when the app is created. |
| Version | `1.0.0`, versionCode `10000` (versionCode = major·10000 + minor·100 + patch) |
| Output | Android App Bundle (`bEnableBundle=True`), ARM64 only, with ABI, density and language splits. A universal APK is kept for local testing only. |
| Asset delivery | Content in the base module for now, with no legacy OBB. Play Asset Delivery is decided against the measured bundle size (Play's base-module download limit). |
| Signing | A production upload key, separate from the judge debug key and stored outside the repo, with Google Play App Signing |

## Accounts
The `Services/identity` service is ported from the AgriSmart identity system. It has no Firebase dependency.
- **Sign-in:** e-mail/password registration and sign-in, with bcrypt password hashes (never plaintext).
- **Tokens:** HS256 JWT access tokens (15 minutes, pinned issuer and audience), plus opaque, SHA-256-hashed refresh tokens. Refresh tokens rotate on every use; reuse is detected and revokes the whole token family.
- **Sessions:**
  - Logout and logout-all.
  - Session invalidation via `tokensValidAfter`.
  - Roles and account state are read from the database on every request.
- **Abuse protection:** identity-keyed rate limits, with failed-attempt limiters per account and per IP.
- **Roles:** `player`, the only self-service role; `moderator` and `admin` are created out-of-band.
- **Player data:** a player profile (avatar, settings, progression, missions, discoveries, unlocks) and up to 3 cloud-save slots. Both use revision-based conflict detection, so a newer save is never silently overwritten.
- **Account deletion:** in-game and on a public web page. See `ACCOUNT_DELETION.md`.
- **Guests:** "Continue as Guest" keeps everything on the device, with no server account.
- **Tests:** 50 ported and adapted security tests pass (`npm test` in `Services/identity`).
