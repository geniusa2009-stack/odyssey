'use strict';

/**
 * middleware/authorizeRole.js — runs after authenticate(); req.user.role was
 * read from the database on this request (never trusted from the token).
 */

const { ApiError } = require('./errorHandler');
const { hasRole } = require('../security/rbac');

function authorizeRole(...allowedRoles) {
  return function authorizeRoleMiddleware(req, res, next) {
    if (!req.user || !hasRole(req.user.role, allowedRoles)) {
      return next(ApiError.forbidden('You do not have permission to do this.'));
    }
    return next();
  };
}

module.exports = authorizeRole;
