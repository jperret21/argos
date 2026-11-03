#!/usr/bin/env node
/**
 * One entry point for the design lab's captures and behaviour checks, gated
 * on the Night Red pixel audit (web/lab/PROPOSAL.md sections 3.5 and 6, wave 2).
 *
 * The lab keeps its own capture scripts (src/lab/<lab>/capture.mjs and
 * src/lab/controls/behave.mjs: they are the design reference, each with its
 * shot list). This script gives them one command and one gate:
 *
 *   node scripts/capture-lab.mjs LAB --out DIR [--port P] [--only a,b] [--list] [--dpr D]
 *   npm run capture:lab -- workspace --out /tmp/lab-shots --only run-night-red,run-observatory
 *
 *   LAB   workspace | charts | controls  (captures), behave (controls behaviour checks)
 *
 * 1. Serves web/ with Vite on --port (default: the lab's own port, 5204
 *    workspace, 5203 charts, 5202 controls; behave needs 5202, its URL is
 *    fixed), unless something already answers there.
 * 2. Runs the lab's script against it (--only, --list and --dpr are passed on).
 * 3. Audits every *night-red*.png written to --out, as written (never
 *    resized), with scripts/audit-png.mjs, and writes DIR/audit.json.
 * 4. Stops the Vite server it started.
 *
 * Exit code: 0 when the lab script and every Night Red shot pass; 1 otherwise;
 * 2 on a usage error. Puppeteer-core drives the system Chrome (CHROME_PATH).
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { auditFile, pngFiles, themeOf } from './audit-png.mjs';

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LABS = {
  workspace: { script: 'src/lab/workspace/capture.mjs', port: 5204, page: 'workspace', base: (o) => o },
  charts: { script: 'src/lab/charts/capture.mjs', port: 5203, page: 'charts', base: (o) => `${o}/lab/charts.html` },
  controls: { script: 'src/lab/controls/capture.mjs', port: 5202, page: 'controls', base: (o) => `${o}/lab/controls.html` },
  behave: { script: 'src/lab/controls/behave.mjs', port: 5202, page: 'controls', base: null, fixedPort: true },
};

const { values: opt, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: 'string' },
    port: { type: 'string' },
    only: { type: 'string' },
    list: { type: 'boolean', default: false },
    dpr: { type: 'string' },
  },
});

const say = (m) => console.log(`[capture-lab] ${m}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lab = LABS[positionals[0]];
if (!lab || positionals.length !== 1) {
  console.error(`capture-lab: give one lab: ${Object.keys(LABS).join(', ')} (see the header of this file)`);
  process.exit(2);
}
if (lab.base && !opt.out && !opt.list) {
  console.error('capture-lab: --out DIR is required for a capture');
  process.exit(2);
}
const port = Number(opt.port ?? lab.port);
if (lab.fixedPort && port !== lab.port) {
  console.error(`capture-lab: behave.mjs has its URL fixed on port ${lab.port}`);
  process.exit(2);
}
const origin = `http://localhost:${port}`;

async function answers() {
  try {
    const res = await fetch(`${origin}/lab/${lab.page}.html`);
    return res.ok;
  } catch {
    return false;
  }
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd: WEB, stdio: 'inherit', ...opts });
    child.on('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)));
  });
}

let vite = null;
let code = 0;
try {
  if (!(await answers())) {
    say(`starting Vite on port ${port}`);
    vite = spawn(path.join(WEB, 'node_modules/.bin/vite'), ['--port', String(port), '--strictPort'], {
      cwd: WEB,
      stdio: ['ignore', 'ignore', 'inherit'],
    });
    const t0 = Date.now();
    while (!(await answers())) {
      if (vite.exitCode !== null) throw new Error(`Vite exited (${vite.exitCode}): is port ${port} taken?`);
      if (Date.now() - t0 > 30_000) throw new Error(`Vite did not answer on ${origin} within 30 s`);
      await sleep(250);
    }
  } else say(`using the server already on ${origin}`);

  const args = [path.join(WEB, lab.script)];
  if (lab.base) args.push('--base', lab.base(origin));
  if (opt.out) args.push('--out', opt.out);
  if (opt.only) args.push('--only', opt.only);
  if (opt.list) args.push('--list');
  if (opt.dpr) args.push('--dpr', opt.dpr);
  const status = await run(process.execPath, args);
  if (status !== 0) {
    say(`${lab.script} exited with ${status}`);
    code = 1;
  }

  if (opt.out && fs.existsSync(opt.out) && !opt.list) {
    const files = pngFiles([opt.out]).filter((f) => themeOf(f) === 'night-red');
    const results = files.map((f) => auditFile(f));
    fs.writeFileSync(path.join(opt.out, 'audit.json'), JSON.stringify(results, null, 2));
    const failed = results.filter((r) => r.error || !r.nightRed?.pass);
    say(`Night Red audit: ${files.length - failed.length} of ${files.length} shot(s) pass`);
    for (const r of failed) say(`  FAIL ${path.basename(r.file)}: ${r.error ?? JSON.stringify(r.nightRed.first)}`);
    if (failed.length) code = 1;
  }
} catch (e) {
  console.error(`[capture-lab] FAILED: ${e instanceof Error ? e.message : e}`);
  code = 1;
} finally {
  if (vite && vite.exitCode === null) {
    vite.kill('SIGTERM');
    say('Vite stopped');
  }
}
process.exit(code);
