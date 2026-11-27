'use strict';

/**
 * Session security (ported from the AgriSmart identity service):
 * - the role and account state come from the database, not the token;
 * - only HS256 tokens signed with our secret are accepted;
 * - logout-all also kills access tokens already issued;
 * - concurrent refreshes with one token cannot both succeed;
 * - logout revokes the refresh token server-side.
 */

const request = require('supertest');
const jwt = require('jsonwebtoken');
const createApp = require('../../src/app');
const config = require('../../src/config');
const User = require('../../src/modules/users/user.model');

const app = createApp();
const PASSWORD = 'CorrectHorseBattery1';

function uniqueEmail() {
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

async function register() {
  const res = await request(app)
    .post('/api/v1/auth/register')
    .send({ email: uniqueEmail(), password: PASSWORD, displayName: 'Session Tester' });
  expect(res.status).toBe(201);
  return res.body.data;
}

const me = (token) => request(app).get('/api/v1/users/me').set('Authorization', `Bearer ${token}`);
const adminStats = (token) =>
  request(app).get('/api/v1/admin/stats').set('Authorization', `Bearer ${token}`);

describe('access token trust', () => {
  test('a role claim in the token is ignored; the database role decides', async () => {
    const { user, accessToken } = await register();
    // A token minted with the real secret but claiming admin.
    const forged = jwt.sign({ sub: user.id, role: 'admin' }, config.jwt.accessSecret, {
      algorithm: 'HS256',
      expiresIn: '5m',
      issuer: 'odyssey-identity', audience: 'odyssey-game',
    });
    expect((await adminStats(forged)).status).toBe(403);
    expect((await adminStats(accessToken)).status).toBe(403);
  });

  test('promotion and demotion take effect on the next request, without a new token', async () => {
    const { user, accessToken } = await register();
    await User.updateOne({ _id: user.id }, { role: 'admin' });
    expect((await adminStats(accessToken)).status).toBe(200);
    await User.updateOne({ _id: user.id }, { role: 'player' });
    expect((await adminStats(accessToken)).status).toBe(403);
  });

  test('a deactivated account is rejected immediately', async () => {
    const { user, accessToken } = await register();
    expect((await me(accessToken)).status).toBe(200);
    await User.updateOne({ _id: user.id }, { isActive: false });
    const res = await me(accessToken);
    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('AUTH_TOKEN_INVALID');
  });

  test('a token for a user that does not exist is rejected', async () => {
    const ghost = jwt.sign({ sub: '64b7f0c2a1b2c3d4e5f60718', role: 'admin' }, config.jwt.accessSecret, {
      algorithm: 'HS256',
      expiresIn: '5m',
      issuer: 'odyssey-identity', audience: 'odyssey-game',
    });
    expect((await me(ghost)).status).toBe(401);
  });

  test.each([
    ['alg none', () => jwt.sign({ sub: 'x', role: 'admin' }, null, { algorithm: 'none', issuer: 'odyssey-identity', audience: 'odyssey-game' })],
    ['HS512 with our secret', () =>
      jwt.sign({ sub: 'x', role: 'admin' }, config.jwt.accessSecret, { algorithm: 'HS512', issuer: 'odyssey-identity', audience: 'odyssey-game' })],
    ['wrong secret', () =>
      jwt.sign({ sub: 'x', role: 'admin' }, 'not-the-secret-at-all-0123456789', { issuer: 'odyssey-identity', audience: 'odyssey-game' })],
    ['wrong issuer', () => jwt.sign({ sub: 'x', role: 'admin' }, config.jwt.accessSecret, { issuer: 'someone-else', audience: 'odyssey-game' })],
    ['wrong audience', () =>
      jwt.sign({ sub: '64b7f0c2a1b2c3d4e5f60718', role: 'admin' }, config.jwt.accessSecret, { issuer: 'odyssey-identity', audience: 'another-app' })],
    ['non-ObjectId subject', () =>
      jwt.sign({ sub: { $ne: null }, role: 'admin' }, config.jwt.accessSecret, { issuer: 'odyssey-identity', audience: 'odyssey-game' })],
  ])('rejects %s', async (_label, make) => {
    const res = await me(make());
    expect(res.status).toBe(401);
  });

  test('an expired token gets AUTH_TOKEN_EXPIRED', async () => {
    const { user } = await register();
    const expired = jwt.sign(
      { sub: user.id, role: 'player', iat: Math.floor(Date.now() / 1000) - 3600, exp: Math.floor(Date.now() / 1000) - 60 },
      config.jwt.accessSecret,
      { algorithm: 'HS256', issuer: 'odyssey-identity', audience: 'odyssey-game' }
    );
    const res = await me(expired);
    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe('AUTH_TOKEN_EXPIRED');
  });
});

describe('logout', () => {
  test('logout-all invalidates access tokens issued before it', async () => {
    const { user, accessToken } = await register();
    // iat has 1-second resolution: make the existing token clearly older.
    await User.updateOne({ _id: user.id }, { tokensValidAfter: null });
    const older = jwt.sign(
      { sub: user.id, role: 'player', iat: Math.floor(Date.now() / 1000) - 5 },
      config.jwt.accessSecret,
      { algorithm: 'HS256', expiresIn: '10m', issuer: 'odyssey-identity', audience: 'odyssey-game' }
    );
    expect((await me(older)).status).toBe(200);
    const out = await request(app).post('/api/v1/auth/logout-all').set('Authorization', `Bearer ${accessToken}`);
    expect(out.status).toBe(204);
    expect((await me(older)).status).toBe(401);
  });

  test('logout revokes the refresh token server-side', async () => {
    const { refreshToken } = await register();
    expect((await request(app).post('/api/v1/auth/logout').send({ refreshToken })).status).toBe(204);
    const res = await request(app).post('/api/v1/auth/refresh').send({ refreshToken });
    expect(res.status).toBe(401);
  });
});

describe('refresh rotation', () => {
  test('two concurrent refreshes with the same token: at most one succeeds and the family is revoked', async () => {
    const { refreshToken } = await register();
    const results = await Promise.all(
      [0, 1, 2].map(() => request(app).post('/api/v1/auth/refresh').send({ refreshToken }))
    );
    const ok = results.filter((r) => r.status === 200);
    expect(ok.length).toBeLessThanOrEqual(1);
    expect(results.filter((r) => r.status === 401).length).toBeGreaterThanOrEqual(2);
    // Whoever won holds a token from a family that reuse detection killed.
    if (ok.length === 1) {
      const next = await request(app).post('/api/v1/auth/refresh').send({ refreshToken: ok[0].body.data.refreshToken });
      expect(next.status).toBe(401);
    }
  });

  test('a normal refresh returns a working access token and a new refresh token', async () => {
    const { refreshToken } = await register();
    const res = await request(app).post('/api/v1/auth/refresh').send({ refreshToken });
    expect(res.status).toBe(200);
    expect(res.body.data.refreshToken).not.toBe(refreshToken);
    expect((await me(res.body.data.accessToken)).status).toBe(200);
  });
});
