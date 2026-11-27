'use strict';

/**
 * modules/users/user.model.js
 *
 * Schema + indexes only — no business logic (Stage 2 section 3: models
 * must not orchestrate workflows). Password is always stored as a
 * bcrypt hash (see security/password.js); `passwordHash` is excluded
 * from default query projections (`select: false`) so a forgotten
 * `.lean()`/serialization step can't accidentally leak it.
 */

const mongoose = require('mongoose');
const { ROLES } = require('../../security/rbac');

const userSchema = new mongoose.Schema(
  {
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    passwordHash: {
      type: String,
      required: true,
      select: false,
    },
    // Player callsign (2-32 chars). Not unique: the stable identity is _id.
    displayName: {
      type: String,
      required: true,
      trim: true,
      minlength: 2,
      maxlength: 32,
    },
    role: {
      type: String,
      enum: Object.values(ROLES),
      default: ROLES.PLAYER,
      required: true,
    },
    isActive: {
      type: Boolean,
      default: true,
    },
    // Access tokens issued (iat) before this instant are rejected by
    // middleware/authenticate.js. Set by logout-all and account
    // deletion so a stolen 15-minute access token dies with the session.
    tokensValidAfter: {
      type: Date,
      default: null,
    },
    // Set when the owner asks to delete the account. The account is
    // locked immediately; if the deletion is interrupted it is resumed
    // by `npm run accounts:finish-deletions` (accountDeletion.service.js).
    deletionRequestedAt: {
      type: Date,
      default: null,
      index: { sparse: true },
    },
  },
  { timestamps: true }
);


module.exports = mongoose.model('User', userSchema);
