import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { afterAll, describe, expect, it, vi } from 'vitest';
import { auditFile, auditNightRed, countBrass, decodePng, main, pngFiles, themeOf } from './audit-png.mjs';

/** A minimal PNG encoder (8-bit, colour type 2 or 6, filter `filter` on every row). */
function png(w, h, pixel, { alpha = false, filter = 0 } = {}) {
  const bpp = alpha ? 4 : 3;
  const raw = Buffer.alloc(h * (w * bpp + 1));
  const prevRow = Buffer.alloc(w * bpp);
  for (let y = 0; y < h; y++) {
    const row = Buffer.alloc(w * bpp);
    for (let x = 0; x < w; x++) {
      const c = pixel(x, y);
      for (let k = 0; k < bpp; k++) row[x * bpp + k] = k < 3 ? c[k] : 255;
    }
    const o = y * (w * bpp + 1);
    raw[o] = filter;
    for (let i = 0; i < row.length; i++) {
      const a = i >= bpp ? row[i - bpp] : 0;
      const b = y > 0 ? prevRow[i] : 0;
      const pred = filter === 1 ? a : filter === 2 ? b : filter === 3 ? (a + b) >> 1 : 0;
      raw[o + 1 + i] = (row[i] - pred) & 255;
    }
    row.copy(prevRow);
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(td) >>> 0);
    return Buffer.concat([len, td, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = alpha ? 6 : 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-png-'));
afterAll(() => fs.rmSync(dir, { recursive: true, force: true }));
const write = (name, buf) => {
  const f = path.join(dir, name);
  fs.writeFileSync(f, buf);
  return f;
};

describe('decodePng', () => {
  it('decodes RGB and RGBA with every row filter', () => {
    const pix = (x, y) => [(x * 40 + y) & 255, (y * 30) & 255, (x * y) & 255];
    for (const filter of [0, 1, 2, 3]) {
      for (const alpha of [false, true]) {
        const img = decodePng(png(5, 4, pix, { alpha, filter }));
        expect(img.w).toBe(5);
        expect(img.h).toBe(4);
        expect([...img.px.subarray((2 * 5 + 3) * 3, (2 * 5 + 3) * 3 + 3)]).toEqual(pix(3, 2));
      }
    }
  });
  it('refuses what is not a PNG', () => {
    expect(() => decodePng(Buffer.from('hello world'))).toThrow(/not a PNG/);
  });
});

describe('Night Red rules', () => {
  const nr = (c) => auditNightRed(decodePng(png(2, 2, () => c)));
  it('passes pure reds and black', () => {
    expect(nr([216, 0, 0]).pass).toBe(true);
    expect(nr([0, 0, 0]).pass).toBe(true);
    // --fg #d88f8f: G/R 0.66, below 0.68.
    expect(nr([0xd8, 0x8f, 0x8f]).pass).toBe(true);
  });
  it('rule A: green or blue above red fails', () => {
    const r = nr([10, 11, 0]);
    expect(r.ruleA).toBe(4);
    expect(r.pass).toBe(false);
    expect(r.first).toEqual({ x: 0, y: 0, r: 10, g: 11, b: 0 });
  });
  it('rule B: grey fails, an anti-aliased --fg edge passes with rounding', () => {
    expect(nr([128, 128, 128]).pass).toBe(false);
    // 0.68 x 40 = 27.2: G = 28 fails strictly, not once +-0.5 of rounding is allowed
    // (27.5 <= 0.68 x 40.5 = 27.54).
    const edge = nr([40, 28, 28]);
    expect(edge.ruleB).toBe(4);
    expect(edge.ruleB_tol).toBe(0);
    expect(edge.pass).toBe(true);
    // Below 9 levels of green or blue nothing is counted.
    expect(nr([4, 8, 8]).ruleB).toBe(0);
  });
});

describe('brass', () => {
  it('counts pixels near the theme tokens only', () => {
    const img = decodePng(png(4, 1, (x) => [[0xc4, 0x9a, 0x3c], [0xb4, 0x8e, 0x2c], [0xd0, 0xa8, 0x5a], [0x90, 0x90, 0x90]][x]));
    expect(countBrass(img, 'observatory')).toMatchObject({ accent: 1, roleTarget: 1, warning: 1, total: 3 });
  });
  it('reads the theme from the file name and skips brass in Night Red', () => {
    expect(themeOf('/a/argos-night-red.png')).toBe('night-red');
    expect(themeOf('connection-charcoal.png')).toBe('charcoal');
    expect(themeOf('observe.png')).toBe('observatory');
    const f = write('x-night-red.png', png(2, 2, () => [200, 0, 0]));
    const r = auditFile(f, { brass: true });
    expect(r.nightRed?.pass).toBe(true);
    expect(r.brass).toBeUndefined();
  });
});

describe('CLI', () => {
  it('expands folders, gates on Night Red and refuses an empty gate', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const sub = path.join(dir, 'shots');
    fs.mkdirSync(sub);
    fs.writeFileSync(path.join(sub, 'a-night-red.png'), png(2, 2, () => [180, 0, 0]));
    fs.writeFileSync(path.join(sub, 'a-observatory.png'), png(2, 2, () => [0x90, 0x90, 0x90]));
    expect(pngFiles([sub]).map((f) => path.basename(f))).toEqual(['a-night-red.png', 'a-observatory.png']);
    expect(main(['--night-red', sub])).toBe(0);
    fs.writeFileSync(path.join(sub, 'b-night-red.png'), png(2, 2, () => [100, 100, 100]));
    expect(main(['--night-red', sub])).toBe(1);
    expect(main(['--night-red', path.join(sub, 'a-observatory.png')])).toBe(2);
    expect(main(['--force-night-red', path.join(sub, 'a-observatory.png')])).toBe(1);
    expect(main(['--nope', sub])).toBe(2);
    expect(main([path.join(sub, 'missing.png')])).toBe(1);
    log.mockRestore();
    err.mockRestore();
  });
});
