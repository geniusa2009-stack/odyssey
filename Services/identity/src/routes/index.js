'use strict';

/**
 * routes/index.js
 *
 * /health (unversioned probes) and the ODYSSEY identity API under /api/v1:
 *   /auth     register, login, refresh (rotation + reuse detection), logout,
 *             logout-all, public account deletion
 *   /users    the signed-in account (GET/PATCH/DELETE /users/me)
 *   /players  the signed-in player's profile and cloud saves
 *   /admin    admin-only aggregate statistics
 */

const express = require('express');

const healthRoutes = require('../modules/health/health.routes');
const authRoutes = require('../modules/auth/auth.routes');
const usersRoutes = require('../modules/users/users.routes');
const playersRoutes = require('../modules/players/players.routes');
const adminRoutes = require('../modules/admin/admin.routes');

const router = express.Router();

router.use('/health', healthRoutes);

const apiV1 = express.Router();
apiV1.use('/auth', authRoutes);
apiV1.use('/users', usersRoutes);
apiV1.use('/players', playersRoutes);
apiV1.use('/admin', adminRoutes);

router.use('/api/v1', apiV1);

module.exports = router;
