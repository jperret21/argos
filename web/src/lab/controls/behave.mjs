#!/usr/bin/env node
/**
 * Behaviour checks of the controls lab in headless Chrome, with real
 * keyboard and pointer input (puppeteer-core, the system Chrome):
 * commit model of the scrub field, stepper repeat, manual segmented
 * activation, slider keys and Esc-to-start, focuser Go to / queue / halt,
 * per-axis jog and the dead-man, hold-to-confirm phases.
 *
 *   cd web && npx vite --port 5202 --strictPort      # terminal 1
 *   node src/lab/controls/behave.mjs                  # prints PASS / FAIL
 */
import puppeteer from 'puppeteer-core';

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const BASE = 'http://localhost:5202/lab/controls.html';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  [${detail}]` : ''}`);
};
setTimeout(() => {
  console.log('WATCHDOG: stalled after', results.length, 'checks');
  process.exit(2);
}, 120000).unref();

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
await page.setViewport({ width: 1440, height: 900 });

async function open(plate) {
  await page.goto(`${BASE}?plate=${plate}`, { waitUntil: 'networkidle0' });
  await sleep(500);
}
const text = (sel) => page.$eval(sel, (el) => el.textContent.trim());
// Puppeteer's clickCount: 3 does not select an input's text (checked on a plain input): select it explicitly.
async function fill(sel, value) {
  await page.click(sel);
  await page.$eval(sel, (i) => i.select());
  await page.keyboard.type(value);
}

// -- Values: scrub field commit model ------------------------------------------------
await open('values');
const exp = '[data-shot="scrub-live"] .sf:first-child input';
const help = '[data-shot="scrub-live"] .sf:first-child .help';
await fill(exp, '480');
check('typing marks the field "Not sent"', (await text(help)).startsWith('Not sent'), await text(help));
await page.keyboard.press('Enter');
await sleep(100);
check('Enter sends: "Sending…"', (await text(help)).includes('Sending'), await text(help));
await sleep(700);
check('device refusal shown in words', (await text(help)).toLowerCase().includes('live view is limited to 300 s'), await text(help));
await page.keyboard.press('Escape');
await sleep(50);
check('Esc reverts to the device value', (await page.$eval(exp, (i) => i.value)) === '2.0', await page.$eval(exp, (i) => i.value));
await page.keyboard.press('ArrowUp');
check('ArrowUp steps the ladder 2 -> 3', (await page.$eval(exp, (i) => i.value)) === '3.0', await page.$eval(exp, (i) => i.value));
await sleep(600 + 450 + 150);
check('arrow step settles and is applied once', (await text(help)).startsWith('Applied'), await text(help));
await fill(exp, '900');
check('out of range is refused, never clamped', (await text(help)).includes('Range') && (await page.$eval(exp, (i) => i.value)) === '900', await text(help));
await page.keyboard.press('Escape');

// Stepper hold-to-repeat with acceleration
const plus = '[data-shot="steppers"] .stepper:first-child button[aria-label="Increase gain"]';
const gainInput = '[data-shot="steppers"] .stepper:first-child input';
const box = await (await page.$(plus)).boundingBox();
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
await page.mouse.down();
await sleep(2400);
const accel = await page.$('[data-shot="steppers"] .stepper:first-child .accel');
const held = Number(await page.$eval(gainInput, (i) => i.value));
await page.mouse.up();
check('hold + repeats then accelerates (x10 shown)', held > 120 && !!accel, `gain ${held}, accel chip ${!!accel}`);
const helpStep = await text('[data-shot="steppers"] .stepper:first-child .help');
check('stepper sends after release, not while held', helpStep.includes('Sends on release') || helpStep.includes('Sending'), helpStep);

// Segmented, manual activation (filter wheel)
const ir = '[data-shot="segmented"] [role="radiogroup"][aria-label="Filter"] [role="radio"]:nth-of-type(1)';
await page.focus(ir);
await page.keyboard.press('ArrowRight');
const checkedAfterArrow = await page.$$eval('[aria-label="Filter"] [role="radio"]', (els) => els.map((e) => e.getAttribute('aria-checked')));
check('manual activation: arrow moves focus only', checkedAfterArrow[0] === 'true' && checkedAfterArrow[1] === 'false', JSON.stringify(checkedAfterArrow));
await page.keyboard.press(' ');
await sleep(80);
const afterSpace = await page.$$eval('[aria-label="Filter"] [role="radio"]', (els) => els.map((e) => [e.getAttribute('aria-checked'), e.getAttribute('aria-busy'), e.getAttribute('aria-disabled')]));
check('Space chooses LP, spinner on LP, others unavailable', afterSpace[1][0] === 'true' && afterSpace[1][1] === 'true' && afterSpace[0][2] === 'true', JSON.stringify(afterSpace));

