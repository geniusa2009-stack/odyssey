'use strict';

/**
 * modules/admin/admin.routes.js — operational, admin-only. Aggregate counts
 * only: no personal data is exposed through this route.
 */

const express = require('express');
const authenticate = require('../../middleware/authenticate');
const authorizeRole = require('../../middleware/authorizeRole');
const { asyncHandler } = require('../../middleware/errorHandler');
const { ROLES } = require('../../security/rbac');
const User = require('../users/user.model');
const { CloudSave } = require('../players/player.models');

const router = express.Router();
router.use(authenticate, authorizeRole(ROLES.ADMIN));

router.get('/stats', asyncHandler(async (req, res) => {
  const [accounts, pendingDeletions, saves] = await Promise.all([
    User.countDocuments({ deletionRequestedAt: null }),
    User.countDocuments({ deletionRequestedAt: { $ne: null } }),
    CloudSave.estimatedDocumentCount(),
  ]);
  res.status(200).json({ success: true, data: { accounts, pendingDeletions, saves } });
}));

module.exports = router;
