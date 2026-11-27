'use strict';

/**
 * observability/httpLogger.js
 *
 * Replaces morgan with pino-http (Stage 2 section 19 dependency swap):
 * one structured logger for both application and access logs, with
 * requestId/correlationId automatically bound to every access log line
 * via the same logger instance.
 */

const pinoHttp = require('pino-http');
const logger = require('./logger');
const { redactRequestForLog } = require('../security/redaction');

// Query parameters that carry credentials or signatures. Applied AFTER the
// redaction serializer (security/redaction.js) as a second layer.
const SECRET_QUERY_KEYS = new Set([
  'hmac', 'signature', 'sig', 'token', 'access_token', 'refresh_token', 'id_token',
  'api_key', 'apikey', 'key', 'password', 'secret', 'email',
]);

function safeDecode(v) {
  try {
    return decodeURIComponent(v);
  } catch {
    return v; // malformed %-escapes come from the client: never throw in the logger
  }
}

function maskSecretQuery(serialized) {
  if (!serialized || typeof serialized !== 'object') return serialized;
  const out = { ...serialized };
  if (typeof out.url === 'string' && out.url.includes('?')) {
    const [path, qs] = out.url.split(/\?(.*)/s, 2);
    out.url = `${path}?${qs
      .split('&')
      .map((pair) => {
        const [k] = pair.split('=');
        return SECRET_QUERY_KEYS.has(safeDecode(k || '').toLowerCase()) ? `${k}=[REDACTED]` : pair;
      })
      .join('&')}`;
  }
  if (out.query && typeof out.query === 'object') {
    out.query = Object.fromEntries(
      Object.entries(out.query).map(([k, v]) => [k, SECRET_QUERY_KEYS.has(k.toLowerCase()) ? '[REDACTED]' : v])
    );
  }
  return out;
}

const httpLogger = pinoHttp({
  logger,
  genReqId: (req) => req.id,
  customLogLevel: (req, res, err) => {
    if (err || res.statusCode >= 500) return 'error';
    if (res.statusCode >= 400) return 'warn';
    return 'info';
  },
  // Skip both health endpoints — Stage 1 finding C2 fix (was only
  // skipping /health/live, leaving /health/ready to flood logs under
  // frequent orchestrator polling).
  autoLogging: {
    ignore: (req) => req.url.startsWith('/health'),
  },
  customProps: (req) => ({
    correlationId: req.correlationId,
  }),
  // Tokens / credentials / e-mails in URLs never reach the access log.
  serializers: {
    req: (req) => maskSecretQuery(redactRequestForLog(req)),
  },
});

module.exports = httpLogger;
module.exports.maskSecretQuery = maskSecretQuery;
