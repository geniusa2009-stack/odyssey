# ODYSSEY account deletion (Google Play)

**Two ways to delete an account:**
- **In the game:** Settings → Account → Delete Account (`DELETE /api/v1/users/me`).
- **On the web, without the app:** the public page `<identity-host>/account/delete` (`POST /api/v1/auth/delete-account`). This is the URL to enter in Play Console.

**What the player must provide:**
- In the game: their password and the typed word `DELETE`.
- On the web: their e-mail, password and the typed word `DELETE`.

A wrong password and an unknown e-mail get the same answer, so the page doesn't reveal whether an account exists. Requests are rate-limited per IP and per account.

## What is deleted
Deletion is real; nothing is just disabled or flagged.

| Data | What happens | Where in the code |
|---|---|---|
| Account: e-mail, display name, bcrypt password hash, role | Deleted | `User` |
| Character / avatar configuration | Deleted | `PlayerProfile.avatar` |
| Settings, progression, mission progress, discoveries, unlocks | Deleted | `PlayerProfile` |
| Every cloud save | Deleted | `CloudSave` |
| Sessions: refresh-token hashes | Revoked at once, then deleted | `RefreshToken` |
| Access tokens already issued | Rejected at once | `tokensValidAfter` + `isActive=false` |

**Nothing is retained.** ODYSSEY has no payments, no social content and no third-party analytics, so no record needs to be kept. Operational logs never contain passwords, tokens or e-mail addresses: they're redacted in `observability/logger.js` and `security/redaction.js`.

**Guests:** guest players have no server account. Their progress exists only on the device and is removed by uninstalling the game.

## How it works
1. **Re-authenticate and confirm:** the player gives their password and the typed `DELETE`.
2. **Lock the account:** sign-in is blocked, every refresh token is revoked, and access tokens issued earlier are rejected.
3. **Delete the data:** cloud saves and the player profile, then the refresh-token records, and the user document last.
4. **Recover from crashes:** if the process dies part-way, the account stays locked with `deletionRequestedAt` set. The service finishes the deletion within the hour (hourly in-process sweep), or you can run `npm run accounts:finish-deletions`.

**Tests:** `Services/identity/tests/security/accountDeletion.test.js` covers every row above, both flows, crash recovery, the last-admin guard and the page's CSP.
