#!/usr/bin/env node
/**
 * Screenshots of the controls lab in headless Chrome (puppeteer-core, the
 * system Chrome), with a Night Red audit of every Night Red shot.
 *
 *   cd web && npx vite --port 5202 --strictPort                 # terminal 1
 *   node src/lab/controls/capture.mjs --out DIR [--only a,b] [--list]
 *
 * Interaction states are produced by real input (mouse down and held on a
 * hold button, keys held for the key hints, a drag on a slider), so the
 * shots also exercise the code paths.
 *
 * Night Red audit (same rule as the research lab): a pixel "emits non-red
 * light" when max(G, B) > 8 and max(G, B) > 0.68 x R. 0.68 is just above
 * the greenest Night Red token (--fg #d88f8f, G/R = 0.66).
 *
 * Output: <name>.png and report.json (console errors, page errors,
 * non-local requests, audit).
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import puppeteer from 'puppeteer-core';

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const { values: opt } = parseArgs({
  options: {
    base: { type: 'string', default: 'http://localhost:5202/lab/controls.html' },
    out: { type: 'string' },
    only: { type: 'string' },
    list: { type: 'boolean', default: false },
    dpr: { type: 'string', default: '1' },
    audit: { type: 'string' },
  },
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const THEMES = ['observatory', 'charcoal', 'night-red'];
const MOD = 'Meta'; // headless Chrome on macOS reports a Mac platform

/** name, plate, theme, size, wait, steps, query extras. */
const SHOTS = [];
for (const theme of THEMES) {
  SHOTS.push({ name: `buttons-${theme}`, plate: 'buttons', theme, wait: 900 });
  SHOTS.push({ name: `toolbar-${theme}`, plate: 'toolbar', theme, wait: 900 });
  SHOTS.push({ name: `values-${theme}`, plate: 'values', theme, wait: 900 });
  SHOTS.push({ name: `focuser-${theme}`, plate: 'focuser', theme, wait: 900 });
  SHOTS.push({ name: `mount-${theme}`, plate: 'mount', theme, wait: 900 });
  SHOTS.push({ name: `confirm-${theme}`, plate: 'confirm', theme, wait: 900 });
  SHOTS.push({ name: `status-${theme}`, plate: 'status', theme, wait: 900 });
}
for (const plate of ['buttons', 'toolbar', 'values', 'focuser', 'mount', 'confirm', 'status']) {
  SHOTS.push({ name: `${plate}-1280x800-observatory`, plate, theme: 'observatory', width: 1280, height: 800, wait: 900 });
}

