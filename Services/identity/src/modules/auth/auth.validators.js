'use strict';

const { z } = require('zod');

const registerSchema = z
  .object({
    email: z.string().email(),
    password: z.string().min(8).max(128),
    // in-game callsign shown to the player; no role can be chosen here (always 'player')
    displayName: z.string().trim().min(2).max(32),
  })
  .strict();

const loginSchema = z
  .object({
    email: z.string().email(),
    password: z.string().min(1),
  })
  .strict();

const refreshSchema = z
  .object({
    refreshToken: z.string().min(1),
  })
  .strict();

// Public web deletion page (no app needed): sign-in credentials plus the
// typed confirmation.
const webDeleteAccountSchema = z
  .object({
    email: z.string().email(),
    password: z.string().min(1).max(128),
    confirmation: z.literal('DELETE'),
  })
  .strict();

module.exports = { registerSchema, loginSchema, refreshSchema, webDeleteAccountSchema };
