#!/usr/bin/env node
/**
 * Pixel audits of UI screenshots, no dependency (a small PNG decoder on
 * node:zlib; 8-bit RGB / RGBA, non-interlaced, which is what headless Chrome
 * and the WKWebView probe write).
 *
 *   node web/lab/synthesis/audit-png.mjs [--brass] a.png b.png ...
 *
 * Night Red (every file whose name contains "night-red"), BRAND 4.3:
 *   rule A  no pixel may have G > R or B > R (green or blue above red).
 *           Reported strict and with 1 level of tolerance.
 *   rule B  the research labs' palette rule: a pixel fails when
 *           max(G, B) > 8 and max(G, B) > 0.68 x R (0.68 is just above
 *           --fg #d88f8f, G/R 0.66). Reported strict and with the 8-bit
 *           rounding of the pixel allowed for (+-0.5 per channel), which
 *           separates anti-aliased --fg edges over black from real grey.
 *   Audit captured originals: a resampled copy (downscaled 2x shot) can
 *   create G > R on near-black edges (filters with negative lobes).
 *
 * --brass (other themes): pixels within RGB distance 28 of --accent
 *   #c49a3c, --accent-hover #d6b25d, --warning #d0a85a, --role-target
 *   #b48e2c (Observatory values). Anti-aliased edges are not counted, so the
 *   counts are indicative: compare screens with the same method only.
 *
 * Exit code 1 when a Night Red file fails rule A, or rule B with tolerance.
 */
import fs from 'node:fs';
import zlib from 'node:zlib';

function decode(file) {
  const buf = fs.readFileSync(file);
  let p = 8;
  let w = 0;
  let h = 0;
  let depth = 0;
  let ctype = 0;
  let inter = 0;
  const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p);
    const type = buf.toString('ascii', p + 4, p + 8);
    const data = buf.subarray(p + 8, p + 8 + len);
    if (type === 'IHDR') {
      w = data.readUInt32BE(0);
      h = data.readUInt32BE(4);
      depth = data[8];
      ctype = data[9];
      inter = data[12];
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    p += 12 + len;
  }
  if (depth !== 8 || inter !== 0 || (ctype !== 2 && ctype !== 6)) {
    throw new Error(`unsupported PNG (depth ${depth}, colour type ${ctype}, interlace ${inter})`);
  }
  const bpp = ctype === 6 ? 4 : 3;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = w * bpp;
  const px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[y * (stride + 1)];
    const src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const dst = px.subarray(y * stride, (y + 1) * stride);
    const prev = y > 0 ? px.subarray((y - 1) * stride, y * stride) : null;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? dst[x - bpp] : 0;
      const b = prev ? prev[x] : 0;
      const c = prev && x >= bpp ? prev[x - bpp] : 0;
      let v = src[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const q = a + b - c;
        const pa = Math.abs(q - a);
        const pb = Math.abs(q - b);
        const pc = Math.abs(q - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      dst[x] = v & 255;
    }
  }
  return { w, h, bpp, px };
}

function nightRed({ w, h, bpp, px }) {
  const r = { pixels: w * h, ruleA: 0, ruleA_tol1: 0, ruleB: 0, ruleB_tol: 0, worst: null };
  for (let i = 0; i < px.length; i += bpp) {
    const R = px[i];
    const m = Math.max(px[i + 1], px[i + 2]);
    if (m > R) r.ruleA++;
    if (m > R + 1) r.ruleA_tol1++;
    if (m > 8 && m > 0.68 * R) {
      r.ruleB++;
      if (!r.worst || m > r.worst[1]) r.worst = [R, m];
      if (m - 0.5 > 8 && m - 0.5 > 0.68 * (R + 0.5)) r.ruleB_tol++;
    }
  }
  return r;
}

const GOLD = { accent: [0xc4, 0x9a, 0x3c], accentHover: [0xd6, 0xb2, 0x5d], warning: [0xd0, 0xa8, 0x5a], roleTarget: [0xb4, 0x8e, 0x2c] };
function brass({ w, h, bpp, px }) {
  const n = { accent: 0, accentHover: 0, warning: 0, roleTarget: 0 };
  for (let i = 0; i < px.length; i += bpp) {
    let best = null;
    let bd = Infinity;
    for (const [k, c] of Object.entries(GOLD)) {
      const d = Math.hypot(px[i] - c[0], px[i + 1] - c[1], px[i + 2] - c[2]);
      if (d < bd) {
        bd = d;
        best = k;
      }
    }
    if (bd <= 28) n[best]++;
  }
  return { pixels: w * h, ...n };
}

const args = process.argv.slice(2);
const withBrass = args.includes('--brass');
let failed = false;
for (const file of args.filter((a) => !a.startsWith('--'))) {
  try {
    const img = decode(file);
    const out = { file };
    if (/night-red/.test(file)) {
      out.nightRed = nightRed(img);
      if (out.nightRed.ruleA || out.nightRed.ruleB_tol) failed = true;
    } else if (withBrass) out.brass = brass(img);
    console.log(JSON.stringify(out));
  } catch (e) {
    console.log(JSON.stringify({ file, error: String(e?.message ?? e) }));
    failed = true;
  }
}
process.exit(failed ? 1 : 0);
