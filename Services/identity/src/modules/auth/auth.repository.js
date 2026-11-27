'use strict';

const RefreshToken = require('./refreshToken.model');

async function createRefreshToken({ userId, tokenHash, familyId, userAgent, expiresAt }) {
  return RefreshToken.create({ userId, tokenHash, familyId, userAgent, expiresAt });
}

async function findByTokenHash(tokenHash) {
  return RefreshToken.findOne({ tokenHash });
}

// Compare-and-set: only the first caller rotates a given token. A
// second concurrent refresh with the same token gets null and is
// treated as reuse (see auth.service.js refresh()).
async function markRotated(id) {
  return RefreshToken.findOneAndUpdate(
    { _id: id, rotatedAt: null, revokedAt: null },
    { rotatedAt: new Date() },
    { new: true }
  );
}

async function revokeFamily(familyId) {
  return RefreshToken.updateMany({ familyId, revokedAt: null }, { revokedAt: new Date() });
}

async function revokeAllForUser(userId) {
  return RefreshToken.updateMany({ userId, revokedAt: null }, { revokedAt: new Date() });
}

module.exports = {
  createRefreshToken,
  findByTokenHash,
  markRotated,
  revokeFamily,
  revokeAllForUser,
};
