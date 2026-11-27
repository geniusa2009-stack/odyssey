'use strict';

const authService = require('./auth.service');
const accountDeletion = require('../users/accountDeletion.service');
const { asyncHandler } = require('../../middleware/errorHandler');

const register = asyncHandler(async (req, res) => {
  const result = await authService.register(req.body);
  res.status(201).json({ success: true, data: result });
});

const login = asyncHandler(async (req, res) => {
  const result = await authService.login({ ...req.body, userAgent: req.headers['user-agent'] });
  res.status(200).json({ success: true, data: result });
});

const refresh = asyncHandler(async (req, res) => {
  const result = await authService.refresh({
    ...req.body,
    userAgent: req.headers['user-agent'],
  });
  res.status(200).json({ success: true, data: result });
});

const logout = asyncHandler(async (req, res) => {
  await authService.logout(req.body);
  res.status(204).send();
});

const logoutAll = asyncHandler(async (req, res) => {
  await authService.logoutAll({ userId: req.user.id });
  res.status(204).send();
});

const deleteAccount = asyncHandler(async (req, res) => {
  const { email, password } = req.body;
  const result = await accountDeletion.deleteAccountWithCredentials({ email, password });
  res.status(200).json({ success: true, data: result });
});

module.exports = { register, login, refresh, logout, logoutAll, deleteAccount };
