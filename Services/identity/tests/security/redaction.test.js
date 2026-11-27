'use strict';

/**
 * Log redaction: credentials, tokens and e-mail addresses never reach logs —
 * neither through structured fields (logger redact paths) nor through URLs.
 */

const { PassThrough } = require('stream');
const pino = require('pino');
const { redactUrl, redactRequestForLog } = require('../../src/security/redaction');

describe('structured log fields', () => {
  test('password, token, refreshToken and email fields are masked', (done) => {
    const stream = new PassThrough();
    // Same redact paths as src/observability/logger.js (which is disabled under NODE_ENV=test).
    const logger = pino(
      { redact: { paths: ['password', 'token', 'refreshToken', 'email', '*.password', '*.email'], censor: '[REDACTED]' } },
      stream
    );
    let raw = '';
    stream.on('data', (c) => { raw += c.toString(); });
    stream.on('end', () => {
      const line = JSON.parse(raw.trim());
      expect(line.password).toBe('[REDACTED]');
      expect(line.token).toBe('[REDACTED]');
      expect(line.refreshToken).toBe('[REDACTED]');
      expect(line.email).toBe('[REDACTED]');
      expect(line.user.email).toBe('[REDACTED]');
      expect(raw).not.toContain('super-secret');
      expect(raw).not.toContain('player@example.com');
      done();
    });
    logger.info({
      password: 'super-secret-password',
      token: 'super-secret-token',
      refreshToken: 'super-secret-refresh',
      email: 'player@example.com',
      user: { email: 'player@example.com' },
    });
    stream.end();
  });
});

describe('URLs', () => {
  test('credential query values and token-like path segments are masked', () => {
    const jwtLike = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXNpZ25hdHVyZQ';
    expect(redactUrl('/api/v1/auth/refresh?refresh_token=abc&id=7')).toBe('/api/v1/auth/refresh?refresh_token=[REDACTED]&id=7');
    expect(redactUrl(`/x/${jwtLike}`)).toBe('/x/[REDACTED]');
    expect(redactUrl('/x/player@example.com')).toBe('/x/[REDACTED]');
    expect(redactUrl('/api/v1/players/me/saves/0')).toBe('/api/v1/players/me/saves/0');
  });
  test('serialized requests have url/query redacted', () => {
    const out = redactRequestForLog({ url: '/a?password=p', query: { password: 'p', page: '1' } });
    expect(out.url).toBe('/a?password=[REDACTED]');
    expect(out.query).toEqual({ password: '[REDACTED]', page: '1' });
  });
});
