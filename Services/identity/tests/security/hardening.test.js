'use strict';

/**
 * Identity-service hardening (ported from AgriSmart): failed-attempt
 * limiters, limiter wiring, strict avatar input (no links), safe request
 * ids, and secrets kept out of logs.
 */

const express = require('express');
const request = require('supertest');
const createApp = require('../../src/app');
const { maskSecretQuery } = require('../../src/observability/httpLogger');
const { loggableError } = require('../../src/middleware/errorHandler');
const limiters = require('../../src/middleware/rateLimiter');

const app = createApp();

/** Fresh limiter module with low thresholds, mounted in front of a stub handler. */
function limiterApp(env, pick, respond) {
  const saved = {};
  for (const [k, v] of Object.entries(env)) {
    saved[k] = process.env[k];
    process.env[k] = String(v);
  }
  let mod;
  try {
    jest.isolateModules(() => {
      mod = require('../../src/middleware/rateLimiter');
    });
  } finally {
    for (const k of Object.keys(env)) (saved[k] === undefined ? delete process.env[k] : (process.env[k] = saved[k]));
  }
  const a = express();
  a.use(express.json());
  a.post('/t', pick(mod), (req, res) => respond(req, res));
  a.use((err, req, res, _next) => res.status(err.statusCode || 500).json({ code: err.code }));
  return a;
}

describe('failed sign-in limiters', () => {
  test('per IP across accounts: password spraying is cut off', async () => {
    const a = limiterApp({ RATE_LIMIT_AUTH_IP_FAILURES_MAX: 3 }, (m) => m.authIpFailureLimiter, (req, res) => res.status(401).end());
    const codes = [];
    for (let i = 0; i < 5; i += 1) codes.push((await request(a).post('/t').send({ email: `victim${i}@example.com` })).status);
    expect(codes).toEqual([401, 401, 401, 429, 429]);
  });

  test('per account across IPs: guessing one account is cut off', async () => {
    const a = limiterApp({ RATE_LIMIT_AUTH_ACCOUNT_FAILURES_MAX: 2 }, (m) => m.authAccountFailureLimiter, (req, res) => res.status(401).end());
    const s = [];
    for (let i = 0; i < 3; i += 1) s.push((await request(a).post('/t').set('X-Forwarded-For', `10.0.0.${i}`).send({ email: 'Target@Example.com' })).status);
    expect(s).toEqual([401, 401, 429]);
    // Another account is unaffected.
    expect((await request(a).post('/t').send({ email: 'other@example.com' })).status).toBe(401);
  });

  test('successful sign-ins are not counted (players behind a shared school NAT are not throttled)', async () => {
    const a = limiterApp({ RATE_LIMIT_AUTH_IP_FAILURES_MAX: 2 }, (m) => m.authIpFailureLimiter, (req, res) => res.status(200).end());
    for (let i = 0; i < 6; i += 1) expect((await request(a).post('/t').send({ email: `u${i}@example.com` })).status).toBe(200);
  });

});

describe('limiter wiring on the real routes', () => {
  const stackOf = (router, path, method) =>
    router.stack.find((l) => l.route && l.route.path === path && l.route.methods[method]).route.stack.map((s) => s.handle);

  test('login and public account deletion run both failure limiters', () => {
    const auth = require('../../src/modules/auth/auth.routes');
    for (const path of ['/login', '/delete-account']) {
      const h = stackOf(auth, path, 'post');
      expect(h).toContain(limiters.authIpFailureLimiter);
      expect(h).toContain(limiters.authAccountFailureLimiter);
    }
  });

  test('profile and cloud-save writes are rate limited per player', () => {
    const players = require('../../src/modules/players/players.routes');
    expect(stackOf(players, '/me/profile', 'put')).toContain(limiters.saveLimiter);
    expect(stackOf(players, '/me/saves/:slot', 'put')).toContain(limiters.saveLimiter);
    expect(stackOf(players, '/me/saves/:slot', 'delete')).toContain(limiters.saveLimiter);
  });
});

describe('avatar input is a closed set of ids (no links, no extra fields)', () => {
  async function player() {
    const r = await request(app)
      .post('/api/v1/auth/register')
      .send({ email: `avatar-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`, password: 'CorrectHorseBattery1', displayName: 'Avatar' });
    return r.body.data.accessToken;
  }
  test.each([
    { hairStyle: 'javascript:alert(1)' },
    { hairColor: 'https://evil.example/x.png' },
    { avatarUrl: 'https://images.example.org/a.png' },
    { suitColor: 'a'.repeat(49) },
  ])('rejects %o', async (avatar) => {
    const token = await player();
    const res = await request(app).put('/api/v1/players/me/profile').set('Authorization', `Bearer ${token}`).send({ baseRevision: 1, avatar });
    expect(res.status).toBe(400);
  });
  test('accepts preset ids and hex colours', async () => {
    const token = await player();
    const res = await request(app)
      .put('/api/v1/players/me/profile')
      .set('Authorization', `Bearer ${token}`)
      .send({ baseRevision: 1, avatar: { facePreset: 'face_03', hairColor: '#3a6ea5', visorStyle: 'visor.gold' } });
    expect(res.status).toBe(200);
    expect(res.body.data.avatar.hairColor).toBe('#3a6ea5');
  });
});

describe('request ids', () => {
  test('a plain client id is echoed', async () => {
    const r = await request(app).get('/health/live').set('X-Request-Id', 'app-123.abc');
    expect(r.headers['x-request-id']).toBe('app-123.abc');
  });
  test.each(['a'.repeat(200), 'x"} {"level":60', 'id with spaces'])('an unsafe id is replaced: %s', async (id) => {
    const r = await request(app).get('/health/live').set('X-Request-Id', id).set('X-Correlation-Id', id);
    expect(r.headers['x-request-id']).toMatch(/^[0-9a-f-]{36}$/);
    expect(r.headers['x-correlation-id']).toBe(r.headers['x-request-id']);
  });
});

describe('secrets kept out of logs', () => {
  test('tokens and e-mails in the query string are masked', () => {
    const out = maskSecretQuery({
      url: '/api/v1/auth/refresh?refresh_token=abc&id=42&Email=a@b.co',
      query: { refresh_token: 'abc', id: '42', email: 'a@b.co' },
    });
    expect(out.url).toBe('/api/v1/auth/refresh?refresh_token=[REDACTED]&id=42&Email=[REDACTED]');
    expect(out.query).toEqual({ refresh_token: '[REDACTED]', id: '42', email: '[REDACTED]' });
  });
  test('malformed escapes never crash the logger', () => {
    expect(() => maskSecretQuery({ url: '/x?%E0%A4%A=1&hmac=s' })).not.toThrow();
    expect(maskSecretQuery({ url: '/x?%E0%A4%A=1&hmac=s' }).url).toContain('hmac=[REDACTED]');
  });
  test('duplicate-key errors log the field, not the value', () => {
    const err = Object.assign(new Error('E11000 duplicate key error collection: users index: email_1 dup key: { email: "player@example.com" }'), {
      code: 11000,
      keyPattern: { email: 1 },
      keyValue: { email: 'player@example.com' },
    });
    const safe = loggableError(err);
    expect(JSON.stringify(safe)).not.toContain('player@example.com');
    expect(safe.message).toBe('Duplicate key on email');
  });
});
