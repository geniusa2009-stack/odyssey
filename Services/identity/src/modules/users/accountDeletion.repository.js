'use strict';

/**
 * modules/users/accountDeletion.repository.js
 *
 * Every database operation account deletion needs, in one place. Each
 * function is idempotent: re-running after a crash finds nothing left to
 * do, so accountDeletion.service.js can re-run the whole sequence for an
 * account whose deletion was interrupted.
 *
 * ODYSSEY retains NOTHING tied to a deleted account: profile, avatar,
 * settings, progression, missions, discoveries, unlocks, every cloud save,
 * every refresh-token record and finally the user document are deleted (not
 * anonymised, not flagged). See Docs/GooglePlay/ACCOUNT_DELETION.md.
 */

const mongoose = require('mongoose');
const User = require('./user.model');
const RefreshToken = require('../auth/refreshToken.model');
const { PlayerProfile, CloudSave } = require('../players/player.models');

const oid = (id) => new mongoose.Types.ObjectId(String(id));

async function findUser(userId) {
  return User.findById(userId).select('+passwordHash');
}

async function findUserByEmail(email) {
  return User.findOne({ email: String(email).toLowerCase() }).select('+passwordHash');
}

async function countActiveAdmins() {
  return User.countDocuments({ role: 'admin', isActive: true, deletionRequestedAt: null });
}

/** Step 1: lock the account — no sign-in, no refresh, no live access token. */
async function lockAccount(userId, now) {
  await User.updateOne({ _id: userId }, { $set: { isActive: false, tokensValidAfter: now } });
  // Keep the first request time on a re-run.
  await User.updateOne({ _id: userId, deletionRequestedAt: null }, { $set: { deletionRequestedAt: now } });
  await RefreshToken.updateMany({ userId, revokedAt: null }, { $set: { revokedAt: now } });
}

async function listUsersPendingDeletion(limit = 50) {
  return User.find({ deletionRequestedAt: { $ne: null } }).select('_id').limit(limit).lean();
}

/** All ODYSSEY player data: profile (avatar, settings, progression, missions, discoveries, unlocks) + cloud saves. */
async function deletePlayerData(userId) {
  const saves = await CloudSave.deleteMany({ userId: oid(userId) });
  const profiles = await PlayerProfile.deleteMany({ userId: oid(userId) });
  return { saves: saves.deletedCount, profiles: profiles.deletedCount };
}

/** Last step: the session records and the user document itself. */
async function deleteUser(userId) {
  await RefreshToken.deleteMany({ userId: oid(userId) });
  await User.deleteOne({ _id: oid(userId) });
}

module.exports = {
  findUser,
  findUserByEmail,
  countActiveAdmins,
  lockAccount,
  listUsersPendingDeletion,
  deletePlayerData,
  deleteUser,
};
