import { describe, expect, it } from 'vitest';
import {
  formatDec,
  formatDegrees,
  formatRA,
  formatSigned,
  MINUS,
  parseDec,
  parseRA,
  separationDeg,
} from './astro';

// M42: RA 05h 35m 17.3s, Dec −05° 23′ 28″ (the values the Qt app and the
// website use as their example).
const M42_RA = 5 + 35 / 60 + 17.3 / 3600;
const M42_DEC = -(5 + 23 / 60 + 28 / 3600);

describe('formatRA', () => {
  it('formats zero-padded tenths of a second', () => {
    expect(formatRA(M42_RA)).toBe('05h 35m 17.3s');
    expect(formatRA(0)).toBe('00h 00m 00.0s');
    expect(formatRA(20 + 3 / 60 + 16.3 / 3600)).toBe('20h 03m 16.3s');
  });

  it('rounds once then carries (never prints 60.0s)', () => {
    expect(formatRA(1 + 59 / 60 + 59.96 / 3600)).toBe('02h 00m 00.0s');
    expect(formatRA(23 + 59 / 60 + 59.97 / 3600)).toBe('00h 00m 00.0s');
  });

  it('wraps into [0, 24)', () => {
    expect(formatRA(24 + M42_RA)).toBe('05h 35m 17.3s');
    expect(formatRA(-1)).toBe('23h 00m 00.0s');
  });

  it('shows a dash for non-finite input', () => {
    expect(formatRA(Number.NaN)).toBe('—');
  });
});

describe('formatDec', () => {
  it('always shows the sign, with prime and double prime', () => {
    expect(formatDec(M42_DEC)).toBe(`${MINUS}05° 23′ 28″`);
    expect(formatDec(5 + 23 / 60 + 28 / 3600)).toBe('+05° 23′ 28″');
    expect(formatDec(58 + 56 / 60 + 26 / 3600)).toBe('+58° 56′ 26″');
  });

  it('keeps the minus for −00° and drops it when the value rounds to zero', () => {
    expect(formatDec(-0.5)).toBe(`${MINUS}00° 30′ 00″`);
    expect(formatDec(-1e-6)).toBe('+00° 00′ 00″');
  });

  it('carries rounded seconds into minutes and degrees', () => {
    expect(formatDec(10 + 59 / 60 + 59.6 / 3600)).toBe('+11° 00′ 00″');
    expect(formatDec(-89.99999)).toBe(`${MINUS}90° 00′ 00″`);
  });

  it('offers tenths of an arcsecond where astrometry needs them', () => {
    expect(formatDec(-(4 / 60 + 7.2 / 3600), 1)).toBe(`${MINUS}00° 04′ 07.2″`);
  });
});

describe('formatSigned / formatDegrees', () => {
  it('uses U+2212 for negatives and never shows −0.00', () => {
    expect(formatSigned(-12.345, 2)).toBe(`${MINUS}12.35`);
    expect(formatSigned(-0.001, 2)).toBe('0.00');
    expect(formatDegrees(41.2712)).toBe('41.27°');
    expect(formatDegrees(-3.5)).toBe(`${MINUS}3.50°`);
    expect(formatDegrees(null)).toBe('—');
  });
});

describe('parseRA', () => {
  const cases: [string, number][] = [
    ['05h 35m 17.3s', M42_RA],
    ['5h35m17.3s', M42_RA],
    ['05:35:17.3', M42_RA],
    ['05 35 17.3', M42_RA],
    ['  5 35 17,3 ', M42_RA],
    ['5 30', 5.5],
    ['5h', 5],
    ['5.5', 5.5],
    ['83.82°', 83.82 / 15],
    ['83.82 deg', 83.82 / 15],
    ['83.82d', 83.82 / 15],
  ];
  it.each(cases)('parses %s', (text, hours) => {
    const r = parseRA(text);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value).toBeCloseTo(hours, 10);
  });

  it.each(['', '24', '25h', '5 60', '5 30 60', '-5', '5.5 30', 'abc', '400°', '5 30 10 2'])(
    'rejects %j',
    (text) => {
      expect(parseRA(text).ok).toBe(false);
    },
  );
});

describe('parseDec', () => {
  const cases: [string, number][] = [
    [`${MINUS}05° 23′ 28″`, M42_DEC],
    ['-05 23 28', M42_DEC],
    ['-5:23:28', M42_DEC],
    ['-5d23m28s', M42_DEC],
    [`-5°23'28"`, M42_DEC],
    ['+58 56 26', 58 + 56 / 60 + 26 / 3600],
    ['58.94', 58.94],
    ['−5.391', -5.391],
    ['5.391°', 5.391],
    ['-0 30', -0.5],
    ['-00:30:00', -0.5],
    ['90', 90],
  ];
  it.each(cases)('parses %s', (text, degrees) => {
    const r = parseDec(text);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value).toBeCloseTo(degrees, 10);
  });

  it.each(['', '91', '-90 30', '5 60', '+-5', 'north', '5 23 28 1'])('rejects %j', (text) => {
    expect(parseDec(text).ok).toBe(false);
  });

  it('round-trips through the formatter', () => {
    const r = parseDec(formatDec(M42_DEC));
    expect(r.ok && formatDec(r.value)).toBe(formatDec(M42_DEC));
    const a = parseRA(formatRA(M42_RA));
    expect(a.ok && formatRA(a.value)).toBe(formatRA(M42_RA));
  });
});

describe('separationDeg', () => {
  it('matches simple geometry', () => {
    expect(separationDeg(0, 0, 0, 10)).toBeCloseTo(10, 10);
    expect(separationDeg(0, 0, 1, 0)).toBeCloseTo(15, 10);
    expect(separationDeg(3, 89, 15, 89)).toBeCloseTo(2, 10);
  });
});
