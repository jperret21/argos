#!/usr/bin/env node
/**
 * Moved to web/scripts/audit-png.mjs in wave 2 (web/lab/PROPOSAL.md sections
 * 3.5 and 6): one implementation, used as the CI gate (`npm run
 * audit:night-red`, `npm run audit:brass`). This forwarder keeps the lab's
 * documented command and its JSON-lines output:
 *
 *   node web/lab/synthesis/audit-png.mjs [--brass] a.png b.png ...
 *
 * Rules, options and exit codes: see the header of web/scripts/audit-png.mjs.
 */
import { main } from '../../scripts/audit-png.mjs';

const args = process.argv.slice(2);
process.exitCode = main(args.includes('--json') ? args : [...args, '--json']);
