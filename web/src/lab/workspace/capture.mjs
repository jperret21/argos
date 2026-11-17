#!/usr/bin/env node
/**
 * Screenshots of the workspace lab (web/lab/workspace.html) in headless
 * Chrome through puppeteer-core (system Chrome, never downloaded), with the
 * Night Red pixel audit of the research lab: a pixel "emits non-red light"
 * when max(G, B) > 8 and max(G, B) > 0.68 x R (0.68 is just above the
 * greenest Night Red token, --fg #d88f8f, G/R 0.66).
 *
 *   cd web && npx vite --port 5204 --strictPort        # terminal 1
 *   node src/lab/workspace/capture.mjs --out DIR [--only a,b] [--list]
 *   node src/lab/workspace/capture.mjs --out DIR --url '/lab/workspace.html?scene=run' --name quick
 *   node src/lab/workspace/capture.mjs --audit a.png b.png     # Night Red audit of any PNG (e.g. WebKit shots)
 *
 * Every shot freezes the simulated clock (?speed=0) unless it says otherwise,
 * so the pictures are reproducible. Output: <name>.png and report.json
 * (console errors, page errors, non-local requests, audit, layout facts).
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import puppeteer from 'puppeteer-core';

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const { values: opt, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    audit: { type: 'boolean', default: false },
    base: { type: 'string', default: 'http://localhost:5204' },
    out: { type: 'string' },
    only: { type: 'string' },
    list: { type: 'boolean', default: false },
    url: { type: 'string' },
    name: { type: 'string', default: 'quick' },
    width: { type: 'string', default: '1440' },
    height: { type: 'string', default: '900' },
    dpr: { type: 'string', default: '1' },
  },
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const THEMES = ['observatory', 'charcoal', 'night-red'];
const P = '/lab/workspace.html';

/** name, query, theme, size, wait, steps. */
const SHOTS = [];
const add = (s) => SHOTS.push({ wait: 2200, width: 1440, height: 900, ...s });

for (const theme of THEMES) {
  add({ name: `run-${theme}`, q: 'scene=run&speed=0', theme });
  add({ name: `framing-${theme}`, q: 'scene=framing&speed=0', theme });
  add({ name: `watch-${theme}`, q: 'scene=run&speed=0&view=watch', theme });
  add({ name: `overview-${theme}`, q: 'scene=run&speed=0&view=overview', theme, wait: 1200 });
}
add({ name: 'focus-observatory', q: 'scene=focus&speed=0', theme: 'observatory' });
add({ name: 'focus-during-run-charcoal', q: 'scene=run&speed=0&mode=focus', theme: 'charcoal' });
add({ name: 'field-observatory', q: 'scene=field&speed=0&select=2&hover=4', theme: 'observatory' });
add({ name: 'field-night-red', q: 'scene=field&speed=0&select=2&hover=4', theme: 'night-red' });
add({ name: 'run-healthy-charcoal', q: 'scene=run-healthy&speed=0', theme: 'charcoal' });
add({ name: 'run-complete-observatory', q: 'scene=run-complete&speed=0', theme: 'observatory' });
add({ name: 'run-1280x800-observatory', q: 'scene=run&speed=0', theme: 'observatory', width: 1280, height: 800 });
add({ name: 'framing-1280x800-night-red', q: 'scene=framing&speed=0', theme: 'night-red', width: 1280, height: 800 });
add({ name: 'watch-1280x800-night-red', q: 'scene=run&speed=0&view=watch', theme: 'night-red', width: 1280, height: 800 });
add({ name: 'watch-dim30-night-red', q: 'scene=run&speed=0&view=watch&dim=30', theme: 'night-red' });
add({ name: 'watch-healthy-nocheck-night-red', q: 'scene=run-healthy&speed=0&view=watch&nocheck=1', theme: 'night-red' });
add({ name: 'palette-park-observatory', q: 'scene=run&speed=0&view=palette&q=park', theme: 'observatory', wait: 1600 });
add({
  name: 'palette-confirm-charcoal',
  q: 'scene=framing&speed=0&view=palette&q=park',
  theme: 'charcoal',
  wait: 1600,
  steps: [{ key: 'Enter' }, { wait: 300 }],
});
add({ name: 'palette-empty-night-red', q: 'scene=run&speed=0&view=palette', theme: 'night-red', wait: 1600 });
add({ name: 'attention-observatory', q: 'scene=run&speed=0&attention=open', theme: 'observatory' });
add({ name: 'attention-night-red', q: 'scene=run&speed=0&attention=open', theme: 'night-red' });
add({ name: 'arrange-charcoal', q: 'scene=run&speed=0&arrange=open', theme: 'charcoal', steps: [{ click: '[aria-label="Conditions card"] [role="radio"]:nth-child(2)' }, { wait: 300 }] });
add({ name: 'drawer-conditions-observatory', q: 'scene=run&speed=0&drawer=conditions', theme: 'observatory' });
add({ name: 'drawer-log-night-red', q: 'scene=framing&speed=0&drawer=log', theme: 'night-red' });
add({
  name: 'band-drag-observatory',
  q: 'scene=run&speed=0',
  theme: 'observatory',
  steps: [{ dragSep: ['.hsep', 0, -150, false] }, { wait: 400 }],
});
add({
  name: 'region-stats-observatory',
  q: 'scene=framing&speed=0',
  theme: 'observatory',
  steps: [{ press: 'r' }, { drag: [[0.36, 0.3], [0.5, 0.48]] }, { wait: 300 }, { hoverAt: [0.62, 0.42] }, { wait: 200 }],
});
add({
  name: 'hover-readout-run-observatory',
  q: 'scene=run&speed=0',
  theme: 'observatory',
  steps: [{ hoverAt: [0.48, 0.82] }, { wait: 250 }],
});
add({
  name: 'hold-park-charcoal',
  q: 'scene=run-complete&speed=0',
  theme: 'charcoal',
  steps: [{ holdOn: ['button[aria-label^="Park"]', 380] }],
});
add({ name: 'mode-switch-reduced-observatory', q: 'scene=run&speed=0&mode=focus&motion=reduced', theme: 'observatory' });
add({ name: 'section-plan-observatory', q: 'scene=run&speed=0&section=plan', theme: 'observatory', wait: 1200 });
add({ name: 'section-review-night-red', q: 'scene=run&speed=0&section=review', theme: 'night-red', wait: 1200 });
add({ name: 'comfortable-run-observatory', q: 'scene=run&speed=0&density=comfortable', theme: 'observatory' });
add({ name: 'run-live-observatory', q: 'scene=run&frame=146&speed=60', theme: 'observatory', wait: 9000 });

