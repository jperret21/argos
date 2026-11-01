#!/usr/bin/env node
/**
 * Screenshots of the chart lab in headless Chrome (puppeteer-core, system
 * Chrome), with the Night Red audit of the research lab on every Night Red
 * shot: a pixel "emits non-red light" when max(G, B) > 8 and
 * max(G, B) > 0.68 x R (0.68 is just above --fg #d88f8f, G/R = 0.66).
 *
 *   cd web && npx vite --port 5203 --strictPort                 # terminal 1
 *   node src/lab/charts/capture.mjs --out DIR [--only a,b] [--list]
 *
 * The simulated clock is paused at a fixed moment (?t=…&paused=1) so every
 * shot is reproducible. Output: <name>.png and report.json (console errors,
 * page errors, non-local requests, audit, facts from [data-lab-facts]).
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import puppeteer from 'puppeteer-core';

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const { values: opt } = parseArgs({
  options: {
    base: { type: 'string', default: 'http://localhost:5203/lab/charts.html' },
    out: { type: 'string' },
    only: { type: 'string' },
    list: { type: 'boolean', default: false },
    dpr: { type: 'string', default: '1' },
  },
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const THEMES = ['observatory', 'charcoal', 'night-red'];

/** demo, theme, query params, size, settle time, steps. */
const SHOTS = [];
const at = (t) => ({ t, paused: '1' });

for (const theme of THEMES) {
  SHOTS.push({ name: `curve-${theme}`, demo: 'curve', theme, q: at('22:41:07'), wait: 1500 });
  SHOTS.push({ name: `wall-${theme}`, demo: 'wall', theme, q: at('02:20'), wait: 1500 });
  SHOTS.push({ name: `vcurve-${theme}`, demo: 'vcurve', theme, q: { ...at('22:41:07'), af: 'done' }, wait: 1500 });
  SHOTS.push({ name: `conditions-${theme}`, demo: 'conditions', theme, q: at('22:41:07'), wait: 1500 });
  SHOTS.push({ name: `visibility-${theme}`, demo: 'visibility', theme, q: at('22:41:07'), wait: 1500 });
  SHOTS.push({ name: `histogram-${theme}`, demo: 'histogram', theme, q: at('22:41:07'), wait: 1500 });
  SHOTS.push({ name: `mini-${theme}`, demo: 'mini', theme, q: at('22:41:07'), wait: 1500 });
  SHOTS.push({ name: `context-${theme}`, demo: 'context', theme, q: { ...at('22:41:07'), chrome: '0' }, wait: 1800 });
}

