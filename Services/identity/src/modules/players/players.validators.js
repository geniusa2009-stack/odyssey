'use strict';

const { z } = require('zod');

// Short identifier used for presets, colours (hex) and content ids.
const id = z.string().trim().min(1).max(48).regex(/^[A-Za-z0-9_.:#-]+$/);

// Character Creator choices (all optional; unknown keys rejected).
const avatarSchema = z
  .object({
    facePreset: id.optional(),
    hairStyle: id.optional(),
    hairColor: id.optional(),
    eyeColor: id.optional(),
    skinTone: id.optional(),
    suitColor: id.optional(),
    suitAccentColor: id.optional(),
    visorStyle: id.optional(),
    gloves: id.optional(),
    boots: id.optional(),
    missionPatch: id.optional(),
    backpackModule: id.optional(),
  })
  .strict();

// Settings are a flat map of short keys to primitive values (graphics, audio,
// controls, accessibility); the client owns the meaning of each key.
const settingsSchema = z
  .record(z.string().min(1).max(48), z.union([z.string().max(64), z.number().finite(), z.boolean()]))
  .refine((o) => Object.keys(o).length <= 128, 'Too many settings.');

const missionSchema = z
  .object({
    missionId: id,
    status: z.enum(['locked', 'available', 'in_progress', 'completed']),
    stage: z.string().max(64).optional(),
    decisions: z.array(id).max(64).optional(),
    updatedAt: z.string().datetime().optional(),
  })
  .strict();

const progressionSchema = z
  .record(z.string().min(1).max(48), z.union([z.number().finite(), z.string().max(64), z.boolean()]))
  .refine((o) => Object.keys(o).length <= 64, 'Too many progression entries.');

const updateProfileSchema = z
  .object({
    baseRevision: z.number().int().min(1),
    avatar: avatarSchema.optional(),
    settings: settingsSchema.optional(),
    progression: progressionSchema.optional(),
    missions: z.array(missionSchema).max(200).optional(),
    discoveries: z.array(id).max(1000).optional(),
    unlocks: z.array(id).max(1000).optional(),
  })
  .strict();

const saveParamsSchema = z.object({ slot: z.coerce.number().int().min(0).max(15) }).strict();

const putSaveSchema = z
  .object({
    // 0 = "there was no save in this slot when I started"; otherwise the
    // revision this save was based on. Anything else is a conflict.
    baseRevision: z.number().int().min(0),
    payload: z.string().min(2),
    clientSavedAt: z.string().datetime(),
    deviceLabel: z.string().max(32).optional(),
    gameVersion: z.string().max(32).optional(),
  })
  .strict();

module.exports = { avatarSchema, updateProfileSchema, saveParamsSchema, putSaveSchema };
