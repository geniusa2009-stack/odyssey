'use strict';

/**
 * middleware/rateLimiter.js
 *
 * Identity-keyed rate limiting (ported from the AgriSmart identity
 * service). Each limiter is keyed by the most specific VERIFIED identity
 * available — never blanket IP where a better identity exists — so
 * players behind one school / campus NAT are not throttled together:
 *
 *   - publicApiLimiter: normalized IP (no identity exists pre-auth)
 *   - authLimiter:      normalized IP + claimed account identifier
 *   - authAccountFailureLimiter / authIpFailureLimiter: failed sign-ins only
 *   - saveLimiter:      authenticated player id (profile / cloud-save writes)
 *
 * Built through one createLimiter() factory with the in-memory store —
 * correct for a single instance; a shared store (e.g. Redis) is a one-line
 * change in the factory.
 */

const rateLimit = require('express-rate-limit');
const net = require('net');
const config = require('../config');
const { ApiError, ErrorCodes } = require('./errorHandler');

/**
 * Normalizes an IP for rate-limit keying. IPv4 addresses are used
 * as-is. IPv6 addresses are masked to their first 4 hextets (/64, the
 * standard "one customer" delegation size) so a client rotating through
 * its own delegated range still shares one bucket instead of evading
 * the limiter by requesting a fresh address per request (Stage 1
 * finding B2 fix).
 * @param {string} ip
 * @returns {string}
 */
function normalizeIp(ip) {
  if (!ip) return 'unknown';
  if (net.isIPv4(ip)) return ip;

  if (net.isIPv6(ip)) {
    // Strip a possible IPv4-mapped prefix and take the first 4 groups.
    const expanded = ip.replace('::ffff:', '');
    const groups = expanded.split(':').filter(Boolean);
    return `${groups.slice(0, 4).join(':')}::/64`;
  }

  return ip;
}

function ipKey(req) {
  return normalizeIp(req.ip);
}

function authKey(req) {
  const identifier =
    (req.body && (req.body.email || req.body.phone)) || 'unknown-identifier';
  return `${ipKey(req)}:${String(identifier).toLowerCase()}`;
}

/**
 * Keyed by the AUTHENTICATED player id only (never IP, never anything from
 * req.body) — every route these limiters guard runs after `authenticate`.
 */
function userKey(req) {
  return req.user ? `user:${req.user.id}` : `ip:${ipKey(req)}`;
}

function rateLimitExceededHandler(req, res, next) {
  next(
    new ApiError(429, 'Too many requests. Please slow down and try again shortly.', {
      code: ErrorCodes.RATE_LIMITED,
      details: {
        retryAfterSeconds: Math.ceil(
          (req.rateLimit && req.rateLimit.resetTime
            ? (req.rateLimit.resetTime.getTime() - Date.now()) / 1000
            : 60)
        ),
      },
    })
  );
}

/**
 * Factory so every limiter shares handler/header behavior and so the
 * backing store can be swapped in one place later.
 */
function createLimiter({ windowMs, max, keyGenerator, skipSuccessfulRequests = false }) {
  return rateLimit({
    windowMs,
    max,
    // true = only responses with status >= 400 count (failed sign-ins).
    skipSuccessfulRequests,
    standardHeaders: true,
    legacyHeaders: false,
    keyGenerator,
    handler: rateLimitExceededHandler,
    // express-rate-limit v7 validates req.ip shape only inside its OWN
    // default key generator; supplying a custom one (as we do here)
    // bypasses that check, which is exactly why we run every custom key
    // generator through normalizeIp()/req.user rather than
    // trusting req.ip verbatim (Stage 1 finding B2).
  });
}

const publicApiLimiter = createLimiter({ ...config.rateLimit.api, keyGenerator: ipKey });
const authLimiter = createLimiter({ ...config.rateLimit.auth, keyGenerator: authKey });
const saveLimiter = createLimiter({ ...config.rateLimit.save, keyGenerator: userKey });

// Failed-attempt limiters (successful requests are not counted):
//   - authAccountFailureLimiter: per claimed account, across ALL IPs —
//     distributed guessing against one account;
//   - authIpFailureLimiter: per IP, across ALL accounts — password
//     spraying that rotates emails to dodge authLimiter's IP+email key;
function accountKey(req) {
  const identifier = (req.body && (req.body.email || req.body.phone)) || 'unknown-identifier';
  return `acct:${String(identifier).toLowerCase()}`;
}
const authAccountFailureLimiter = createLimiter({
  ...config.rateLimit.authAccountFailures,
  keyGenerator: accountKey,
  skipSuccessfulRequests: true,
});
const authIpFailureLimiter = createLimiter({
  ...config.rateLimit.authIpFailures,
  keyGenerator: (req) => `authip:${ipKey(req)}`,
  skipSuccessfulRequests: true,
});
module.exports = {
  authAccountFailureLimiter,
  authIpFailureLimiter,
  publicApiLimiter,
  authLimiter,
  saveLimiter,
  normalizeIp, // exported for unit testing
};