// Interaction states (real input).
SHOTS.push({
  name: 'toolbar-hints-held-observatory',
  plate: 'toolbar',
  theme: 'observatory',
  wait: 700,
  steps: [{ keydown: MOD }, { wait: 800 }],
  after: [{ keyup: MOD }],
});
SHOTS.push({
  name: 'toolbar-hints-held-night-red',
  plate: 'toolbar',
  theme: 'night-red',
  wait: 700,
  steps: [{ keydown: MOD }, { wait: 800 }],
  after: [{ keyup: MOD }],
});
SHOTS.push({
  name: 'toolbar-overflow-menu-charcoal',
  plate: 'toolbar',
  theme: 'charcoal',
  wait: 700,
  steps: [{ click: '[data-shot="narrow"] button[aria-haspopup="menu"][aria-label$="more tools"]' }, { wait: 400 }],
});
SHOTS.push({
  name: 'toolbar-split-menu-night-red',
  plate: 'toolbar',
  theme: 'night-red',
  wait: 700,
  steps: [{ click: '[data-shot="full"] button[aria-label="Take one exposure options"]' }, { wait: 400 }],
});
SHOTS.push({
  name: 'confirm-holding-observatory',
  plate: 'confirm',
  theme: 'observatory',
  wait: 700,
  steps: [{ downOn: '[data-shot="hold-live"] button.ctl' }, { wait: 380 }],
  after: [{ up: true }],
});
SHOTS.push({
  name: 'confirm-holding-night-red',
  plate: 'confirm',
  theme: 'night-red',
  wait: 700,
  steps: [{ downOn: '[data-shot="hold-live"] button.ctl' }, { wait: 380 }],
  after: [{ up: true }],
});
SHOTS.push({
  name: 'confirm-keyboard-inline-charcoal',
  plate: 'confirm',
  theme: 'charcoal',
  wait: 700,
  steps: [{ focus: '[data-shot="hold-live"] button.ctl' }, { press: 'Enter' }, { wait: 400 }],
});
SHOTS.push({
  name: 'mount-jogging-armed-observatory',
  plate: 'mount',
  theme: 'observatory',
  wait: 700,
  steps: [{ press: 'j' }, { keydown: 'ArrowUp' }, { keydown: 'ArrowRight' }, { wait: 1500 }],
  after: [{ keyup: 'ArrowUp' }, { keyup: 'ArrowRight' }],
});
SHOTS.push({
  name: 'mount-deadman-stop-night-red',
  plate: 'mount',
  theme: 'night-red',
  wait: 700,
  steps: [{ click: '[data-shot="link-loss"] button' }, { downOn: '[data-shot="jog-live"] button[aria-label="Jog Altitude +"]' }, { wait: 1700 }],
  after: [{ up: true }],
});
SHOTS.push({
  name: 'values-slider-fine-drag-observatory',
  plate: 'values',
  theme: 'observatory',
  wait: 700,
  steps: [{ dragOn: ['[data-shot="slider-live"] .track', 0.62, 0.5, 0.7, 0.5, 'Alt'] }, { wait: 200 }],
  after: [{ up: true }, { keyup: 'Alt' }],
});
SHOTS.push({
  name: 'values-scrub-exposure-charcoal',
  plate: 'values',
  theme: 'charcoal',
  wait: 700,
  steps: [{ dragOn: ['[data-shot="scrub-live"] .key', 0.3, 0.5, 2.6, 0.5, null] }, { wait: 200 }],
  after: [{ up: true }],
});
SHOTS.push({
  name: 'focuser-moving-observatory',
  plate: 'focuser',
  theme: 'observatory',
  wait: 700,
  steps: [
    { click: '[data-shot="focuser-live"] [role="radiogroup"] [role="radio"]:last-child' },
    { click: '[data-shot="focuser-live"] button[aria-label="Focus in"]' },
    { wait: 150 },
    { click: '[data-shot="focuser-live"] button[aria-label="Focus in"]' },
    { wait: 120 },
    { click: '[data-shot="focuser-live"] button[aria-label="Focus in"]' },
    { wait: 600 },
  ],
});
SHOTS.push({
  name: 'focuser-autofocus-night-red',
  plate: 'focuser',
  theme: 'night-red',
  wait: 700,
  steps: [{ click: '[data-shot="focuser-live"] button.ctl:has(.text)' }, { wait: 5200 }],
});
SHOTS.push({ name: 'buttons-reduced-motion-observatory', plate: 'buttons', theme: 'observatory', motion: 'reduced', wait: 1500 });
SHOTS.push({
  name: 'status-tip-reason-observatory',
  plate: 'status',
  theme: 'observatory',
  wait: 700,
  steps: [{ downOn: '[data-shot="press-reason"] button[aria-disabled="true"]' }, { wait: 250 }],
  after: [{ up: true }],
});

async function audit(page, png) {
  const b64 = png.toString('base64');
  return page.evaluate(async (data) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let bad = 0;
    const worst = [];
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i];
      const gb = Math.max(d[i + 1], d[i + 2]);
      if (gb > 8 && gb > 0.68 * r) {
        bad++;
        if (worst.length < 8) {
          const p = i / 4;
          worst.push({ x: p % c.width, y: Math.floor(p / c.width), rgb: [r, d[i + 1], d[i + 2]] });
        }
      }
    }
    return { pixels: c.width * c.height, nonRed: bad, worst };
  }, b64);
}

/** --audit a.png,b.png: Night Red audit of existing PNGs (e.g. WKWebView shots). */
async function auditFiles(files) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  try {
    const page = await browser.newPage();
    for (const f of files) {
      const a = await audit(page, fs.readFileSync(f));
      console.log(`${path.basename(f)} nonRed=${a.nonRed} of ${a.pixels}${a.worst.length ? ` worst ${JSON.stringify(a.worst.slice(0, 3))}` : ''}`);
    }
  } finally {
    await browser.close();
  }
}

