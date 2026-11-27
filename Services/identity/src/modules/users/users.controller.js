'use strict';

const usersService = require('./users.service');
const accountDeletion = require('./accountDeletion.service');
const { asyncHandler } = require('../../middleware/errorHandler');

const getMe = asyncHandler(async (req, res) => {
  const profile = await usersService.getProfile(req.user.id);
  res.status(200).json({ success: true, data: profile });
});

const updateMe = asyncHandler(async (req, res) => {
  const profile = await usersService.updateProfile(req.user.id, req.body);
  res.status(200).json({ success: true, data: profile });
});

const deleteMe = asyncHandler(async (req, res) => {
  const result = await accountDeletion.deleteOwnAccount(req.user.id, req.body);
  res.status(200).json({ success: true, data: result });
});

module.exports = { getMe, updateMe, deleteMe };
