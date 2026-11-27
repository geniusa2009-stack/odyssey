'use strict';

const express = require('express');
const controller = require('./users.controller');
const validate = require('../../middleware/validate');
const authenticate = require('../../middleware/authenticate');
const { authLimiter } = require('../../middleware/rateLimiter');
const { updateProfileSchema, deleteAccountSchema } = require('./users.validators');

const router = express.Router();

router.use(authenticate);

router.get('/me', controller.getMe);
router.patch('/me', validate(updateProfileSchema), controller.updateMe);
router.delete('/me', authLimiter, validate(deleteAccountSchema), controller.deleteMe);

module.exports = router;
