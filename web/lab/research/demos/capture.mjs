#!/usr/bin/env node
/**
 * Screenshots of the lab research page in headless Chrome (puppeteer-core,
 * system Chrome), with a Night Red audit of every Night Red shot.
 *
 *   cd web && npx vite --port 5201 --strictPort      # terminal 1
 *   node lab/research/demos/capture.mjs --out /tmp/shots [--only curve-observatory,...] [--list]
 *
 * Night Red audit: the PNG is decoded in the browser and every pixel is
 * checked: a pixel "emits non-red light" when max(G, B) > 8 and
 * max(G, B) > 0.68 x R. 0.68 is just above the greenest Night Red token
 * (--fg #d88f8f, G/R = 0.66); antialiasing between two tokens stays inside
 * that bound. Offending pixels are counted and the worst ones listed.
 *
 * Output: <name>.png per shot and report.json (console errors, page errors,
 * non-local requests, audit, page facts read from [data-lab-facts]).
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import puppeteer from 'puppeteer-core';

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const { values: opt } = parseArgs({
  options: {
    base: { type: 'string', default: 'http://localhost:5201/lab/research.html' },
    out: { type: 'string' },
    only: { type: 'string' },
    list: { type: 'boolean', default: false },
    dpr: { type: 'string', default: '1' },
  },
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** The shot list: demo, theme, size, settle time, optional steps. */
const SHOTS = [];
const THEMES = ['observatory', 'charcoal', 'night-red'];
for (const theme of THEMES) {
  SHOTS.push({ name: `curve-${theme}`, demo: 'curve', theme, wait: 2600 });
  SHOTS.push({ name: `frame-${theme}`, demo: 'frame', theme, wait: 3500 });
  SHOTS.push({ name: `motion-${theme}`, demo: 'motion', theme, wait: 1200 });
  SHOTS.push({ name: `space-${theme}`, demo: 'space', theme, wait: 1200 });
  SHOTS.push({ name: `popover-${theme}`, demo: 'popover', theme, wait: 1200, steps: [{ click: '[data-shot="open-popover"]' }, { wait: 500 }] });
  SHOTS.push({ name: `table-${theme}`, demo: 'table', theme, wait: 1200, steps: [{ type: ['[data-shot="filter"]', 'cloud'] }, { wait: 400 }] });
  SHOTS.push({ name: `support-${theme}`, demo: 'support', theme, wait: 14000 });
}
SHOTS.push({ name: 'curve-1280x800-observatory', demo: 'curve', theme: 'observatory', width: 1280, height: 800, wait: 2600 });
SHOTS.push({ name: 'frame-1280x800-observatory', demo: 'frame', theme: 'observatory', width: 1280, height: 800, wait: 3500 });
SHOTS.push({ name: 'space-1280x800-observatory', demo: 'space', theme: 'observatory', width: 1280, height: 800, wait: 1200 });
SHOTS.push({
  name: 'curve-zoomed-observatory',
  demo: 'curve',
  theme: 'observatory',
  wait: 1500,
  steps: [{ eval: 'window.__lab?.zoomCurve?.()' }, { wait: 2500 }, { hoverAt: [0.62, 0.42] }, { wait: 300 }],
});
SHOTS.push({
  name: 'curve-night-observatory',
  demo: 'curve',
  theme: 'observatory',
  wait: 800,
  steps: [{ click: '[data-shot="load-night"]' }, { wait: 1200 }, { hoverAt: [0.45, 0.3] }, { wait: 300 }],
});
SHOTS.push({
  name: 'frame-zoomed-observatory',
  demo: 'frame',
  theme: 'observatory',
  wait: 2500,
  steps: [{ wheelAt: [0.42, 0.45, -900] }, { wait: 1800 }],
});
SHOTS.push({ name: 'frame-fire-observatory', demo: 'frame', theme: 'observatory', wait: 2500, steps: [{ click: '[data-shot="palette-fire"]' }, { wait: 1500 }] });
SHOTS.push({ name: 'frame-ice-charcoal', demo: 'frame', theme: 'charcoal', wait: 2500, steps: [{ click: '[data-shot="palette-ice"]' }, { wait: 1500 }] });
SHOTS.push({
  name: 'curve-season-observatory',
  demo: 'curve',
  theme: 'observatory',
  wait: 800,
  steps: [{ click: '[data-shot="load-season"]' }, { wait: 2500 }],
});
SHOTS.push({
  name: 'curve-threshold-night-red',
  demo: 'curve',
  theme: 'night-red',
  wait: 800,
  steps: [{ click: '[data-shot="load-night"]' }, { wait: 800 }, { eval: 'window.__lab?.setThreshold?.(2.45)' }, { wait: 1200 }, { hoverAt: [0.5, 0.88] }, { wait: 300 }],
});
SHOTS.push({ name: 'space-rail-580-observatory', demo: 'space', theme: 'observatory', wait: 800, steps: [{ click: '[data-shot="rail-580"]' }, { wait: 600 }] });
SHOTS.push({ name: 'space-drawer-tall-charcoal', demo: 'space', theme: 'charcoal', wait: 800, steps: [{ click: '[data-shot="drawer-tall"]' }, { wait: 600 }] });
SHOTS.push({ name: 'popover-fallback-observatory', demo: 'popover', theme: 'observatory', wait: 800, steps: [{ click: '[data-shot="force-fallback"]' }, { click: '[data-shot="open-popover"]' }, { wait: 500 }] });
SHOTS.push({ name: 'motion-reduced-observatory', demo: 'motion', theme: 'observatory', motion: 'reduced', wait: 800, steps: [{ click: '[data-shot="auto-stretch"]' }, { wait: 60 }] });
SHOTS.push({ name: 'motion-ghost-observatory', demo: 'motion', theme: 'observatory', wait: 800, steps: [{ click: '[data-shot="auto-stretch"]' }, { wait: 90 }] });

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
  // Metal (GPU) by default, like the recorded Chromium column; CAPTURE_GL=swiftshader for a CPU run.
  args:
    process.env.CAPTURE_GL === 'swiftshader'
      ? ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--hide-scrollbars']
      : ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars'],
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
    const top = [...worst.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    return { pixels: d.length / 4, nonRed: bad, top };
  }, png.toString('base64'));
  await page.close();
  return result;
}

