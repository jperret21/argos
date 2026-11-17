/**
 * The web stretch must agree with argos/core/imaging/stretch.py.
 *
 * Every expected number below was produced by running the Python module on
 * exactly these arrays (repo virtualenv, numpy 1.26.4, 2026-11-01):
 *
 *   PYTHONPATH=. .venv/bin/python -c "
 *   import numpy as np
 *   from argos.core.imaging.stretch import auto_stf, auto_levels, apply_stretch, _mtf
 *   A = np.array(<CASE_A>, dtype=np.uint16).reshape(6, 8)
 *   print(auto_stf(A), auto_levels(A))
 *   b, w, m = auto_stf(A); print(apply_stretch(A, b, w, 'Linear', m).ravel().tolist())
 *   ..."
 *
 * (median / MAD / percentile were printed from the same float32 arrays that
 * auto_stf builds.) Case E is rint(normal(1000, 20, 100)) from
 * np.random.default_rng(42) with E[17] = 1400 and E[63] = 1500.
 */

import { describe, expect, it } from 'vitest';
import {
  autoLevels,
  autoStf,
  histogram16,
  medianAbsDeviation,
  median,
  mtf,
  percentile,
  stdDev,
  stretchValue,
  toDisplayByte,
  type StretchParams,
} from './stretch';

// 6x8 sky on the Seestar 16-ADU grid, two stars and a hot pixel.
const A = [
  1104, 1120, 1088, 1104, 1136, 1104, 1120, 1088, 1120, 1104, 1104, 2400, 5200, 2300, 1104, 1120,
  1088, 1136, 1120, 5600, 30000, 5100, 1104, 1104, 1104, 1104, 1088, 2200, 5000, 2350, 1120, 1088,
  1136, 1120, 1104, 1104, 1120, 1104, 1088, 65520, 1104, 1088, 1120, 1104, 1104, 1136, 1400, 1104,
];
// MAD == 0 (more than half the samples equal the median): std() fallback.
const B = [500, 500, 500, 500, 500, 500, 500, 900, 1200, 3000, 40000];
// Constant frame: white <= black guard.
const C = new Array<number>(15).fill(1000);
// Even count, median and MAD are half-integers.
const D = [3, 17, 250, 1023, 4095, 12, 7, 999, 60000, 31];
// Realistic sky noise: the auto midtones are NOT clamped.
const E = [
  1006, 979, 1015, 1019, 961, 974, 1003, 994, 1000, 983, 1018, 1016, 1001, 1023, 1009, 983, 1007,
  1400, 1018, 999, 996, 986, 1024, 997, 991, 993, 1011, 1007, 1008, 1009, 1043, 992, 990, 984, 1012,
  1023, 998, 983, 984, 1013, 1015, 1011, 987, 1005, 1002, 1004, 1017, 1004, 1014, 1001, 1006, 1013,
  971, 994, 991, 987, 994, 1030, 983, 1019, 966, 993, 1003, 1500, 1014, 1016, 993, 991, 1017, 996,
  974, 977, 982, 1010, 1003, 1014, 991, 1003, 1013, 994, 1009, 987, 993, 992, 976, 1010, 991, 1000,
  1010, 1009, 1013, 998, 992, 998, 966, 971, 974, 980, 1008, 982,
];

const u16 = (a: number[]) => Uint16Array.from(a);

describe('order statistics match numpy', () => {
  const cases: Array<[string, number[], number, number, number]> = [
    // name, data, np.median, MAD, np.percentile(a, 99.8)
    ['A', A, 1112.0, 8.0, 62181.11999999996],
    ['B', B, 500.0, 0.0, 39260.000000000015],
    ['C', C, 1000.0, 0.0, 1000.0],
    ['D', D, 140.5, 135.5, 58993.70999999996],
    ['E', E, 1000.5, 10.5, 1480.2000000000007],
  ];
  for (const [name, data, med, mad, p998] of cases) {
    it(`case ${name}`, () => {
      const h = histogram16(u16(data));
      expect(h.n).toBe(data.length);
      expect(h.min).toBe(Math.min(...data));
      expect(h.max).toBe(Math.max(...data));
      expect(median(h)).toBe(med);
      expect(medianAbsDeviation(h, med)).toBe(mad);
      expect(percentile(h, 99.8)).toBe(p998);
    });
  }

  it('std fallback agrees with float32 numpy std to float32 precision', () => {
    // numpy: 11274.5751953125 (B) and 17825.515625 (D), accumulated in float32.
    expect(stdDev(histogram16(u16(B)))).toBeCloseTo(11274.5751953125, 2);
    expect(stdDev(histogram16(u16(D)))).toBeCloseTo(17825.515625, 1);
  });
});

describe('autoStf (stretch.auto_stf)', () => {
  const expected: Array<[string, number[], number, number, number]> = [
    ['A', A, 1088.0, 62181.11999999996, 0.01],
    ['B', B, 500.0, 39260.000000000015, 0.01],
    ['C', C, 1000.0, 1001.0, 0.01],
    ['D', D, 3.0, 58993.70999999996, 0.01],
    ['E', E, 961.0, 1480.2000000000007, 0.19809428284854538],
  ];
  for (const [name, data, black, white, midtones] of expected) {
    it(`case ${name}`, () => {
      const p = autoStf(u16(data));
      expect(p.black).toBe(black);
      expect(p.white).toBe(white);
      expect(p.midtones).toBeCloseTo(midtones, 14);
      expect(p.mode).toBe('linear');
    });
  }

  it('accepts a precomputed histogram', () => {
    expect(autoStf(histogram16(u16(E)))).toEqual(autoStf(u16(E)));
  });
});