// Slider keyboard
const thumb = '[data-shot="slider-live"] [role="slider"]';
await page.focus(thumb);
await page.keyboard.press('End');
check('slider End -> max', (await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'))) === '30');
await page.keyboard.down('Shift');
await page.keyboard.press('ArrowLeft');
await page.keyboard.up('Shift');
check('slider Shift+ArrowLeft -> -1.0', (await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'))) === '29');
await page.keyboard.down('Alt');
await page.keyboard.press('ArrowLeft');
await page.keyboard.up('Alt');
check('slider Alt+ArrowLeft -> -0.01', (await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'))) === '28.99', await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow')));

// Slider drag + Esc returns to the start value
const track = await (await page.$('[data-shot="slider-live"] .track')).boundingBox();
await page.keyboard.press('Home');
const startV = await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'));
await page.mouse.move(track.x + track.width * 0.5, track.y + track.height / 2);
await page.mouse.down();
await page.mouse.move(track.x + track.width * 0.7, track.y + track.height / 2, { steps: 5 });
const midV = await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'));
await page.keyboard.press('Escape');
await page.mouse.up();
const endV = await page.$eval(thumb, (t) => t.getAttribute('aria-valuenow'));
check('drag moves the value, Esc returns to the start', midV !== startV && endV === startV, `start ${startV} mid ${midV} end ${endV}`);

// -- Focuser ------------------------------------------------------------------------------
await open('focuser');
const live = '[data-shot="focuser-live"]';
const goto = `${live} .sf input`;
await fill(goto, '200000');
check('Go to out of range refused in words', (await text(`${live} .sf .help`)).includes('Range'), await text(`${live} .sf .help`));
await fill(goto, '13000');
await page.click(`${live} .readouts`); // blur
await sleep(300);
const posAfterBlur = await text(`${live} .ro .v.big`);
check('Go to never moves on blur', posAfterBlur === '12\u202f450', posAfterBlur); // U+202F grouping (lab synthesis)
await page.click(goto);
await page.keyboard.press('Enter');
await sleep(150);
check('Enter moves: badge Moving', (await text(`${live} .status`)).includes('Moving'), await text(`${live} .status`));
await page.click(`${live} button[aria-label="Focus in"]`);
await page.click(`${live} button[aria-label="Focus in"]`);
await sleep(50);
check('taps during a move are queued', (await text(`${live} .readouts`)).includes('+200 queued'), await text(`${live} .readouts`));
await page.keyboard.press('Escape');
await sleep(100);
check('Esc halts the focuser', (await text(`${live} .line`)).startsWith('Halted at'), await text(`${live} .line`));

// -- Mount: keyboard jog, per-axis, blur stops ------------------------------------------------
await open('mount');
const altSel = '[data-shot="jog-live"] .ro > div:nth-child(3) .v';
const alt0 = await text(altSel);
await page.keyboard.press('j');
await page.keyboard.down('ArrowUp');
await page.keyboard.down('ArrowRight');
await sleep(700);
const pressed = await page.$$eval('[data-shot="jog-live"] .key[aria-pressed="true"]', (els) => els.map((e) => e.getAttribute('aria-label')));
check('armed arrows jog two axes at once', pressed.includes('Jog Altitude +') && pressed.includes('Jog Azimuth +'), JSON.stringify(pressed));
await page.keyboard.up('ArrowUp');
await sleep(300);
const pressed2 = await page.$$eval('[data-shot="jog-live"] .key[aria-pressed="true"]', (els) => els.map((e) => e.getAttribute('aria-label')));
check('releasing Up stops only altitude', pressed2.length === 1 && pressed2[0] === 'Jog Azimuth +', JSON.stringify(pressed2));
await page.keyboard.up('ArrowRight');
await sleep(300);
const alt1 = await text(altSel);
check('altitude changed while held (polled)', alt1 !== alt0, `${alt0} -> ${alt1}`);
// dead-man: break the link, hold N, wait
await page.click('[data-shot="link-loss"] button');
const n = await (await page.$('[data-shot="jog-live"] button[aria-label="Jog Altitude +"]')).boundingBox();
await page.mouse.move(n.x + n.width / 2, n.y + n.height / 2);
await page.mouse.down();
await sleep(400);
const movingEarly = await page.$eval('[data-shot="jog-live"] button[aria-label="Jog Altitude +"]', (e) => e.getAttribute('aria-pressed'));
await sleep(1100);
const stoppedLate = await page.$eval('[data-shot="jog-live"] button[aria-label="Jog Altitude +"]', (e) => e.getAttribute('aria-pressed'));
await page.mouse.up();
check('link lost: moves, then the server stops it after 1 s', movingEarly === 'true' && stoppedLate === 'false', `${movingEarly} -> ${stoppedLate}`);

// -- Hold to confirm --------------------------------------------------------------------------
await open('confirm');
const hold = '[data-shot="hold-live"] button.ctl';
const cap = '[data-shot="hold-live"] .caption';
await page.click(hold);
await sleep(50);
check('a tap teaches the gesture', (await text(cap)).includes('Hold to park, or press Enter'), await text(cap));
const hb = await (await page.$(hold)).boundingBox();
await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
await page.mouse.down();
await sleep(350);
await page.mouse.up();
await sleep(30);
check('released early: nothing sent', (await text(cap)).includes('nothing sent'), await text(cap));
await sleep(2000);
await page.mouse.down();
await sleep(820);
check('held 0.7 s: busy', (await text(cap)).includes('Parking'), await text(cap));
await page.mouse.up();
await sleep(1900);
check('then done', (await text(cap)).includes('Parked'), await text(cap));

check('no page errors', errors.length === 0, errors.join(' | '));
await browser.close();

console.log(`${results.filter((r) => r.ok).length}/${results.length} passed`);
process.exit(results.every((r) => r.ok) ? 0 : 1);