const report = [];
for (const shot of SHOTS) {
  if (only && !only.has(shot.name)) continue;
  const page = await browser.newPage();
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
  if (shot.motion) url.searchParams.set('motion', shot.motion);
  await page.goto(url.href, { waitUntil: 'networkidle0' });
  await sleep(shot.wait ?? 1000);
  for (const step of shot.steps ?? []) {
    if (step.click) await page.click(step.click);
    if (step.type) await page.type(step.type[0], step.type[1]);
    if (step.wait) await sleep(step.wait);
    if (step.eval) await page.evaluate(step.eval);
    if (step.hoverAt) await page.mouse.move(w * step.hoverAt[0], h * step.hoverAt[1]);
    if (step.wheelAt) {
      await page.mouse.move(w * step.wheelAt[0], h * step.wheelAt[1]);
      for (let i = 0; i < 6; i++) {
        await page.mouse.wheel({ deltaY: step.wheelAt[2] / 6 });
        await sleep(30);
      }
    }
  }
  const file = path.join(opt.out, `${shot.name}.png`);
  const png = await page.screenshot({ path: file });
  const facts = await page.evaluate(() => {
    const el = document.querySelector('[data-lab-facts]');
    return el ? el.getAttribute('data-lab-facts') : null;
  });
  const entry = { name: shot.name, file, ...log, facts: facts ? JSON.parse(facts) : null };
  if (shot.theme === 'night-red') entry.nightRedAudit = await auditRed(png);
  report.push(entry);
  const audit = entry.nightRedAudit ? ` nonRed=${entry.nightRedAudit.nonRed}` : '';
  console.log(`[capture] ${shot.name}: errors=${log.errors.length} console=${log.console.length} external=${log.external.length}${audit}`);
  await page.close();
}

fs.writeFileSync(path.join(opt.out, 'report.json'), JSON.stringify(report, null, 2));
await browser.close();
