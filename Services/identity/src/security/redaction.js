'use strict';

/**
 * security/redaction.js
 *
 * Log redaction for request URLs/queries (same interface as the AgriSmart
 * helper it replaces, minus payment-card logic — ODYSSEY has no payments).
 * Credentials must never reach logs even if a client mistakenly puts them in
 * a URL: values of credential-like query keys are masked, and path segments
 * that look like bearer/refresh tokens or e-mail addresses are masked too.
 * Field-level redaction of bodies/headers lives in observability/logger.js.
 */

const SECRET_KEYS = new Set([
  'token', 'access_token', 'accesstoken', 'refresh_token', 'refreshtoken', 'id_token', 'idtoken',
  'password', 'newpassword', 'currentpassword', 'secret', 'code', 'email', 'authorization',
]);

function safeDecode(text) {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

// JWT (three base64url parts), long opaque base64url tokens, or an e-mail address.
const TOKENISH = /^(?:[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|[A-Za-z0-9_-]{40,}|[^@\s/]+@[^@\s/]+\.[^@\s/]+)$/;

function redactSegment(segment) {
  return TOKENISH.test(safeDecode(segment)) ? '[REDACTED]' : segment;
}

/** URL with credential-like query values and token/e-mail path segments masked. */
function redactUrl(url) {
  if (typeof url !== 'string' || !url) return url;
  const q = url.indexOf('?');
  const pathPart = q === -1 ? url : url.slice(0, q);
  const path = pathPart.split('/').map(redactSegment).join('/');
  if (q === -1) return path;
  const query = url
    .slice(q + 1)
    .split('&')
    .map((pair) => {
      const eq = pair.indexOf('=');
      const key = eq === -1 ? pair : pair.slice(0, eq);
      const value = eq === -1 ? '' : pair.slice(eq + 1);
      if (SECRET_KEYS.has(safeDecode(key).toLowerCase())) return `${key}=[REDACTED]`;
      return eq === -1 ? redactSegment(pair) : `${key}=${redactSegment(value)}`;
    })
    .join('&');
  return `${path}?${query}`;
}

/** Deep copy of a parsed query/params object with credential-like values masked. */
function redactObject(node) {
  if (Array.isArray(node)) return node.map(redactObject);
  if (node && typeof node === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(node)) {
      out[k] = SECRET_KEYS.has(String(k).toLowerCase()) ? '[REDACTED]' : redactObject(v);
    }
    return out;
  }
  return typeof node === 'string' ? redactSegment(node) : node;
}

/** Serialized pino-http request with url/query/params redacted. */
function redactRequestForLog(serialized) {
  if (!serialized || typeof serialized !== 'object') return serialized;
  return {
    ...serialized,
    ...(serialized.url !== undefined ? { url: redactUrl(serialized.url) } : {}),
    ...(serialized.query !== undefined ? { query: redactObject(serialized.query) } : {}),
    ...(serialized.params !== undefined ? { params: redactObject(serialized.params) } : {}),
  };
}

module.exports = { redactUrl, redactObject, redactRequestForLog, SECRET_KEYS };
