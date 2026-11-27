'use strict';

/**
 * tests/setup/globalSetup.js
 *
 * Runs once before any test file. Starts an ephemeral, real MongoDB
 * instance via mongodb-memory-server (downloads and runs an actual
 * mongod binary — no Atlas credentials, no network dependency on a
 * real database) and
 * injects its connection string plus every other required env var into
 * process.env, which Jest test-worker processes inherit.
 */

const { MongoMemoryServer } = require('mongodb-memory-server');

module.exports = async function globalSetup() {
  const mongod = await MongoMemoryServer.create();
  global.__MONGOD__ = mongod;

  process.env.NODE_ENV = 'test';
  process.env.MONGODB_URI = mongod.getUri('odyssey_identity_test');
  process.env.JWT_ACCESS_SECRET = 'test-access-secret-do-not-use-in-prod-0001';
  process.env.JWT_REFRESH_SECRET = 'test-refresh-secret-do-not-use-in-prod-0002';
  process.env.BCRYPT_SALT_ROUNDS = '4'; // fast hashing in tests only
  process.env.LOG_LEVEL = 'silent';
  process.env.SAVE_MAX_BYTES = '4096'; // small cap so the size limit is testable
};
