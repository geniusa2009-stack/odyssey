'use strict';

const express = require('express');
const controller = require('./auth.controller');
const validate = require('../../middleware/validate');
const authenticate = require('../../middleware/authenticate');
const { authLimiter, authAccountFailureLimiter, authIpFailureLimiter } = require('../../middleware/rateLimiter');
const { registerSchema, loginSchema, refreshSchema, webDeleteAccountSchema } = require('./auth.validators');

const router = express.Router();

router.post('/register', authLimiter, validate(registerSchema), controller.register);
router.post('/login', authIpFailureLimiter, authLimiter, validate(loginSchema), authAccountFailureLimiter, controller.login);
router.post('/refresh', authLimiter, validate(refreshSchema), controller.refresh);
router.post('/logout', authLimiter, validate(refreshSchema), controller.logout);
router.post('/logout-all', authenticate, controller.logoutAll);
// Public account-deletion page (Google Play: deletion must be possible without the app).
router.post(
  '/delete-account',
  authIpFailureLimiter,
  authLimiter,
  validate(webDeleteAccountSchema),
  authAccountFailureLimiter,
  controller.deleteAccount
);

module.exports = router;
