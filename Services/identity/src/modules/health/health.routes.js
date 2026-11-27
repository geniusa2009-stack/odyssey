'use strict';

/**
 * modules/health/health.routes.js — unversioned infrastructure probes.
 *   GET /health/live  : process is up (never touches the database)
 *   GET /health/ready : 200 only while MongoDB is connected, else 503
 */

const express = require('express');
const { getConnectionHealth } = require('../../infrastructure/database/mongoose');

const router = express.Router();

router.get('/live', (req, res) => {
  res.status(200).json({ success: true, status: 'live' });
});

router.get('/ready', (req, res) => {
  const db = getConnectionHealth();
  const ready = db.readyState === 1;
  res.status(ready ? 200 : 503).json({ success: ready, status: ready ? 'ready' : 'not_ready', db: db.state });
});

module.exports = router;
