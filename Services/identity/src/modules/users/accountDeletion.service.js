'use strict';

/**
 * modules/users/accountDeletion.service.js
 *
 * Deletes an account at the owner's request (Google Play account-deletion
 * requirement). Not a soft flag: the user document and ALL ODYSSEY data
 * linked to it (profile, avatar, settings, progression, missions,
 * discoveries, unlocks, cloud saves, sessions) are removed; nothing is
 * retained (see accountDeletion.repository.js and
 * Docs/GooglePlay/ACCOUNT_DELETION.md).
 *
 * Order of work:
 *   1. re-authenticate with the password, and an explicit confirmation;
 *   2. lock the account (no sign-in, refresh tokens revoked, live access
 *      tokens rejected by middleware/authenticate.js);
 *   3. idempotent delete/anonymise steps;
 *   4. delete the user document last.
 * MongoDB may be standalone (no multi-document transactions), so a crash
 * between steps leaves a locked account with `deletionRequestedAt` set;
 * finishPendingDeletions() re-runs the steps for it.
 */

const repo = require('./accountDeletion.repository');
const passwordSecurity = require('../../security/password');
const { ApiError } = require('../../middleware/errorHandler');
const logger = require('../../observability/logger');
const metrics = require('../../observability/metrics');

async function runSteps(userId) {
  const summary = {};
  summary.playerData = await repo.deletePlayerData(userId);
  await repo.deleteUser(userId);
  metrics.increment('accounts_deleted_total');
  return { completed: true, summary };
}

async function verifyAndLock(user, password, now) {
  // Same message for "no account" and "wrong password" (no enumeration).
  const ok = user && user.isActive && !user.deletionRequestedAt
    ? await passwordSecurity.verify(password, user.passwordHash)
    : false;
  if (!ok) throw ApiError.unauthorized('Invalid email or password.');
  if (user.role === 'admin' && (await repo.countActiveAdmins()) <= 1) {
    throw ApiError.conflict('The last admin account cannot be deleted.', { code: 'LAST_ADMIN' });
  }
  await repo.lockAccount(user._id, now);
}

/** Signed-in deletion: DELETE /users/me. */
async function deleteOwnAccount(userId, { password }, { now = new Date() } = {}) {
  const user = await repo.findUser(userId);
  await verifyAndLock(user, password, now);
  const result = await runSteps(user._id);
  logger.info({ event: 'account_deleted', completed: result.completed }, 'account deletion processed');
  return { deleted: result.completed, pending: !result.completed };
}

/** Deletion from the public web page, without the app: POST /auth/delete-account. */
async function deleteAccountWithCredentials({ email, password }, { now = new Date() } = {}) {
  const user = await repo.findUserByEmail(email);
  await verifyAndLock(user, password, now);
  const result = await runSteps(user._id);
  logger.info({ event: 'account_deleted', via: 'web', completed: result.completed }, 'account deletion processed');
  return { deleted: result.completed, pending: !result.completed };
}

/** Resume deletions interrupted by a crash. */
async function finishPendingDeletions({ limit = 50 } = {}) {
  const pending = await repo.listUsersPendingDeletion(limit);
  let completed = 0;
  for (const u of pending) {
    try {
      const r = await runSteps(u._id);
      if (r.completed) completed += 1;
    } catch (err) {
      logger.error({ err: { message: err.message } }, 'resuming account deletion failed');
    }
  }
  return { pending: pending.length, completed };
}

module.exports = { deleteOwnAccount, deleteAccountWithCredentials, finishPendingDeletions };
