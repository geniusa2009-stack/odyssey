'use strict';

/**
 * scripts/finishAccountDeletions.js — `npm run accounts:finish-deletions`
 *
 * Finishes account deletions that were interrupted (e.g. a process crash).
 * The accounts are already locked; this re-runs the idempotent deletion steps. Safe to run
 * repeatedly, e.g. daily from a scheduler.
 */

require('dotenv').config();

const { connectDB, disconnectDB } = require('../src/infrastructure/database/mongoose');
const { finishPendingDeletions } = require('../src/modules/users/accountDeletion.service');

async function main() {
  await connectDB();
  const r = await finishPendingDeletions({ limit: 200 });
  // eslint-disable-next-line no-console
  console.log(`[accounts] pending ${r.pending}, completed ${r.completed}`);
  return 0;
}

main()
  .then(async (code) => { await disconnectDB(); process.exit(code); })
  .catch(async (err) => {
    // eslint-disable-next-line no-console
    console.error('[accounts] failed:', err.message);
    await disconnectDB().catch(() => {});
    process.exit(1);
  });
