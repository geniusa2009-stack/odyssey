'use strict';

/**
 * modules/players/player.models.js
 *
 * ODYSSEY player data owned by one account. Schemas + indexes only.
 *
 * PlayerProfile — one per account: avatar / character configuration, settings,
 *   progression, mission progress, discoveries, unlocks. `revision` implements
 *   optimistic concurrency: a write must name the revision it was based on.
 * CloudSave — up to SAVE_MAX_SLOTS per account; an opaque game save written by
 *   the client (JSON), stored with its SHA-256 and the same revision rule, so a
 *   newer save on the server is never silently overwritten by an older device.
 *
 * Both are deleted with the account (modules/users/accountDeletion.repository.js).
 */

const mongoose = require('mongoose');

const playerProfileSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, unique: true },
    revision: { type: Number, required: true, default: 1 },
    avatar: { type: mongoose.Schema.Types.Mixed, default: {} },
    settings: { type: mongoose.Schema.Types.Mixed, default: {} },
    progression: { type: mongoose.Schema.Types.Mixed, default: {} },
    missions: { type: [mongoose.Schema.Types.Mixed], default: [] },
    discoveries: { type: [String], default: [] },
    unlocks: { type: [String], default: [] },
  },
  { timestamps: true, minimize: false }
);

const cloudSaveSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    slot: { type: Number, required: true, min: 0 },
    revision: { type: Number, required: true, default: 1 },
    payload: { type: String, required: true }, // JSON text produced by the game client
    sizeBytes: { type: Number, required: true },
    sha256: { type: String, required: true },
    clientSavedAt: { type: Date, required: true },
    deviceLabel: { type: String, default: '' }, // e.g. "Android" — never a hardware identifier
    gameVersion: { type: String, default: '' },
  },
  { timestamps: true }
);
cloudSaveSchema.index({ userId: 1, slot: 1 }, { unique: true });

const PlayerProfile = mongoose.model('PlayerProfile', playerProfileSchema);
const CloudSave = mongoose.model('CloudSave', cloudSaveSchema);

module.exports = { PlayerProfile, CloudSave };