if (opt.list) {
  for (const s of SHOTS) console.log(s.name);
  process.exit(0);
}
if (!opt.out && !opt.audit) {
  console.error('capture.mjs: --out DIR is required');
  process.exit(2);
}
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars', '--autoplay-policy=user-gesture-required'],
});

async function auditRed(png) {
  const page = await browser.newPage();
  await page.setContent('<canvas id="c"></canvas>');
  const result = await page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.getElementById('c');
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    // strict: the research lab's test as is. tolerant: the same test with the
    // 8-bit quantisation (±0.5 per channel) given to the pixel, so the
    // anti-aliased edge of a --fg glyph (#d88f8f, G/R 0.66) at intensity
    // 10-25 is not counted; a grey or white pixel still is.
    let bad = 0;
    let badTolerant = 0;
    let maxGb = 0;
    const where = [];
    const worst = new Map();
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i];
      const gb = Math.max(d[i + 1], d[i + 2]);
      if (gb > 8 && gb > 0.68 * r) {
        bad++;
        if (gb > maxGb) maxGb = gb;
        const key = `rgb(${d[i]},${d[i + 1]},${d[i + 2]})`;
        worst.set(key, (worst.get(key) ?? 0) + 1);
        if (gb - 0.5 > 0.68 * (r + 0.5)) badTolerant++;
        const p = i / 4;
        if (where.length < 6) where.push([p % c.width, Math.floor(p / c.width)]);
      }
    }
    return {
      pixels: d.length / 4,
      nonRed: bad,
      nonRedTolerant: badTolerant,
      brightestOffender: maxGb,
      where,
      top: [...worst.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8),
    };
  }, png.toString('base64'));
  await page.close();
  return result;
}

