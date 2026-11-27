'use strict';

/**
 * modules/players/players.service.js
 *
 * Player profile + cloud saves for the authenticated account only (the
 * user id always comes from the verified token, never from the request).
 *
 * Conflict policy (never destroy a newer save silently):
 *   every write names the revision it was based on; the update is a single
 *   compare-and-set on (userId, slot, revision). If the server copy has moved
 *   on, nothing is written and 409 SAVE_CONFLICT returns the server copy's
 *   metadata so the client can show both versions and let the player choose.
 *   Choosing "keep this device" re-submits with the server's revision as base —
 *   an explicit, informed overwrite.
 */

const crypto = require('crypto');
const mongoose = require('mongoose');
const { PlayerProfile, CloudSave } = require('./player.models');
const config = require('../../config');
const metrics = require('../../observability/metrics');
const { ApiError, ErrorCodes } = require('../../middleware/errorHandler');

const oid = (id) => new mongoose.Types.ObjectId(String(id));

function serializeProfile(p) {
  return {
    revision: p.revision,
    avatar: p.avatar || {},
    settings: p.settings || {},
    progression: p.progression || {},
    missions: p.missions || [],
    discoveries: p.discoveries || [],
    unlocks: p.unlocks || [],
    updatedAt: p.updatedAt,
  };
}

function saveMeta(s) {
  return {
    slot: s.slot,
    revision: s.revision,
    sizeBytes: s.sizeBytes,
    sha256: s.sha256,
    clientSavedAt: s.clientSavedAt,
    deviceLabel: s.deviceLabel,
    gameVersion: s.gameVersion,
    updatedAt: s.updatedAt,
  };
}

function conflict(message, server) {
  metrics.increment('save_conflicts_total');
  return new ApiError(409, message, { code: ErrorCodes.SAVE_CONFLICT, details: { server } });
}

/** Returns the profile, creating an empty one on first access. */
async function getProfile(userId) {
  const p = await PlayerProfile.findOneAndUpdate(
    { userId: oid(userId) },
    { $setOnInsert: { userId: oid(userId), revision: 1 } },
    { new: true, upsert: true }
  ).lean();
  return serializeProfile(p);
}

async function updateProfile(userId, { baseRevision, ...fields }) {
  await getProfile(userId); // ensure it exists
  const updated = await PlayerProfile.findOneAndUpdate(
    { userId: oid(userId), revision: baseRevision },
    { $set: fields, $inc: { revision: 1 } },
    { new: true }
  ).lean();
  if (!updated) {
    const server = await PlayerProfile.findOne({ userId: oid(userId) }).lean();
    throw conflict('Profile was changed on another device.', serializeProfile(server));
  }
  return serializeProfile(updated);
}

async function listSaves(userId) {
  const saves = await CloudSave.find({ userId: oid(userId) }).sort({ slot: 1 }).lean();
  return saves.map(saveMeta);
}

async function getSave(userId, slot) {
  const s = await CloudSave.findOne({ userId: oid(userId), slot }).lean();
  if (!s) throw ApiError.notFound('No save in this slot.');
  return { ...saveMeta(s), payload: s.payload };
}

async function putSave(userId, slot, { baseRevision, payload, clientSavedAt, deviceLabel = '', gameVersion = '' }) {
  if (slot >= config.saves.maxSlots) {
    throw ApiError.badRequest(`Save slot must be below ${config.saves.maxSlots}.`);
  }
  const sizeBytes = Buffer.byteLength(payload, 'utf8');
  if (sizeBytes > config.saves.maxBytes) {
    throw new ApiError(413, 'Save is too large.', { code: ErrorCodes.SAVE_TOO_LARGE });
  }
  try {
    JSON.parse(payload);
  } catch {
    throw ApiError.badRequest('Save payload must be JSON.');
  }
  const doc = {
    payload,
    sizeBytes,
    sha256: crypto.createHash('sha256').update(payload).digest('hex'),
    clientSavedAt: new Date(clientSavedAt),
    deviceLabel,
    gameVersion,
  };

  if (baseRevision === 0) {
    // First save in this slot: insert-only. The unique (userId, slot) index
    // makes a concurrent first save from another device a conflict, not an overwrite.
    try {
      const created = await CloudSave.create({ userId: oid(userId), slot, revision: 1, ...doc });
      return saveMeta(created);
    } catch (err) {
      if (err && err.code === 11000) {
        const server = await CloudSave.findOne({ userId: oid(userId), slot }).lean();
        throw conflict('A save already exists in this slot.', saveMeta(server));
      }
      throw err;
    }
  }

  const updated = await CloudSave.findOneAndUpdate(
    { userId: oid(userId), slot, revision: baseRevision },
    { $set: doc, $inc: { revision: 1 } },
    { new: true }
  ).lean();
  if (!updated) {
    const server = await CloudSave.findOne({ userId: oid(userId), slot }).lean();
    if (!server) throw conflict('The save in this slot was deleted on another device.', null);
    throw conflict('A newer save exists on the server.', saveMeta(server));
  }
  return saveMeta(updated);
}

async function deleteSave(userId, slot) {
  const r = await CloudSave.deleteOne({ userId: oid(userId), slot });
  if (!r.deletedCount) throw ApiError.notFound('No save in this slot.');
}

module.exports = { getProfile, updateProfile, listSaves, getSave, putSave, deleteSave };
