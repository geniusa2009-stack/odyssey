'use strict';

/**
 * Account deletion (Google Play requirement), ported from AgriSmart and
 * adapted to ODYSSEY data: the account, profile (avatar, settings,
 * progression, missions, discoveries, unlocks), every cloud save and every
 * session are deleted — nothing is retained. In-app (DELETE /users/me) and
 * public web page (POST /auth/delete-account) flows.
 */

const request = require('supertest');
const mongoose = require('mongoose');
const createApp = require('../../src/app');
const User = require('../../src/modules/users/user.model');
const RefreshToken = require('../../src/modules/auth/refreshToken.model');
const { PlayerProfile, CloudSave } = require('../../src/modules/players/player.models');
const accountDeletion = require('../../src/modules/users/accountDeletion.service');

const app = createApp();
const PASSWORD = 'CorrectHorseBattery1';
const uniq = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const auth = (u) => ({ Authorization: `Bearer ${u.accessToken}` });

async function register(label) {
  const email = `${label}-${uniq()}@example.com`;
  const res = await request(app).post('/api/v1/auth/register').send({ email, password: PASSWORD, displayName: label.slice(0, 32) });
  expect(res.status).toBe(201);
  return { email, ...res.body.data };
}

/** A player with a customised character, progress and two cloud saves. */
async function richPlayer(label = 'pilot') {
  const u = await register(label);
  await request(app).get('/api/v1/players/me/profile').set(auth(u));
  const p = await request(app).put('/api/v1/players/me/profile').set(auth(u)).send({
    baseRevision: 1,
    avatar: { facePreset: 'face_02', hairStyle: 'short_01', suitColor: '#e8edf2', missionPatch: 'patch_luna' },
    settings: { 'graphics.preset': 'balanced', 'audio.master': 0.8 },
    progression: { level: 3, xp: 420 },
    missions: [{ missionId: 'earth_command_power', status: 'completed' }],
    discoveries: ['moon.shackleton_ice'],
    unlocks: ['suit.ion_trim'],
  });
  expect(p.status).toBe(200);
  for (const slot of [0, 1]) {
    const s = await request(app).put(`/api/v1/players/me/saves/${slot}`).set(auth(u))
      .send({ baseRevision: 0, payload: JSON.stringify({ slot, mission: 'earth_command' }), clientSavedAt: new Date().toISOString() });
    expect(s.status).toBe(200);
  }
  return u;
}

const del = (u, body) => request(app).delete('/api/v1/users/me').set(auth(u)).send(body);