async function run() {
  if (opt.audit) return auditFiles(opt.audit.split(','));
  if (opt.list) {
    for (const s of SHOTS) console.log(s.name);
    return;
  }
  if (!opt.out) throw new Error('--out DIR is required');
  fs.mkdirSync(opt.out, { recursive: true });
  const only = opt.only ? new Set(opt.only.split(',')) : null;
  const shots = SHOTS.filter((s) => !only || only.has(s.name));
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--force-color-profile=srgb', '--hide-scrollbars', '--font-render-hinting=none'],
  });
  const report = { shots: [] };
  try {
    for (const s of shots) {
      const page = await browser.newPage();
      const log = { console: [], errors: [], remote: [] };
      page.on('console', (m) => {
        if (m.type() === 'error' || m.type() === 'warning') log.console.push(`${m.type()}: ${m.text()}`);
      });
      page.on('pageerror', (e) => log.errors.push(String(e)));
      page.on('request', (r) => {
        const u = r.url();
        if (!u.startsWith('http://localhost') && !u.startsWith('data:') && !u.startsWith('blob:')) log.remote.push(u);
      });
      await page.setViewport({ width: s.width ?? 1440, height: s.height ?? 900, deviceScaleFactor: Number(opt.dpr) });
      if (s.motion === 'reduced') await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
      const q = new URLSearchParams({ plate: s.plate, theme: s.theme, ...(s.query ?? {}) });
      await page.goto(`${opt.base}?${q}`, { waitUntil: 'networkidle0' });
      await page.evaluate(() => document.fonts.ready);
      await sleep(s.wait ?? 600);
      for (const st of s.steps ?? []) await step(page, st);
      const file = path.join(opt.out, `${s.name}.png`);
      const png = await page.screenshot({ path: file, type: 'png' });
      for (const st of s.after ?? []) await step(page, st);
      const entry = { name: s.name, file, ...log };
      if (s.theme === 'night-red') entry.audit = await audit(page, png);
      report.shots.push(entry);
      const a = entry.audit ? ` audit nonRed=${entry.audit.nonRed}` : '';
      console.log(`${s.name}${a}${log.errors.length ? ` ERRORS ${log.errors.length}` : ''}${log.console.length ? ` console ${log.console.length}` : ''}`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(opt.out, 'report.json'), JSON.stringify(report, null, 2));
}

async function centerOf(page, sel, fx = 0.5, fy = 0.5) {
  const el = await page.$(sel);
  if (!el) throw new Error(`no element ${sel}`);
  const box = await el.boundingBox();
  return { x: box.x + box.width * fx, y: box.y + box.height * fy };
}

async function step(page, st) {
  if (st.wait) return sleep(st.wait);
  if (st.click) return page.click(st.click);
  if (st.focus) return page.focus(st.focus);
  if (st.press) return page.keyboard.press(st.press);
  if (st.keydown) return page.keyboard.down(st.keydown);
  if (st.keyup) return page.keyboard.up(st.keyup);
  if (st.eval) return page.evaluate(st.eval);
  if (st.hover) return page.hover(st.hover);
  if (st.downOn) {
    const p = await centerOf(page, st.downOn);
    await page.mouse.move(p.x, p.y);
    return page.mouse.down();
  }
  if (st.up) return page.mouse.up();
  if (st.dragOn) {
    const [sel, fx0, fy0, fx1, fy1, mod] = st.dragOn;
    const a = await centerOf(page, sel, fx0, fy0);
    const b = await centerOf(page, sel, fx1, fy1);
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    if (mod) await page.keyboard.down(mod);
    const n = 12;
    for (let i = 1; i <= n; i++) {
      await page.mouse.move(a.x + ((b.x - a.x) * i) / n, a.y + ((b.y - a.y) * i) / n);
      await sleep(16);
    }
    return;
  }
  throw new Error(`unknown step ${JSON.stringify(st)}`);
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
