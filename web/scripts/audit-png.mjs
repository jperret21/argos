#!/usr/bin/env node
/**
 * Pixel audits of UI screenshots (BRAND.md 4.3 and 8), no dependency: a small
 * PNG decoder on node:zlib (8-bit grey, grey + alpha, RGB, RGBA; not
 * interlaced, not palette), which covers what headless Chrome, puppeteer and
 * the WKWebView probe write. Moved from web/lab/synthesis/audit-png.mjs in
 * wave 2 (web/lab/PROPOSAL.md sections 3.5 and 6); the lab path forwards here.
 *
 *   node scripts/audit-png.mjs [options] PATH...
 *   npm run audit:night-red -- shots/            # the CI gate
 *   npm run audit:brass -- shots/argos-observatory.png
 *
 * PATH is a PNG file or a folder (its *.png files, not recursive).
 *
 * Night Red (files whose name contains "night-red"; every file with
 * --force-night-red), BRAND 4.3, MUST:
 *   rule A  no pixel has G > R or B > R (green or blue above red). Strict;
 *           the count with 1 level of tolerance is reported for diagnosis.
 *   rule B  no pixel has max(G, B) > 8 and max(G, B) > 0.68 x R (0.68 is just
 *           above --fg #d88f8f, G/R 0.66), with the 8-bit rounding of the
 *           pixel allowed for (+-0.5 per channel): that separates anti-aliased
 *           --fg edges over black from real grey or green.
 *   A file fails on any rule A pixel or any rule B pixel past the tolerance.
 *   Audit captured ORIGINALS: a resampled copy (a downscaled 2x shot) can
 *   create G > R on near-black edges (filters with negative lobes).
 *
 * Brass (--brass; BRAND 3 and the brass budget of section 8): pixels within
 *   RGB distance 28 of the theme's --accent, --accent-hover, --warning and
 *   --role-target (the theme is read from the file name: observatory,
 *   charcoal, night-red; Observatory otherwise). Anti-aliased edges are not
 *   counted, so the counts are indicative: compare screens with the same
 *   method only. Night Red has no brass (its accents are reds close to its
 *   red text), so no count is made there.
 *
 * Options
 *   --night-red        audit only the Night Red files given (others are
 *                      skipped) and fail (exit 2) when there is none, so a
 *                      CI step never passes on an empty folder
 *   --force-night-red  apply the Night Red rules to every file (WebKit shots
 *                      named otherwise)
 *   --brass            also count brass pixels
 *   --json             one JSON object per file (the lab's output format)
 *
 * Exit code: 0 all audited files pass; 1 a Night Red file fails or a file
 * cannot be read; 2 usage error (no file, or --night-red with no Night Red
 * file).
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import zlib from 'node:zlib';

/** Decode a PNG buffer to 8-bit RGB pixels: { w, h, px } with px.length = w * h * 3. */
export function decodePng(buf) {
  const SIG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (buf.length < 8 || SIG.some((b, i) => buf[i] !== b)) throw new Error('not a PNG file');
  let p = 8;
  let w = 0;
  let h = 0;
  let depth = 0;
  let ctype = -1;
  let inter = 0;
  const idat = [];
  while (p + 8 <= buf.length) {
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
  const channels = { 0: 1, 2: 3, 4: 2, 6: 4 }[ctype];
  if (depth !== 8 || inter !== 0 || !channels) {
    throw new Error(`unsupported PNG (bit depth ${depth}, colour type ${ctype}, interlace ${inter})`);
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const bpp = channels;
  const stride = w * bpp;
  if (raw.length < h * (stride + 1)) throw new Error('truncated PNG data');
  const rows = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[y * (stride + 1)];
    const src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const dst = rows.subarray(y * stride, (y + 1) * stride);
    const prev = y > 0 ? rows.subarray((y - 1) * stride, y * stride) : null;
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
      } else if (filter !== 0) throw new Error(`bad PNG filter ${filter} on row ${y}`);
      dst[x] = v & 255;
    }
  }
  // Alpha is dropped: a screenshot is opaque, and a pixel's colour is what it emits.
  const px = Buffer.alloc(w * h * 3);
  for (let i = 0, o = 0; i < rows.length; i += bpp, o += 3) {
    if (bpp <= 2) px[o] = px[o + 1] = px[o + 2] = rows[i];
    else {
      px[o] = rows[i];
      px[o + 1] = rows[i + 1];
      px[o + 2] = rows[i + 2];
    }
  }
  return { w, h, px };
}

