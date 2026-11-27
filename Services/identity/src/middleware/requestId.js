'use strict';

/**
 * middleware/requestId.js
 *
 * Assigns a per-hop request ID and an end-to-end correlation ID to
 * every request (Stage 2 section 5G). `requestId` is always freshly
 * generated for this hop (echoed back via X-Request-Id). `correlationId`
 * is honored from an inbound `X-Correlation-Id` header when present
 * (letting a future mobile app / IoT gateway trace a call across
 * multiple internal hops) and generated if absent.
 */

const crypto = require('crypto');

// Client-supplied ids are echoed into response headers and every log
// line, so only short, plain tokens are honoured (no log forging with
// newlines/JSON, no oversized values). Anything else gets a fresh UUID.
const SAFE_ID = /^[A-Za-z0-9._:-]{1,64}$/;
function safeIncomingId(value) {
  return typeof value === 'string' && SAFE_ID.test(value.trim()) ? value.trim() : null;
}

function requestId(req, res, next) {
  req.id = safeIncomingId(req.headers['x-request-id']) || crypto.randomUUID();
  req.correlationId = safeIncomingId(req.headers['x-correlation-id']) || req.id;

  res.setHeader('X-Request-Id', req.id);
  res.setHeader('X-Correlation-Id', req.correlationId);
  next();
}

module.exports = requestId;
