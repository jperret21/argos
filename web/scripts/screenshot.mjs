#!/usr/bin/env node
/**
 * Screenshots of the ARGOS web UI in headless Chrome, for reviews and docs.
 *
 * Needs: the ARGOS server and the Vite dev server (or `npm run preview`)
 * running, Google Chrome installed (puppeteer-core never downloads a browser),
 * and `npm install` done in web/. WebGL2 runs on SwiftShader in headless mode,
 * so the image viewer renders on any machine.
 *
 *   # terminal 1 (repo root)
 *   .venv/bin/python -m argos.server --simulator --dev-token dev
 *   # terminal 2 (web/)
 *   npm run dev
 *   # terminal 3 (web/)
 *   node scripts/screenshot.mjs --out /tmp/shots --themes observatory,charcoal,night-red --live
 *
 * Options
 *   --url URL         page to open (default http://localhost:5173/). ?api= and
 *                     ?token= are added from --api / --token when missing.
 *   --api URL         ARGOS server (default: the page's ?api=, else http://127.0.0.1:8742)
 *   --token TOKEN     server token (default: the page's ?token=, else "dev")
 *   --out DIR         output folder, created if needed (required)
 *   --themes LIST     comma list of observatory, charcoal, night-red (default observatory).
 *                     The theme is stored in localStorage before the page loads, so
 *                     the real "apply before first paint" path is exercised.
 *   --live            through the API: connect the simulator if needed and start live
 *                     view, then before each shot wait until a NEW frame is on screen
 *   --exposure S      live-view exposure in seconds (default 1)
 *   --gain G          live-view gain (default 80)
 *   --slew "RA DEC"   unpark if parked, GoTo RA (decimal hours) / Dec (decimal degrees),
 *                     e.g. --slew "5.5881 -5.3911"; each shot waits for "slewing"
 *   --section NAME    rail section to show: connection, imaging, sequencer, analyze,
 *                     configuration (clicks the rail entry; default imaging)
 *   --click LABEL     click the button whose aria-label (or, failing that, visible
 *                     text) is LABEL before the shot, e.g. "Levels strip (histogram)"
 *                     or "Mount" (a card's fold button); repeatable, in order
 *   --log-open        open the activity log drawer before the shot
 *   --pref KEY=JSON   localStorage preference set before the page loads, repeatable,
 *                     e.g. --pref argos.rail-open=false --pref 'argos.fit-mode="fill"'
 *   --name PREFIX     file name prefix (default "argos"): PREFIX-THEME.png
 *   --width W --height H --dpr D   viewport (default 1440 x 900, DPR 1)
 *   --wait MS         settle time before each shot (default 700)
 *   --stop            stop live view (POST /api/camera/stop) at the end
 *   --strict          exit 1 on console errors, page errors or non-local requests
 *   --audit           pixel audit of every shot (scripts/audit-png.mjs, on the PNG as
 *                     written, never resized): Night Red rules A and B on the
 *                     night-red shot, brass counts on the others; exit 1 when a
 *                     Night Red shot fails (BRAND 4.3)
 *
 * Environment: CHROME_PATH overrides the Chrome binary (default: the macOS app path).
 *
 * Output: one PNG per theme and PREFIX-report.json (console messages, failed or
 * non-local requests, frame sequence per shot, and the measured layout: the
 * image's box against the viewer's, the black bands on each side, the levels
 * strip height and the bottom of the right rail's cards; BRAND 11.1), the frame
 * metrics of owner decision D8 (toolbar, status bar and right panel sizes), every
 * element that scrolls (only the log may, BRAND 11.1) and, with --audit, the
 * pixel audit. The page exposes the frame on screen as [data-frame-seq]
 * (ImagingScreen); scripts can wait on it too.
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import puppeteer from 'puppeteer-core';
import { auditFile } from './audit-png.mjs';

// System Chrome (macOS default path); set CHROME_PATH elsewhere, e.g. /usr/bin/google-chrome.
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const THEMES = ['observatory', 'charcoal', 'night-red'];

const { values: opt } = parseArgs({
  options: {
    url: { type: 'string', default: 'http://localhost:5173/' },
    api: { type: 'string' },
    token: { type: 'string' },
    out: { type: 'string' },
    themes: { type: 'string', default: 'observatory' },
    live: { type: 'boolean', default: false },
    exposure: { type: 'string', default: '1' },
    gain: { type: 'string', default: '80' },
    slew: { type: 'string' },
    section: { type: 'string', default: 'imaging' },
    click: { type: 'string', multiple: true, default: [] },
    'log-open': { type: 'boolean', default: false },
    pref: { type: 'string', multiple: true, default: [] },
    name: { type: 'string', default: 'argos' },
    width: { type: 'string', default: '1440' },
    height: { type: 'string', default: '900' },
    dpr: { type: 'string', default: '1' },
    wait: { type: 'string', default: '700' },
    stop: { type: 'boolean', default: false },
    strict: { type: 'boolean', default: false },
    audit: { type: 'boolean', default: false },
  },
});

if (!opt.out) {
  console.error('screenshot.mjs: --out DIR is required (see the header of this file)');
  process.exit(2);
}
const themes = opt.themes.split(',').map((t) => t.trim()).filter(Boolean);
for (const t of themes) {
  if (!THEMES.includes(t)) {
    console.error(`screenshot.mjs: unknown theme "${t}" (use ${THEMES.join(', ')})`);
    process.exit(2);
  }
}

const pageUrl = new URL(opt.url);
const api = (opt.api ?? pageUrl.searchParams.get('api') ?? 'http://127.0.0.1:8742').replace(/\/$/, '');
const token = opt.token ?? pageUrl.searchParams.get('token') ?? 'dev';
if (!pageUrl.searchParams.has('api')) pageUrl.searchParams.set('api', api);
if (!pageUrl.searchParams.has('token')) pageUrl.searchParams.set('token', token);

fs.mkdirSync(opt.out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const say = (m) => console.log(`[screenshot] ${m}`);

// -- ARGOS API ------------------------------------------------------------------

async function call(method, route, body) {
  const res = await fetch(`${api}${route}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${route} -> ${res.status} ${text}`);
  return JSON.parse(text);
}

async function waitStatus(predicate, what, timeoutMs = 30_000) {
  const t0 = Date.now();
  for (;;) {
    const status = await call('GET', '/api/status');
    if (predicate(status)) return status;
    if (Date.now() - t0 > timeoutMs) throw new Error(`timed out waiting for ${what}`);
    await sleep(250);
  }
}

async function prepareServer() {
  let status = await call('GET', '/api/status');
  if (opt.live || opt.slew) {
    if (status.connection.state !== 'connected') {
      say('connecting the simulator');
      await call('POST', '/api/connection', { mode: 'simulator' });
      status = await waitStatus((s) => s.connection.state === 'connected', 'connection');
    }
  }
  if (opt.live && status.camera.state !== 'live') {
    say(`starting live view (${opt.exposure} s, gain ${opt.gain})`);
    if (status.camera.state !== 'idle') await call('POST', '/api/camera/stop');
    await call('POST', '/api/camera/live', {
      exposure_s: Number(opt.exposure),
      gain: Math.round(Number(opt.gain)),
    });
  }
}

async function startSlew() {
  const [ra, dec] = opt.slew.trim().split(/[\s,]+/).map(Number);
  if (!Number.isFinite(ra) || !Number.isFinite(dec)) throw new Error(`bad --slew "${opt.slew}"`);
  const status = await call('GET', '/api/status');
  if (status.mount.state === 'parked') {
    say('unparking');
    await call('POST', '/api/mount/unpark');
  }
  say(`GoTo RA ${ra} h, Dec ${dec} deg`);
  await call('POST', '/api/mount/goto', { ra_hours: ra, dec_deg: dec });
  await waitStatus((s) => s.mount.state === 'slewing', 'slewing', 10_000);
}

// -- Browser ----------------------------------------------------------------------

const report = { url: pageUrl.toString(), shots: [], console: [], external: [], failed: [] };
let problems = 0;
let auditFailed = 0;

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--no-first-run',
    '--no-default-browser-check',
    '--hide-scrollbars',
  ],
  defaultViewport: {
    width: Number(opt.width),
    height: Number(opt.height),
    deviceScaleFactor: Number(opt.dpr),
  },
});

try {
  await prepareServer();

  for (const theme of themes) {
    const page = await browser.newPage();
    page.on('console', (m) => {
      const line = `[${theme}] [${m.type()}] ${m.text()}`;
      report.console.push(line);
      if (m.type() === 'error') problems++;
    });
    page.on('pageerror', (e) => {
      report.console.push(`[${theme}] [pageerror] ${e.message}`);
      problems++;
    });
    page.on('requestfailed', (r) => report.failed.push(`${r.url()} ${r.failure()?.errorText ?? ''}`));
    page.on('request', (r) => {
      const u = r.url();
      if (!/^(https?|wss?):\/\/(localhost|127\.0\.0\.1)(:\d+)?\/|^(data|blob):/.test(u)) {
        report.external.push(u);
        problems++;
      }
    });

    const prefs = opt.pref.map((kv) => {
      const i = kv.indexOf('=');
      if (i < 1) throw new Error(`bad --pref "${kv}" (KEY=JSON)`);
      return [kv.slice(0, i), kv.slice(i + 1)];
    });
    await page.evaluateOnNewDocument(
      (t, kvs) => {
        try {
          localStorage.setItem('argos.theme', t);
          for (const [k, v] of kvs) localStorage.setItem(k, v);
        } catch {
          /* ignore */
        }
      },
      theme,
      prefs,
    );
    await page.goto(pageUrl.toString(), { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.shell', { timeout: 15_000 });
    await page.evaluate(() => document.fonts.ready);

    {
      // Always click the entry: the app may open on Connection (equipment not ready).
      const labels = {
        connection: 'Connection',
        imaging: 'Observe',
        sequencer: 'Plan',
        analyze: 'Review',
        configuration: 'Settings',
      };
      const label = labels[opt.section];
      if (!label) throw new Error(`unknown --section ${opt.section}`);
      await page.click(`nav button[aria-label^="${label}"]`);
    }

    let seq = null;
    if (opt.live && opt.section === 'imaging') {
      // A frame is on screen, then a newer one: proof that frames are flowing.
      const first = await page.waitForFunction(
        () => Number(document.querySelector('[data-frame-seq]')?.getAttribute('data-frame-seq') ?? 0),
        { timeout: 30_000, polling: 100 },
      );
      const firstSeq = await first.jsonValue();
      await page.waitForFunction(
        (s) => Number(document.querySelector('[data-frame-seq]')?.getAttribute('data-frame-seq') ?? 0) > s,
        { timeout: 30_000, polling: 100 },
        firstSeq,
      );
      seq = await page.$eval('[data-frame-seq]', (e) => Number(e.getAttribute('data-frame-seq')));
    }

    if (opt.slew) {
      await startSlew();
      await page.waitForFunction(() => document.body.innerText.includes('Slewing'), {
        timeout: 10_000,
      });
    }

    if (opt['log-open']) await page.click('footer button[aria-label^="Activity log"]');
    for (const label of opt.click) {
      const handle = await page.waitForFunction(
        (l) =>
          document.querySelector(`button[aria-label="${CSS.escape(l)}"]`) ??
          [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === l),
        { timeout: 10_000 },
        label,
      );
      await handle.asElement().click();
    }

    // Park the pointer on the empty middle of the navigation rail: no hover state,
    // no tooltip (the bottom-right corner is the status bar's Log button).
    await page.mouse.move(46, Math.round(Number(opt.height) * 0.55));
    await sleep(Number(opt.wait));
    const file = path.join(opt.out, `${opt.name}-${theme}.png`);
    await page.screenshot({ path: file });
    const appliedTheme = await page.evaluate(() => document.documentElement.dataset.theme);
    const layout = await page.evaluate(() => {
      const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom, right: r.right };
      };
      const stage = box(document.querySelector('.stage'));
      const image = box(document.querySelector('.frame-edge'));
      const cards = [...document.querySelectorAll('aside.rail .card')].map((c) => ({
        title: c.querySelector('h2')?.textContent ?? '',
        ...box(c),
      }));
      const rail = box(document.querySelector('aside.rail'));
      const r1 = (v) => Math.round(v * 10) / 10;
      const bands =
        stage && image
          ? {
              top: r1(Math.max(0, image.y - stage.y)),
              bottom: r1(Math.max(0, stage.bottom - image.bottom)),
              left: r1(Math.max(0, image.x - stage.x)),
              right: r1(Math.max(0, stage.right - image.right)),
              // Share of the image hidden by the viewer edges (Fill mode crops).
              croppedX: r1((100 * Math.max(0, image.width - stage.width)) / image.width),
            }
          : null;
      const h = (sel) => {
        const el = document.querySelector(sel);
        return el ? r1(el.getBoundingClientRect().height) : null;
      };
      const w = (sel) => {
        const el = document.querySelector(sel);
        return el ? r1(el.getBoundingClientRect().width) : null;
      };
      // Owner D8: toolbar 44 px, status bar 28 px, right panel 360-580 px (400 by default).
      const frame = {
        toolbar: h('main [role="toolbar"]'),
        statusbar: h('footer.statusbar'),
        rightPanel: w('aside.rail'),
        navRail: w('nav.rail'),
      };
      // Everything that scrolls (BRAND 11.1: nothing but the log may).
      const name = (el) =>
        el.getAttribute('aria-label') ||
        `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''}${[...el.classList]
          .filter((c) => !c.startsWith('svelte-'))
          .slice(0, 2)
          .map((c) => `.${c}`)
          .join('')}`;
      const scrollers = [...document.querySelectorAll('body *')]
        .filter((el) => {
          const cs = getComputedStyle(el);
          const y = /(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1;
          const x = /(auto|scroll)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1;
          return (x || y) && el.getClientRects().length > 0;
        })
        .map((el) => ({ name: name(el), log: !!el.closest('.log, [aria-label^="Activity log"], .log-drawer, .drawer') }));
      const se = document.scrollingElement;
      const pageScrolls = se ? se.scrollHeight > innerHeight + 1 || se.scrollWidth > innerWidth + 1 : false;
      return {
        frame,
        scrollers,
        pageScrolls,
        stage,
        image,
        bands,
        stripHeight: box(document.querySelector('section.strip'))?.height ?? 0,
        rail,
        cards,
        railScrolls: (() => {
          const a = document.querySelector('aside.rail');
          return a ? a.scrollHeight > a.clientHeight + 1 : false;
        })(),
      };
    });
    const shot = { theme, appliedTheme, file, frameSeq: seq, layout };
    report.shots.push(shot);
    const f8 = layout.frame;
    say(
      `${theme}: toolbar ${f8.toolbar ?? '—'} px, status bar ${f8.statusbar ?? '—'} px, ` +
        `right panel ${f8.rightPanel ?? '—'} px; page ${layout.pageScrolls ? 'SCROLLS' : 'does not scroll'}; ` +
        `scrolling: ${layout.scrollers.map((s) => s.name + (s.log ? ' (log)' : '')).join(', ') || 'nothing'}`,
    );
    if (opt.audit) {
      shot.audit = auditFile(file, { brass: true });
      const a = shot.audit;
      if (a.error || (a.nightRed && !a.nightRed.pass)) auditFailed++;
      say(
        `${theme}: audit ` +
          (a.error
            ? `ERROR ${a.error}`
            : a.nightRed
              ? `Night Red ${a.nightRed.pass ? 'PASS' : 'FAIL'} (rule A ${a.nightRed.ruleA} px, rule B ${a.nightRed.ruleB_tol} px with rounding)`
              : `brass ${a.brass.total} px (accent ${a.brass.accent}, hover ${a.brass.accentHover}, warning ${a.brass.warning}, role target ${a.brass.roleTarget})`),
      );
    }
    if (layout.bands) {
      const b = layout.bands;
      say(
        `${theme}: bands top ${b.top} / bottom ${b.bottom} / left ${b.left} / right ${b.right} px, ` +
          `strip ${layout.stripHeight} px, rail ${layout.railScrolls ? 'scrolls' : 'fits'}`,
      );
    }
    say(`${theme}: ${file}${seq !== null ? ` (frame #${seq})` : ''}`);
    await page.close();
  }

  if (opt.stop) {
    await call('POST', '/api/camera/stop');
    say('live view stopped');
  }
} catch (err) {
  console.error(`[screenshot] FAILED: ${err instanceof Error ? err.message : err}`);
  process.exitCode = 1;
} finally {
  await browser.close();
  const reportFile = path.join(opt.out, `${opt.name}-report.json`);
  fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
  say(
    `report: ${reportFile} (${report.console.length} console lines, ` +
      `${report.external.length} non-local requests, ${report.failed.length} failed requests)`,
  );
  if (opt.strict && problems > 0 && !process.exitCode) process.exitCode = 1;
  if (auditFailed > 0) {
    console.error(`[screenshot] pixel audit: ${auditFailed} shot(s) FAIL (BRAND 4.3)`);
    process.exitCode = 1;
  }
}