/**
 * Night Red rules A and B on decoded pixels. `first` is the first failing
 * pixel (x, y, r, g, b) and `worst` the rule B pixel with the most green or
 * blue, for diagnosis.
 */
export function auditNightRed({ w, h, px }) {
  const r = { pixels: w * h, ruleA: 0, ruleA_tol1: 0, ruleB: 0, ruleB_tol: 0, pass: true, first: null, worst: null };
  for (let i = 0, n = 0; i < px.length; i += 3, n++) {
    const R = px[i];
    const G = px[i + 1];
    const B = px[i + 2];
    const m = Math.max(G, B);
    let fail = false;
    if (m > R) {
      r.ruleA++;
      fail = true;
    }
    if (m > R + 1) r.ruleA_tol1++;
    if (m > 8 && m > 0.68 * R) {
      r.ruleB++;
      if (!r.worst || m - 0.68 * R > r.worst.excess) {
        r.worst = { x: n % w, y: Math.floor(n / w), r: R, g: G, b: B, excess: Math.round((m - 0.68 * R) * 100) / 100 };
      }
      if (m - 0.5 > 8 && m - 0.5 > 0.68 * (R + 0.5)) {
        r.ruleB_tol++;
        fail = true;
      }
    }
    if (fail && !r.first) r.first = { x: n % w, y: Math.floor(n / w), r: R, g: G, b: B };
  }
  r.pass = r.ruleA === 0 && r.ruleB_tol === 0;
  return r;
}

/** The brass family of each theme with brass (tokens.css). */
export const BRASS = {
  observatory: { accent: [0xc4, 0x9a, 0x3c], accentHover: [0xd6, 0xb2, 0x5d], warning: [0xd0, 0xa8, 0x5a], roleTarget: [0xb4, 0x8e, 0x2c] },
  charcoal: { accent: [0xc4, 0x9a, 0x3c], accentHover: [0xd8, 0xb7, 0x5f], warning: [0xd1, 0xaa, 0x5e], roleTarget: [0xb4, 0x8e, 0x2c] },
};

/** The theme a screenshot's file name says (observatory by default). */
export function themeOf(file) {
  const name = path.basename(file);
  if (/night-red/.test(name)) return 'night-red';
  if (/charcoal/.test(name)) return 'charcoal';
  return 'observatory';
}

/**
 * Brass pixels by token: nearest of the theme's brass family within RGB
 * distance 28 (Observatory's family for a theme without brass). `total` is
 * their sum.
 */
export function countBrass({ w, h, px }, theme = 'observatory') {
  const family = Object.entries(BRASS[theme] ?? BRASS.observatory);
  const n = Object.fromEntries(family.map(([k]) => [k, 0]));
  const R2 = 28 * 28;
  for (let i = 0; i < px.length; i += 3) {
    let best = null;
    let bd = Infinity;
    for (const [k, c] of family) {
      const dr = px[i] - c[0];
      const dg = px[i + 1] - c[1];
      const db = px[i + 2] - c[2];
      const d = dr * dr + dg * dg + db * db;
      if (d < bd) {
        bd = d;
        best = k;
      }
    }
    if (bd <= R2) n[best]++;
  }
  const total = Object.values(n).reduce((a, b) => a + b, 0);
  return { pixels: w * h, theme, ...n, total };
}

