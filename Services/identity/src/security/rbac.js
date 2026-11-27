'use strict';

/**
 * security/rbac.js
 *
 * ODYSSEY role table. Pure logic, no HTTP/DB access.
 *
 *   player    — every self-registered account (the only self-service role)
 *   moderator — staff: reviews reports; NOT ranked above admin and never
 *               satisfies an isAtLeast(..., ADMIN) check
 *   admin     — staff: operational administration
 *
 * Roles are read from the database on every request (middleware/
 * authenticate.js); a role carried in a token is never trusted on its own.
 */

const ROLES = Object.freeze({
  PLAYER: 'player',
  MODERATOR: 'moderator',
  ADMIN: 'admin',
});

const ROLE_HIERARCHY = Object.freeze({
  [ROLES.PLAYER]: 0,
  [ROLES.ADMIN]: 2,
});

/**
 * @param {string} role
 * @param {string[]} allowedRoles
 * @returns {boolean}
 */
function hasRole(role, allowedRoles) {
  return allowedRoles.includes(role);
}

/** True if `role` is at least as privileged as `minimumRole` (moderator is unranked). */
function isAtLeast(role, minimumRole) {
  const roleRank = ROLE_HIERARCHY[role];
  const minimumRank = ROLE_HIERARCHY[minimumRole];
  if (roleRank === undefined || minimumRank === undefined) return false;
  return roleRank >= minimumRank;
}

/** Ownership check: a player may only touch their own records. */
function isOwner(userId, ownerId) {
  return Boolean(userId) && Boolean(ownerId) && String(userId) === String(ownerId);
}

module.exports = { ROLES, ROLE_HIERARCHY, hasRole, isAtLeast, isOwner };
