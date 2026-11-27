'use strict';

/**
 * middleware/authenticate.js
 *
 * Verifies a user access JWT and attaches `req.user = { id, role }`.
 *
 * The JWT proves who the caller is; the ROLE and ACCOUNT STATE come from
 * the database on every request (one indexed _id lookup). A role carried
 * in the token is never trusted on its own, so demoting, deactivating or
 * deleting an account takes effect on the next request instead of when
 * the 15-minute token expires. Tokens issued before the user's
 * `tokensValidAfter` (logout-all, account deletion) are rejected too.
 * The RBAC role check and ownership checks that follow are separate,
 * composable middleware (authorizeRole.js, authorizeOwnership.js).
 */

const jwt = require('jsonwebtoken');
const mongoose = require('mongoose');
const { verifyAccessToken } = require('../security/jwt');
const { ApiError, ErrorCodes } = require('./errorHandler');
const usersRepository = require('../modules/users/users.repository');

function invalid(message = 'Access token is invalid.') {
  return new ApiError(401, message, { code: ErrorCodes.AUTH_TOKEN_INVALID });
}

async function authenticate(req, res, next) {
  const header = req.headers.authorization || '';
  const [scheme, token] = header.split(' ');

  if (scheme !== 'Bearer' || !token) {
    return next(ApiError.unauthorized('Missing or malformed Authorization header.'));
  }

  let payload;
  try {
    payload = verifyAccessToken(token);
  } catch (err) {
    if (err instanceof jwt.TokenExpiredError) {
      return next(
        new ApiError(401, 'Access token has expired.', { code: ErrorCodes.AUTH_TOKEN_EXPIRED })
      );
    }
    return next(invalid());
  }

  if (typeof payload.sub !== 'string' || !mongoose.isValidObjectId(payload.sub)) {
    return next(invalid());
  }

  try {
    const user = await usersRepository.findAuthState(payload.sub);
    if (!user || !user.isActive) return next(invalid('Account is no longer active.'));
    if (user.tokensValidAfter && payload.iat < Math.floor(user.tokensValidAfter.getTime() / 1000)) {
      return next(
        new ApiError(401, 'Session has been signed out.', { code: ErrorCodes.AUTH_TOKEN_EXPIRED })
      );
    }
    req.user = { id: payload.sub, role: user.role };
    return next();
  } catch (err) {
    return next(err);
  }
}

module.exports = authenticate;