describe('autoLevels (stretch.auto_levels)', () => {
  const expected: Array<[string, number[], number, number]> = [
    ['A', A, 1088.0, 48825.60000000004],
    ['B', B, 500.0, 36300.000000000015],
    ['C', C, 1000.0, 1001.0],
    ['D', D, 3.36, 54968.55000000001],
    ['E', E, 965.95, 1401.0000000000005],
  ];
  for (const [name, data, black, white] of expected) {
    it(`case ${name}`, () => {
      const { black: b, white: w } = autoLevels(u16(data));
      expect(b).toBeCloseTo(black, 9);
      expect(w).toBeCloseTo(white, 9);
    });
  }
});

describe('transfer (apply_stretch -> uint8)', () => {
  const bytes = (data: number[], p: StretchParams) => data.map((v) => toDisplayByte(stretchValue(v, p)));

  it('linear with the auto-STF of case A', () => {
    const p = autoStf(u16(A));
    expect(bytes(A, p)).toEqual([
      6, 13, 0, 6, 18, 6, 13, 0, 13, 6, 6, 175, 224, 170, 6, 13, 0, 18, 13, 226, 252, 223, 6, 6, 6,
      6, 0, 165, 222, 172, 13, 0, 18, 13, 6, 6, 13, 6, 0, 255, 6, 0, 13, 6, 6, 18, 86, 6,
    ]);
  });

  it('linear with the auto-STF of case E (unclamped midtones)', () => {
    const p = autoStf(u16(E));
    expect(bytes(E, p)).toEqual([
      71, 32, 82, 86, 0, 24, 67, 55, 63, 39, 85, 83, 64, 90, 74, 39, 72, 244, 85, 62, 58, 43, 91, 59,
      51, 54, 77, 72, 73, 74, 110, 52, 49, 40, 78, 90, 60, 39, 40, 79, 82, 77, 45, 70, 66, 68, 84,
      68, 80, 64, 71, 79, 19, 55, 51, 45, 55, 98, 39, 86, 10, 54, 67, 255, 80, 83, 54, 51, 84, 58, 24,
      29, 37, 76, 67, 80, 51, 67, 79, 55, 74, 45, 54, 52, 27, 76, 51, 63, 76, 74, 79, 60, 52, 60, 10,
      19, 24, 34, 73, 37,
    ]);
  });

  it('log, black 1000 white 20000, neutral midtones', () => {
    const p: StretchParams = { black: 1000, white: 20000, midtones: 0.5, mode: 'log' };
    expect(bytes(A, p)).toEqual([
      69, 73, 64, 69, 77, 69, 73, 64, 73, 69, 69, 159, 199, 157, 69, 73, 64, 77, 73, 203, 255, 199,
      69, 69, 69, 69, 64, 154, 198, 158, 73, 64, 77, 73, 69, 69, 73, 69, 64, 255, 69, 64, 73, 69, 69,
      77, 114, 69,
    ]);
  });

  it('asinh, black 1000 white 20000, midtones 0.3', () => {
    const p: StretchParams = { black: 1000, white: 20000, midtones: 0.3, mode: 'asinh' };
    expect(bytes(A, p)).toEqual([
      23, 26, 19, 23, 29, 23, 26, 19, 26, 23, 23, 149, 204, 144, 23, 26, 19, 29, 26, 208, 255, 203,
      23, 23, 23, 23, 19, 139, 202, 147, 26, 19, 29, 26, 23, 23, 26, 23, 19, 255, 23, 19, 26, 23, 23,
      29, 73, 23,
    ]);
  });

  it('linear, black 1000 white 6000, neutral midtones', () => {
    const p: StretchParams = { black: 1000, white: 6000, midtones: 0.5, mode: 'linear' };
    expect(bytes(A, p)).toEqual([
      5, 6, 4, 5, 7, 5, 6, 4, 6, 5, 5, 71, 214, 66, 5, 6, 4, 7, 6, 235, 255, 209, 5, 5, 5, 5, 4, 61,
      204, 69, 6, 4, 7, 6, 5, 5, 6, 5, 4, 255, 5, 4, 6, 5, 5, 7, 20, 5,
    ]);
  });
});

describe('mtf (stretch._mtf)', () => {
  const xs = [0.0, 0.01, 0.1, 0.25, 0.5, 0.75, 1.0];
  const expected: Array<[number, number[]]> = [
    [0.05, [0.0, 0.16101694915254236, 0.6785714285714285, 0.8636363636363635, 0.95, 0.9827586206896549, 0.9999999999999999]],
    [0.25, [0.0, 0.029411764705882353, 0.25000000000000006, 0.5, 0.75, 0.9, 1.0]],
    [0.8, [0.0, 0.0025188916876574302, 0.02702702702702702, 0.0769230769230769, 0.19999999999999996, 0.4285714285714285, 1.0]],
  ];
  for (const [m, ys] of expected) {
    it(`m = ${m}`, () => {
      xs.forEach((x, i) => expect(mtf(x, m)).toBeCloseTo(ys[i]!, 14));
      expect(mtf(m, m)).toBeCloseTo(0.5, 14);
    });
  }
});

describe('histogram16', () => {
  it('counts every channel sample (ravel semantics) and handles empty input', () => {
    const h = histogram16(u16([0, 65535, 65535, 7]));
    expect(h.counts[0]).toBe(1);
    expect(h.counts[65535]).toBe(2);
    expect(h.counts[7]).toBe(1);
    expect([h.min, h.max]).toEqual([0, 65535]);
    const empty = histogram16(new Uint16Array(0));
    expect(empty.n).toBe(0);
    expect(autoStf(empty)).toEqual({ black: 0, white: 65535, midtones: 0.5, mode: 'linear' });
  });
});
