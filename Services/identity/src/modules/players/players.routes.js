'use strict';

/**
 * modules/players/players.routes.js
 *
 * /api/v1/players/me/... — always the authenticated player's own data
 * (there is deliberately no route taking another player's id: no IDOR surface).
 */

const express = require('express');
const service = require('./players.service');
const validate = require('../../middleware/validate');
const authenticate = require('../../middleware/authenticate');
const { saveLimiter } = require('../../middleware/rateLimiter');
const { asyncHandler } = require('../../middleware/errorHandler');
const { updateProfileSchema, saveParamsSchema, putSaveSchema } = require('./players.validators');

const router = express.Router();
router.use(authenticate);

router.get('/me/profile', asyncHandler(async (req, res) => {
  res.status(200).json({ success: true, data: await service.getProfile(req.user.id) });
}));

router.put('/me/profile', saveLimiter, validate(updateProfileSchema), asyncHandler(async (req, res) => {
  res.status(200).json({ success: true, data: await service.updateProfile(req.user.id, req.body) });
}));

router.get('/me/saves', asyncHandler(async (req, res) => {
  res.status(200).json({ success: true, data: await service.listSaves(req.user.id) });
}));

router.get('/me/saves/:slot', validate(saveParamsSchema, 'params'), asyncHandler(async (req, res) => {
  res.status(200).json({ success: true, data: await service.getSave(req.user.id, req.params.slot) });
}));

router.put('/me/saves/:slot', saveLimiter, validate(saveParamsSchema, 'params'), validate(putSaveSchema),
  asyncHandler(async (req, res) => {
    res.status(200).json({ success: true, data: await service.putSave(req.user.id, req.params.slot, req.body) });
  }));

router.delete('/me/saves/:slot', saveLimiter, validate(saveParamsSchema, 'params'), asyncHandler(async (req, res) => {
  await service.deleteSave(req.user.id, req.params.slot);
  res.status(204).end();
}));

module.exports = router;
