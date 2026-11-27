'use strict';

/**
 * Anti-IDOR + cloud-save safety. Player data is reachable only through
 * /players/me/... and the user id always comes from the verified token, so
 * one player can never read or overwrite another's profile or saves. Saves
 * use revision-based conflict detection: a newer save is never silently lost.
 */

const request = require('supertest');
const createApp = require('../../src/app');

const app = createApp();
const PASSWORD = 'CorrectHorseBattery1';

async function registerPlayer(label) {
  const res = await request(app)
    .post('/api/v1/auth/register')
    .send({ email: `${label}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`, password: PASSWORD, displayName: label });
  expect(res.status).toBe(201);
  return res.body.data;
}
const auth = (p) => ({ Authorization: `Bearer ${p.accessToken}` });
const now = () => new Date().toISOString();
const putSave = (p, slot, body) => request(app).put(`/api/v1/players/me/saves/${slot}`).set(auth(p)).send({ clientSavedAt: now(), ...body });

describe('Anti-IDOR: player data is always the token owner\'s', () => {
  test('player A never sees player B\'s saves or profile', async () => {
    const a = await registerPlayer('pilotA');
    const b = await registerPlayer('pilotB');
    expect((await putSave(b, 0, { baseRevision: 0, payload: '{"secret":"B"}' })).status).toBe(200);
    await request(app).put('/api/v1/players/me/profile').set(auth(b)).send({ baseRevision: 1, avatar: { facePreset: 'face_b' } });

    const aSaves = await request(app).get('/api/v1/players/me/saves').set(auth(a));
    expect(aSaves.body.data).toEqual([]);
    expect((await request(app).get('/api/v1/players/me/saves/0').set(auth(a))).status).toBe(404);
    const aProfile = await request(app).get('/api/v1/players/me/profile').set(auth(a));
    expect(aProfile.body.data.avatar).toEqual({});
  });

  test('a userId smuggled in the body is rejected, not honoured', async () => {
    const a = await registerPlayer('smuggler');
    const b = await registerPlayer('victim');
    const res = await putSave(a, 0, { baseRevision: 0, payload: '{}', userId: b.user.id });
    expect(res.status).toBe(400);
    expect((await request(app).get('/api/v1/players/me/saves').set(auth(b))).body.data).toEqual([]);
  });

  test('requests without a token are rejected', async () => {
    expect((await request(app).get('/api/v1/players/me/profile')).status).toBe(401);
    expect((await request(app).put('/api/v1/players/me/saves/0').send({ baseRevision: 0, payload: '{}', clientSavedAt: now() })).status).toBe(401);
  });
});

describe('cloud saves never lose a newer save silently', () => {
  test('stale base revision -> 409 with the server copy; nothing is overwritten', async () => {
    const p = await registerPlayer('conflict');
    const first = await putSave(p, 0, { baseRevision: 0, payload: '{"v":1}', deviceLabel: 'Phone' });
    expect(first.body.data.revision).toBe(1);
    const second = await putSave(p, 0, { baseRevision: 1, payload: '{"v":2}', deviceLabel: 'Tablet' });
    expect(second.body.data.revision).toBe(2);

    // The phone still thinks revision 1 is current.
    const stale = await putSave(p, 0, { baseRevision: 1, payload: '{"v":"phone-old"}', deviceLabel: 'Phone' });
    expect(stale.status).toBe(409);
    expect(stale.body.error.code).toBe('SAVE_CONFLICT');
    expect(stale.body.error.details.server.revision).toBe(2);
    expect(stale.body.error.details.server.deviceLabel).toBe('Tablet');
    const kept = await request(app).get('/api/v1/players/me/saves/0').set(auth(p));
    expect(JSON.parse(kept.body.data.payload)).toEqual({ v: 2 });

    // Explicit, informed overwrite: base on the server revision.
    const forced = await putSave(p, 0, { baseRevision: 2, payload: '{"v":"phone-kept"}', deviceLabel: 'Phone' });
    expect(forced.status).toBe(200);
    expect(forced.body.data.revision).toBe(3);
  });

  test('two first saves in the same empty slot: one wins, the other gets a conflict', async () => {
    const p = await registerPlayer('race');
    const [r1, r2] = await Promise.all([
      putSave(p, 1, { baseRevision: 0, payload: '{"d":1}' }),
      putSave(p, 1, { baseRevision: 0, payload: '{"d":2}' }),
    ]);
    expect([r1.status, r2.status].sort()).toEqual([200, 409]);
  });

  test('profile updates use the same revision rule', async () => {
    const p = await registerPlayer('profilerev');
    await request(app).get('/api/v1/players/me/profile').set(auth(p));
    const ok = await request(app).put('/api/v1/players/me/profile').set(auth(p)).send({ baseRevision: 1, progression: { level: 2 } });
    expect(ok.body.data.revision).toBe(2);
    const stale = await request(app).put('/api/v1/players/me/profile').set(auth(p)).send({ baseRevision: 1, progression: { level: 1 } });
    expect(stale.status).toBe(409);
    expect(stale.body.error.details.server.progression).toEqual({ level: 2 });
  });

  test('size, JSON and slot limits are enforced', async () => {
    const p = await registerPlayer('limits');
    expect((await putSave(p, 0, { baseRevision: 0, payload: 'not json' })).status).toBe(400);
    expect((await putSave(p, 0, { baseRevision: 0, payload: JSON.stringify({ x: 'a'.repeat(5000) }) })).status).toBe(413);
    expect((await putSave(p, 3, { baseRevision: 0, payload: '{}' })).status).toBe(400);
  });
});