// Interaction states.
SHOTS.push({
  name: 'curve-hover-zoomed-observatory',
  demo: 'curve',
  theme: 'observatory',
  q: at('22:41:07'),
  wait: 1200,
  steps: [
    { eval: 'window.__lc?.zoomTo(Date.UTC(2026,10,1,20,40)/1000, Date.UTC(2026,10,1,22,10)/1000)' },
    { wait: 400 },
    { eval: "window.__lc?.select(150)" },
    { hoverIn: ['.facet:nth-of-type(1) .u-over', 0.58, 0.45] },
    { wait: 300 },
  ],
});
SHOTS.push({
  name: 'curve-drag-zoom-observatory',
  demo: 'curve',
  theme: 'observatory',
  q: at('22:41:07'),
  wait: 1200,
  steps: [{ dragIn: ['.facet:nth-of-type(2) .u-over', 0.3, 0.5, 0.55, 0.5, true] }, { wait: 200 }],
});
SHOTS.push({
  name: 'curve-bjd-follow-charcoal',
  demo: 'curve',
  theme: 'charcoal',
  q: { t: '22:41:07', speed: '600' },
  wait: 1000,
  steps: [{ click: '[aria-label="Time axis"] button:nth-child(3)' }, { click: '[aria-label="Follow the newest frame"]' }, { wait: 2500 }, { hoverIn: ['.facet:nth-of-type(1) .u-over', 0.82, 0.3] }, { wait: 300 }],
});
SHOTS.push({
  name: 'curve-legend-export-charcoal',
  demo: 'curve',
  theme: 'charcoal',
  q: at('22:41:07'),
  wait: 1200,
  steps: [
    { click: '.facet:nth-of-type(1) .legend button:nth-of-type(2)' },
    { click: '.facet:nth-of-type(2) .legend button:nth-of-type(2)' },
    { click: '[data-shot="export-png"]' },
    { wait: 700 },
    { hoverIn: ['.facet:nth-of-type(1) .u-over', 0.9, 0.2] },
    { wait: 300 },
  ],
});
SHOTS.push({ name: 'curve-band-observatory', demo: 'curve', theme: 'observatory', q: { ...at('22:41:07'), frame: 'band' }, wait: 1500 });
SHOTS.push({ name: 'curve-band-night-red', demo: 'curve', theme: 'night-red', q: { ...at('22:41:07'), frame: 'band' }, wait: 1500 });
SHOTS.push({ name: 'curve-drawer-observatory', demo: 'curve', theme: 'observatory', q: { ...at('22:41:07'), frame: 'drawer' }, wait: 1500 });
SHOTS.push({ name: 'curve-stress-observatory', demo: 'curve', theme: 'observatory', q: { t: '22:41:07', source: 'stress' }, wait: 12000 });
SHOTS.push({ name: 'curve-1280x800-observatory', demo: 'curve', theme: 'observatory', q: at('22:41:07'), width: 1280, height: 800, wait: 1500 });
SHOTS.push({
  name: 'wall-selected-expanded-observatory',
  demo: 'wall',
  theme: 'observatory',
  q: at('02:20'),
  wait: 1200,
  steps: [{ eval: 'window.__wall?.select(212)' }, { eval: "window.__wall?.expand('C4')" }, { wait: 300 }, { hoverIn: ['.cell .u-over', 0.4, 0.5] }, { wait: 300 }],
});
SHOTS.push({ name: 'wall-1280x800-night-red', demo: 'wall', theme: 'night-red', q: at('02:20'), width: 1280, height: 800, wait: 1500 });
SHOTS.push({ name: 'vcurve-building-observatory', demo: 'vcurve', theme: 'observatory', q: { ...at('22:41:07'), af: 'step-11' }, wait: 1500 });
SHOTS.push({ name: 'vcurve-rejected-charcoal', demo: 'vcurve', theme: 'charcoal', q: { ...at('22:41:07'), af: 'done', scenario: 'flat' }, wait: 1500 });
SHOTS.push({ name: 'vcurve-noisy-night-red', demo: 'vcurve', theme: 'night-red', q: { ...at('22:41:07'), af: 'done', scenario: 'seeing' }, wait: 1500 });
SHOTS.push({ name: 'conditions-stalled-observatory', demo: 'conditions', theme: 'observatory', q: { t: '22:41:07', stalled: '1', speed: '60' }, wait: 4500 });
SHOTS.push({ name: 'conditions-1280x800-charcoal', demo: 'conditions', theme: 'charcoal', q: at('22:41:07'), width: 1280, height: 800, wait: 1500 });
SHOTS.push({ name: 'visibility-rrlyr-observatory', demo: 'visibility', theme: 'observatory', q: { ...at('22:41:07'), target: 'rrlyr' }, wait: 1500 });
SHOTS.push({ name: 'histogram-full-observatory', demo: 'histogram', theme: 'observatory', q: { ...at('22:41:07'), range: 'full' }, wait: 1500 });
SHOTS.push({ name: 'histogram-focus-handle-charcoal', demo: 'histogram', theme: 'charcoal', q: at('22:41:07'), wait: 1200, steps: [{ focus: '[data-shot="handle-white"]' }, { key: 'ArrowLeft' }, { key: 'ArrowLeft' }, { wait: 300 }] });
SHOTS.push({ name: 'mini-1280x800-observatory', demo: 'mini', theme: 'observatory', q: at('22:41:07'), width: 1280, height: 800, wait: 1500 });
SHOTS.push({ name: 'context-1280x800-observatory', demo: 'context', theme: 'observatory', q: { ...at('22:41:07'), chrome: '0' }, width: 1280, height: 800, wait: 1800 });
SHOTS.push({ name: 'curve-reduced-motion-observatory', demo: 'curve', theme: 'observatory', q: { ...at('22:41:07'), motion: 'reduced' }, wait: 1200, steps: [{ focus: '.lc' }, { key: '+' }, { wait: 40 }] });