async function shoot(shot) {
  // A fresh context per shot: the lab remembers layouts per mode in
  // localStorage, which must not leak from one shot into the next.
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  const log = { console: [], errors: [], external: [] };
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') log.console.push(`${m.type()}: ${m.text()}`);
  });
  page.on('pageerror', (e) => log.errors.push(String(e)));
  page.on('request', (r) => {
    const u = new URL(r.url());
    if (!['localhost', '127.0.0.1', '[::1]'].includes(u.hostname) && u.protocol.startsWith('http')) log.external.push(r.url());
  });
  const w = shot.width;
  const h = shot.height;
  await page.setViewport({ width: w, height: h, deviceScaleFactor: Number(opt.dpr) });
  const url = shot.url ?? `${opt.base}${P}?${shot.q}&theme=${shot.theme}`;
  await page.goto(url, { waitUntil: 'networkidle0' });
  await sleep(shot.wait);
  for (const step of shot.steps ?? []) {
    if (step.click) await page.click(step.click);
    if (step.key) await page.keyboard.press(step.key);
    if (step.press) await page.keyboard.press(step.press);
    if (step.wait) await sleep(step.wait);
    if (step.hoverAt) await page.mouse.move(w * step.hoverAt[0], h * step.hoverAt[1]);
    if (step.drag) {
      const [[x0, y0], [x1, y1]] = step.drag;
      await page.mouse.move(w * x0, h * y0);
      await page.mouse.down();
      for (let i = 1; i <= 8; i++) await page.mouse.move(w * (x0 + ((x1 - x0) * i) / 8), h * (y0 + ((y1 - y0) * i) / 8));
      await page.mouse.up();
    }
    if (step.dragSep) {
      const [sel, dx, dy, release] = step.dragSep;
      const box = await (await page.$(sel)).boundingBox();
      const x = box.x + box.width / 2;
      const y = box.y + box.height / 2;
      await page.mouse.move(x, y);
      await page.mouse.down();
      for (let i = 1; i <= 8; i++) await page.mouse.move(x + (dx * i) / 8, y + (dy * i) / 8);
      await sleep(400);
      if (release) await page.mouse.up();
    }
    if (step.holdOn) {
      const [sel, ms] = step.holdOn;
      const box = await (await page.$(sel)).boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await sleep(ms);
    }
  }
  const file = path.join(opt.out, `${shot.name}.png`);
  const png = await page.screenshot({ path: file });
  const facts = await page.evaluate(() => {
    const q = (s) => document.querySelector(s)?.getBoundingClientRect();
    const v = q('.viewer-cell');
    const b = q('.band-cell');
    const rail = q('.panel');
    return {
      viewer: v ? [Math.round(v.width), Math.round(v.height)] : null,
      band: b ? Math.round(b.height) : null,
      rail: rail ? Math.round(rail.width) : null,
      seq: document.querySelector('[data-frame-seq]')?.getAttribute('data-frame-seq') ?? null,
    };
  });
  const entry = { name: shot.name, file, ...log, facts };
  if (shot.theme === 'night-red') entry.nightRedAudit = await auditRed(png);
  await context.close();
  return entry;
}

if (opt.audit) {
  for (const f of positionals) console.log(path.basename(f), JSON.stringify(await auditRed(fs.readFileSync(f))));
  await browser.close();
  process.exit(0);
}
fs.mkdirSync(opt.out, { recursive: true });

const report = [];
if (opt.url) {
  const u = opt.url.startsWith('http') ? opt.url : `${opt.base}${opt.url}`;
  const theme = new URL(u).searchParams.get('theme') ?? 'observatory';
  report.push(await shoot({ name: opt.name, url: u, theme, wait: 2200, width: Number(opt.width), height: Number(opt.height) }));
} else {
  const only = opt.only ? new Set(opt.only.split(',')) : null;
  for (const shot of SHOTS) {
    if (only && !only.has(shot.name)) continue;
    report.push(await shoot(shot));
  }
}
for (const e of report) {
  const a = e.nightRedAudit;
  const audit = a ? ` nonRed strict=${a.nonRed} tolerant=${a.nonRedTolerant}${a.nonRed ? ` max(G,B)=${a.brightestOffender} ` + JSON.stringify(a.top.slice(0, 3)) : ''}` : '';
  console.log(`[capture] ${e.name}: errors=${e.errors.length} console=${e.console.length} external=${e.external.length}${audit} ${JSON.stringify(e.facts)}`);
  for (const m of [...e.errors, ...e.console].slice(0, 4)) console.log('   ', m.slice(0, 300));
}
fs.writeFileSync(path.join(opt.out, opt.url ? `${opt.name}.report.json` : 'report.json'), JSON.stringify(report, null, 2));
await browser.close();
