'use strict';

/**
 * config/index.js
 *
 * The single object every other module imports for configuration.
 * Wraps env.js's validated output into a shaped, purpose-grouped config
 * object. No other file should call `loadEnv()` directly except this
 * one and tests that specifically want to test env.js in isolation.
 */

const { loadEnv } = require('./env');

const env = loadEnv();

function parseAllowedOrigins(raw) {
  return raw
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

const config = {
  env: env.NODE_ENV,
  isProduction: env.NODE_ENV === 'production',
  isTest: env.NODE_ENV === 'test',
  isDevelopment: env.NODE_ENV === 'development',

  server: {
    port: env.PORT,
    host: env.HOST,
    shutdownTimeoutMs: env.SHUTDOWN_TIMEOUT_MS,
    keepAliveTimeoutMs: env.SERVER_KEEP_ALIVE_TIMEOUT_MS,
    headersTimeoutMs: env.SERVER_HEADERS_TIMEOUT_MS,
    requestTimeoutMs: env.SERVER_REQUEST_TIMEOUT_MS,
  },

  db: {
    uri: env.MONGODB_URI,
    maxPoolSize: env.MONGO_MAX_POOL_SIZE,
    minPoolSize: env.MONGO_MIN_POOL_SIZE,
    connectTimeoutMs: env.MONGO_CONNECT_TIMEOUT_MS,
    socketTimeoutMs: env.MONGO_SOCKET_TIMEOUT_MS,
    serverSelectionTimeoutMs: env.MONGO_SERVER_SELECTION_TIMEOUT_MS,
    heartbeatFrequencyMs: env.MONGO_HEARTBEAT_FREQUENCY_MS,
    startupFailFast: env.DB_STARTUP_FAIL_FAST,
  },

  cors: {
    allowedOrigins: parseAllowedOrigins(env.CORS_ALLOWED_ORIGINS),
  },

  bodyLimit: env.JSON_BODY_LIMIT,

  rateLimit: {
    api: { windowMs: env.RATE_LIMIT_API_WINDOW_MS, max: env.RATE_LIMIT_API_MAX },
    auth: { windowMs: env.RATE_LIMIT_AUTH_WINDOW_MS, max: env.RATE_LIMIT_AUTH_MAX },
    authAccountFailures: { windowMs: env.RATE_LIMIT_AUTH_WINDOW_MS, max: env.RATE_LIMIT_AUTH_ACCOUNT_FAILURES_MAX },
    authIpFailures: { windowMs: env.RATE_LIMIT_AUTH_WINDOW_MS, max: env.RATE_LIMIT_AUTH_IP_FAILURES_MAX },
    save: { windowMs: env.RATE_LIMIT_SAVE_WINDOW_MS, max: env.RATE_LIMIT_SAVE_MAX },
  },

  jwt: {
    accessSecret: env.JWT_ACCESS_SECRET,
    refreshSecret: env.JWT_REFRESH_SECRET,
    accessTokenTtl: env.JWT_ACCESS_TOKEN_TTL,
    refreshTokenTtlDays: env.JWT_REFRESH_TOKEN_TTL_DAYS,
  },

  security: {
    bcryptSaltRounds: env.BCRYPT_SALT_ROUNDS,
  },

  logging: {
    level: env.LOG_LEVEL,
  },

  saves: {
    maxBytes: env.SAVE_MAX_BYTES,
    maxSlots: env.SAVE_MAX_SLOTS,
  },

  publicBaseUrl: env.PUBLIC_BASE_URL || null,
};

module.exports = config;