if (opt.list) {
  for (const s of SHOTS) console.log(s.name);
  process.exit(0);
}
if (!opt.out) {
  console.error('capture.mjs: --out DIR is required');
  process.exit(2);
}
const only = opt.only ? new Set(opt.only.split(',')) : null;
fs.mkdirSync(opt.out, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars', '--force-color-profile=srgb'],
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
    let bad = 0;
    const worst = new Map();
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i];
      const gb = Math.max(d[i + 1], d[i + 2]);
      if (gb > 8 && gb > 0.68 * r) {
        bad++;
        const key = `rgb(${d[i]},${d[i + 1]},${d[i + 2]})`;
        worst.set(key, (worst.get(key) ?? 0) + 1);
      }
    }
    return { pixels: d.length / 4, nonRed: bad, top: [...worst.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8) };
  }, png.toString('base64'));
  await page.close();
  return result;
}

async function boxOf(page, sel) {
  const el = await page.$(sel);
  if (!el) throw new Error(`no element ${sel}`);
  return el.boundingBox();
}

const report = [];
for (const shot of SHOTS) {
  if (only && !only.has(shot.name)) continue;
  const page = await browser.newPage();
  // The export hooks would download into ~/Downloads: deny downloads (the toast still shows the result).
  const cdp = await page.createCDPSession();
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'deny' }).catch(() => cdp.send('Page.setDownloadBehavior', { behavior: 'deny' }));
  const log = { console: [], errors: [], external: [] };
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') log.console.push(`${m.type()}: ${m.text()}`);
  });
  page.on('pageerror', (e) => log.errors.push(String(e)));
  page.on('request', (r) => {
    const u = new URL(r.url());
    if (!['localhost', '127.0.0.1'].includes(u.hostname) && u.protocol.startsWith('http')) log.external.push(r.url());
  });
  const w = shot.width ?? 1440;
  const h = shot.height ?? 900;
  await page.setViewport({ width: w, height: h, deviceScaleFactor: Number(opt.dpr) });
  const url = new URL(opt.base);
  url.searchParams.set('demo', shot.demo);
  url.searchParams.set('theme', shot.theme);
  for (const [k, v] of Object.entries(shot.q ?? {})) url.searchParams.set(k, v);
  await page.goto(url.href, { waitUntil: 'networkidle0' });
  await page.evaluate(() => document.fonts.ready);
  await sleep(shot.wait ?? 1000);
  for (const step of shot.steps ?? []) {
    if (step.click) await page.click(step.click);
    if (step.focus) await page.focus(step.focus);
    if (step.key) await page.keyboard.press(step.key);
    if (step.wait) await sleep(step.wait);
    if (step.eval) await page.evaluate(step.eval);
    if (step.hoverIn) {
      const b = await boxOf(page, step.hoverIn[0]);
      await page.mouse.move(b.x + b.width * step.hoverIn[1], b.y + b.height * step.hoverIn[2]);
    }
    if (step.dragIn) {
      const [sel, x0, y0, x1, y1, hold] = step.dragIn;
      const b = await boxOf(page, sel);
      await page.mouse.move(b.x + b.width * x0, b.y + b.height * y0);
      await page.mouse.down();
      for (let k = 1; k <= 8; k++) await page.mouse.move(b.x + b.width * (x0 + ((x1 - x0) * k) / 8), b.y + b.height * (y0 + ((y1 - y0) * k) / 8));
      if (!hold) await page.mouse.up();
    }
  }
  const file = path.join(opt.out, `${shot.name}.png`);
  const png = await page.screenshot({ path: file });
  const facts = await page.evaluate(() => {
    const el = document.querySelector('[data-lab-facts]');
    const v = el?.getAttribute('data-lab-facts');
    return v ? v : null;
  });
  const entry = { name: shot.name, file, ...log, facts: facts ? JSON.parse(facts) : null };
  if (shot.theme === 'night-red') entry.nightRedAudit = await auditRed(png);
  report.push(entry);
  const audit = entry.nightRedAudit ? ` nonRed=${entry.nightRedAudit.nonRed}` : '';
  console.log(`[capture] ${shot.name}: errors=${log.errors.length} console=${log.console.length} external=${log.external.length}${audit}`);
  for (const e of [...log.errors, ...log.console].slice(0, 3)) console.log(`   ${e.slice(0, 300)}`);
  await page.close();
}

fs.writeFileSync(path.join(opt.out, 'report.json'), JSON.stringify(report, null, 2));
await browser.close();