/** PNG files of the given paths (folders expanded, not recursive), sorted per folder. */
export function pngFiles(paths) {
  const out = [];
  for (const p of paths) {
    let st;
    try {
      st = fs.statSync(p);
    } catch {
      out.push(p); // reported as unreadable by the caller
      continue;
    }
    if (st.isDirectory()) {
      out.push(
        ...fs
          .readdirSync(p)
          .filter((f) => f.toLowerCase().endsWith('.png'))
          .sort()
          .map((f) => path.join(p, f)),
      );
    } else out.push(p);
  }
  return out;
}

/** Audit one file: { file, theme, nightRed?, brass?, error? }. */
export function auditFile(file, { brass = false, forceNightRed = false } = {}) {
  const out = { file, theme: forceNightRed ? 'night-red' : themeOf(file) };
  try {
    const img = decodePng(fs.readFileSync(file));
    out.size = [img.w, img.h];
    if (out.theme === 'night-red') out.nightRed = auditNightRed(img);
    if (brass && out.theme !== 'night-red') out.brass = countBrass(img, out.theme);
  } catch (e) {
    out.error = String(e?.message ?? e);
  }
  return out;
}

const fmtInt = (v) => String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

function describe(r) {
  if (r.error) return `ERROR ${r.file}: ${r.error}`;
  const parts = [];
  if (r.nightRed) {
    const a = r.nightRed;
    parts.push(
      `${a.pass ? 'PASS' : 'FAIL'} Night Red: rule A ${fmtInt(a.ruleA)} px (tol 1: ${fmtInt(a.ruleA_tol1)}), ` +
        `rule B ${fmtInt(a.ruleB)} px (with rounding: ${fmtInt(a.ruleB_tol)})` +
        (a.first ? `, first at ${a.first.x},${a.first.y} rgb(${a.first.r}, ${a.first.g}, ${a.first.b})` : ''),
    );
  }
  if (r.brass) {
    const b = r.brass;
    const keys = Object.keys(BRASS[b.theme] ?? BRASS.observatory).filter((k) => k in b);
    parts.push(`brass (${b.theme}) ${keys.map((k) => `${k} ${fmtInt(b[k])}`).join(', ')}; total ${fmtInt(b.total)} px`);
  }
  if (!parts.length) parts.push('skipped (not Night Red; pass --brass to count brass)');
  return `${path.basename(r.file)} ${r.size ? `${r.size[0]} x ${r.size[1]}` : ''}: ${parts.join(' · ')}`;
}

/** The CLI. Returns the exit code. */
export function main(argv) {
  const flags = new Set(argv.filter((a) => a.startsWith('--')));
  const known = new Set(['--brass', '--night-red', '--force-night-red', '--json']);
  for (const f of flags) {
    if (!known.has(f)) {
      console.error(`audit-png: unknown option ${f} (see the header of scripts/audit-png.mjs)`);
      return 2;
    }
  }
  let files = pngFiles(argv.filter((a) => !a.startsWith('--')));
  const onlyNightRed = flags.has('--night-red') && !flags.has('--force-night-red');
  if (onlyNightRed) files = files.filter((f) => themeOf(f) === 'night-red');
  if (!files.length) {
    console.error(
      onlyNightRed
        ? 'audit-png: no Night Red PNG (file name containing "night-red") in the given paths'
        : 'audit-png: no PNG file given',
    );
    return 2;
  }
  let failed = 0;
  for (const file of files) {
    const r = auditFile(file, { brass: flags.has('--brass'), forceNightRed: flags.has('--force-night-red') });
    if (r.error || (r.nightRed && !r.nightRed.pass)) failed++;
    console.log(flags.has('--json') ? JSON.stringify(r) : describe(r));
  }
  if (!flags.has('--json')) {
    console.log(failed ? `audit-png: ${failed} of ${files.length} file(s) FAIL` : `audit-png: ${files.length} file(s) pass`);
  }
  return failed ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href) {
  process.exitCode = main(process.argv.slice(2));
}
