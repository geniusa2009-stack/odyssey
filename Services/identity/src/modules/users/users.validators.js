'use strict';

const { z } = require('zod');

const updateProfileSchema = z
  .object({
    displayName: z.string().trim().min(2).max(32).optional(),
  })
  .strict();

// Account deletion: the current password re-authenticates the request and
// the literal "DELETE" proves the user meant it (the UI asks them to type it).
const deleteAccountSchema = z
  .object({
    password: z.string().min(1).max(128),
    confirmation: z.literal('DELETE'),
  })
  .strict();

module.exports = { updateProfileSchema, deleteAccountSchema };
