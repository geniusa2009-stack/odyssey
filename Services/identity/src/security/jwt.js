'use strict';

/**
 * security/jwt.js
 *
 * Access-token sign/verify. Refresh tokens are deliberately NOT JWTs —
 * they're opaque random values whose HASH is stored server-side (see
 * modules/auth/auth.service.js), so they can be looked up, rotated, and
 * revoked. Access tokens ARE JWTs because they're short-lived and
 * stateless by design (Stage 2 section 6): 15 minutes bounds the blast
 * radius of a token that can't be revoked before it expires.
 */

const jwt = require('jsonwebtoken');
const config = require('../config');

/**
 * @param {{ sub: string, role: string }} payload
 * @returns {string}
 */
function signAccessToken(payload) {
  return jwt.sign(payload, config.jwt.accessSecret, {
    algorithm: 'HS256',
    expiresIn: config.jwt.accessTokenTtl,
    issuer: 'odyssey-identity',
    audience: 'odyssey-game',
  });
}

/**
 * @param {string} token
 * @returns {{ sub: string, role: string, iat: number, exp: number }}
 * @throws {jwt.JsonWebTokenError | jwt.TokenExpiredError}
 */
function verifyAccessToken(token) {
  // Pin the algorithm: only HS256 tokens signed with our secret are accepted.
  return jwt.verify(token, config.jwt.accessSecret, {
    issuer: 'odyssey-identity',
    audience: 'odyssey-game',
    algorithms: ['HS256'],
  });
}

module.exports = { signAccessToken, verifyAccessToken };