describe('DELETE /users/me', () => {
  test('requires the password and the typed confirmation', async () => {
    const u = await register('delcheck');
    expect((await del(u, { password: PASSWORD })).status).toBe(400);
    expect((await del(u, { password: PASSWORD, confirmation: 'delete' })).status).toBe(400);
    expect((await del(u, { password: 'wrong-password-1', confirmation: 'DELETE' })).status).toBe(401);
    expect((await del(u, { password: PASSWORD, confirmation: 'DELETE', role: 'admin' })).status).toBe(400);
    expect(await User.exists({ email: u.email })).toBeTruthy();
    expect((await request(app).delete('/api/v1/users/me').send({ password: PASSWORD, confirmation: 'DELETE' })).status).toBe(401);
  });

  test('removes the account and ALL its ODYSSEY data; other players are untouched', async () => {
    const u = await richPlayer('pilot');
    const other = await richPlayer('copilot');
    const uid = new mongoose.Types.ObjectId(u.user.id);
    expect(await CloudSave.countDocuments({ userId: uid })).toBe(2);

    const res = await del(u, { password: PASSWORD, confirmation: 'DELETE' });
    expect(res.status).toBe(200);
    expect(res.body.data).toEqual({ deleted: true, pending: false });

    expect(await User.exists({ _id: uid })).toBeNull();
    expect(await RefreshToken.countDocuments({ userId: uid })).toBe(0);
    expect(await PlayerProfile.countDocuments({ userId: uid })).toBe(0);
    expect(await CloudSave.countDocuments({ userId: uid })).toBe(0);

    // Old credentials and tokens are dead; the email can register again (as a new, empty account).
    expect((await request(app).get('/api/v1/users/me').set(auth(u))).status).toBe(401);
    expect((await request(app).get('/api/v1/players/me/saves').set(auth(u))).status).toBe(401);
    expect((await request(app).post('/api/v1/auth/refresh').send({ refreshToken: u.refreshToken })).status).toBe(401);
    expect((await request(app).post('/api/v1/auth/login').send({ email: u.email, password: PASSWORD })).status).toBe(401);
    const again = await request(app).post('/api/v1/auth/register').send({ email: u.email, password: PASSWORD, displayName: 'New' });
    expect(again.status).toBe(201);
    const fresh = await request(app).get('/api/v1/players/me/saves').set(auth(again.body.data));
    expect(fresh.body.data).toEqual([]);

    // The other player keeps everything.
    const oid = new mongoose.Types.ObjectId(other.user.id);
    expect(await CloudSave.countDocuments({ userId: oid })).toBe(2);
    expect(await PlayerProfile.countDocuments({ userId: oid })).toBe(1);
  });

  test('an interrupted deletion leaves the account locked; the sweep finishes it', async () => {
    const u = await richPlayer('crash');
    const uid = new mongoose.Types.ObjectId(u.user.id);
    // Simulate a crash right after the lock step.
    await User.updateOne({ _id: uid }, { $set: { isActive: false, deletionRequestedAt: new Date(), tokensValidAfter: new Date() } });
    expect((await request(app).post('/api/v1/auth/login').send({ email: u.email, password: PASSWORD })).status).toBe(401);
    const r = await accountDeletion.finishPendingDeletions();
    expect(r.completed).toBeGreaterThanOrEqual(1);
    expect(await User.exists({ _id: uid })).toBeNull();
    expect(await CloudSave.countDocuments({ userId: uid })).toBe(0);
    expect(await PlayerProfile.countDocuments({ userId: uid })).toBe(0);
  });

  test('the last admin cannot delete their account', async () => {
    await User.updateMany({ role: 'admin' }, { $set: { role: 'player' } });
    const u = await register('lastadmin');
    await User.updateOne({ email: u.email }, { $set: { role: 'admin' } });
    const res = await del(u, { password: PASSWORD, confirmation: 'DELETE' });
    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe('LAST_ADMIN');
    expect((await User.findOne({ email: u.email }).lean()).isActive).toBe(true);
  });
});

describe('POST /auth/delete-account (public web page, no app)', () => {
  test('deletes with email + password + confirmation, including saves', async () => {
    const u = await richPlayer('webdel');
    const res = await request(app).post('/api/v1/auth/delete-account').send({ email: u.email, password: PASSWORD, confirmation: 'DELETE' });
    expect(res.status).toBe(200);
    expect(res.body.data.deleted).toBe(true);
    expect(await User.exists({ email: u.email })).toBeNull();
    expect(await CloudSave.countDocuments({ userId: new mongoose.Types.ObjectId(u.user.id) })).toBe(0);
  });

  test('wrong password and unknown email get the same answer; nothing is deleted', async () => {
    const u = await register('webdel2');
    const wrong = await request(app).post('/api/v1/auth/delete-account').send({ email: u.email, password: 'nope-nope-1', confirmation: 'DELETE' });
    const unknown = await request(app).post('/api/v1/auth/delete-account').send({ email: `nobody-${uniq()}@example.com`, password: 'nope-nope-1', confirmation: 'DELETE' });
    expect(wrong.status).toBe(401);
    expect(unknown.status).toBe(401);
    expect(wrong.body.error.message).toBe(unknown.body.error.message);
    expect(await User.exists({ email: u.email })).toBeTruthy();
  });

  test('rejects NoSQL operator payloads', async () => {
    const res = await request(app).post('/api/v1/auth/delete-account').send({ email: { $ne: null }, password: { $ne: null }, confirmation: 'DELETE' });
    expect(res.status).toBe(400);
  });

  test('the public deletion page is served with a strict CSP', async () => {
    const res = await request(app).get('/account/delete');
    expect(res.status).toBe(200);
    expect(res.text).toContain('Delete your ODYSSEY account');
    expect(res.headers['content-security-policy']).toContain("default-src 'none'");
    expect(res.headers['content-security-policy']).not.toContain('unsafe-inline');
  });
});
