import { describe, expect, it } from 'vitest';
import {
  ambiguousComma,
  compactCount,
  count,
  DASH,
  factor,
  fixed,
  GROUP,
  groupDigits,
  int,
  mag,
  MINUS,
  parseNumber,
  percent,
  seconds,
  signed,
  signedInt,
  TIMES,
  times,
  withError,
} from './number';
import { clockUtc, duration, isoUtc, julian, julianDate, utcDate } from './time';

const G = GROUP;

describe('constants', () => {
  it('are the BRAND 5 code points', () => {
    expect(MINUS.codePointAt(0)).toBe(0x2212);
    expect(GROUP.codePointAt(0)).toBe(0x202f);
    expect(TIMES.codePointAt(0)).toBe(0x00d7);
  });
});

describe('fixed', () => {
  it('uses U+2212 and never prints a negative zero', () => {
    expect(fixed(-0.0123, 3)).toBe(`${MINUS}0.012`);
    expect(fixed(-0.0001, 3)).toBe('0.000');
    expect(fixed(-0, 1)).toBe('0.0');
    expect(fixed(2.5, 1)).toBe('2.5');
    expect(fixed(-4.4, 0)).toBe(`${MINUS}4`);
  });
  it('does not group decimals unless asked', () => {
    expect(fixed(12450.5, 1)).toBe('12450.5');
    expect(fixed(12450.5, 1, { group: true })).toBe(`12${G}450.5`);
    expect(fixed(-1234.56, 2, { group: true })).toBe(`${MINUS}1${G}234.56`);
    expect(fixed(999.96, 1, { group: true })).toBe(`1${G}000.0`);
  });
  it('prints a dash for missing values', () => {
    expect(fixed(Number.NaN, 2)).toBe(DASH);
    expect(fixed(Infinity, 2)).toBe(DASH);
    expect(fixed(null, 2)).toBe(DASH);
    expect(fixed(undefined, 2)).toBe(DASH);
  });
});

describe('signed', () => {
  it('always carries a sign, zero included', () => {
    expect(signed(0.004, 3)).toBe('+0.004');
    expect(signed(-0.004, 3)).toBe(`${MINUS}0.004`);
    expect(signed(0, 3)).toBe('+0.000');
    expect(signed(-0.0001, 3)).toBe('+0.000');
    expect(signed(48.85341, 5)).toBe('+48.85341');
    expect(signed(-122.27, 5)).toBe(`${MINUS}122.27000`);
    expect(signed(null, 1)).toBe(DASH);
  });
});

describe('int and grouping', () => {
  it('groups from 1 000 up with U+202F', () => {
    expect(int(999)).toBe('999');
    expect(int(1000)).toBe(`1${G}000`);
    expect(int(65535)).toBe(`65${G}535`);
    expect(int(12450)).toBe(`12${G}450`);
    expect(int(-1234567)).toBe(`${MINUS}1${G}234${G}567`);
    expect(int(-0.4)).toBe('0');
    expect(int(1234.5)).toBe(`1${G}235`);
  });
  it('signs integers', () => {
    expect(signedInt(300)).toBe('+300');
    expect(signedInt(-1000)).toBe(`${MINUS}1${G}000`);
    expect(signedInt(0)).toBe('+0');
  });
  it('groupDigits leaves short strings alone', () => {
    expect(groupDigits('123')).toBe('123');
    expect(groupDigits('1234')).toBe(`1${G}234`);
    expect(groupDigits('123456')).toBe(`123${G}456`);
  });
  it('never uses a comma or a plain space', () => {
    for (const v of [1000, 65535, 1234567, -98765]) {
      expect(int(v)).not.toMatch(/[, ]/);
    }
  });
});

describe('counts, factors, products', () => {
  it('counts with a noun', () => {
    expect(count(1, 'line')).toBe('1 line');
    expect(count(5000, 'line')).toBe(`5${G}000 lines`);
    expect(count(0, 'frame')).toBe('0 frames');
    expect(count(2, 'repeat', 'repeats')).toBe('2 repeats');
  });
  it('uses U+00D7, never the letter x', () => {
    expect(factor(2.5)).toBe(`2.5${TIMES}`);
    expect(factor(10, 0)).toBe(`10${TIMES}`);
    expect(times(20, '10 s')).toBe(`20 ${TIMES} 10 s`);
    expect(factor(Number.NaN)).toBe(DASH);
  });
});

describe('quantities', () => {
  it('magnitudes and uncertainties', () => {
    expect(mag(12.3449, 0.0121)).toBe(`12.345 ± 0.012`);
    expect(mag(-0.5)).toBe(`${MINUS}0.500`);
    expect(mag(7.692, null)).toBe('7.692');
    expect(withError(1.5, 0.25, 2)).toBe('1.50 ± 0.25');
  });
  it('seconds keep the UI precision, grouped', () => {
    expect(seconds(0.25)).toBe('0.250 s');
    expect(seconds(2)).toBe('2.0 s');
    expect(seconds(1200)).toBe(`1${G}200.0 s`);
    expect(seconds(null)).toBe(DASH);
  });
  it('percent', () => {
    expect(percent(1)).toBe('100 %');
    expect(percent(16)).toBe(`1${G}600 %`);
    expect(percent(0.125, 1)).toBe('12.5 %');
  });
  it('compact counts', () => {
    expect(compactCount(1)).toBe('1');
    expect(compactCount(999)).toBe('999');
    expect(compactCount(1000)).toBe('1k');
    expect(compactCount(12500)).toBe('12.5k');
    expect(compactCount(1_500_000)).toBe('1.5M');
    expect(compactCount(-2000)).toBe(`${MINUS}2k`);
  });
  it('compact counts round before choosing the unit (technical review)', () => {
    expect(compactCount(999950)).toBe('1M');
    expect(compactCount(999999)).toBe('1M');
    expect(compactCount(999.6)).toBe('1k');
    expect(compactCount(-0.4)).toBe('0');
  });
  it('never groups into an exponent', () => {
    expect(int(1e21)).toBe('1e+21');
    expect(fixed(-2e22, 0, { group: true })).toBe(`${MINUS}2e+22`);
  });
  it('seconds choose decimals from the rounded value', () => {
    expect(seconds(0.9996)).toBe('1.0 s');
    expect(seconds(0.9994)).toBe('0.999 s');
    expect(seconds(-0.9996)).toBe(`${MINUS}1.0 s`);
  });
});

describe('parseNumber', () => {
  it('reads point and comma decimals', () => {
    expect(parseNumber('0.5')).toBe(0.5);
    expect(parseNumber('0,5')).toBe(0.5);
    expect(parseNumber('  2,0  ')).toBe(2);
    expect(parseNumber('.5')).toBe(0.5);
    expect(parseNumber(',5')).toBe(0.5);
    expect(parseNumber('3.')).toBe(3);
  });
  it('a single comma is always a decimal comma (no silent 1 000x)', () => {
    expect(parseNumber('0,500')).toBe(0.5);
    expect(parseNumber('1,234')).toBe(1.234);
  });
  it('in a whole-number field one comma before three digits groups (no silent 1 000x)', () => {
    expect(parseNumber('60,000', { integer: true })).toBe(60000);
    expect(parseNumber('1,000', { integer: true })).toBe(1000);
    expect(parseNumber(`${MINUS}1,250`, { integer: true })).toBe(-1250);
    expect(parseNumber('1,5', { integer: true })).toBe(1.5); // refused as not whole by the field
    expect(parseNumber('1,0000', { integer: true })).toBe(1); // not a group of three: a decimal comma
    expect(parseNumber('60,000')).toBe(60); // decimal fields: see ambiguousComma
  });
  it('flags a comma that reads both ways in a decimal field', () => {
    expect(ambiguousComma('60,000')).toEqual({ grouped: `60${G}000`, decimal: '60.000' });
    expect(ambiguousComma(' -1,250 ')).toEqual({ grouped: `${MINUS}1${G}250`, decimal: `${MINUS}1.250` });
    for (const t of ['0,500', '1,5', '1,0000', '12,450.5', '1,234,567', '60000', '60.000', '1 000']) {
      expect(ambiguousComma(t), t).toBeNull();
    }
  });
  it('reads any minus sign and a plus', () => {
    expect(parseNumber(`${MINUS}5.25`)).toBe(-5.25);
    expect(parseNumber('-5,25')).toBe(-5.25);
    expect(parseNumber('–3')).toBe(-3);
    expect(parseNumber('+12')).toBe(12);
  });
  it('ignores spaces of every width as grouping', () => {
    expect(parseNumber(`65${G}535`)).toBe(65535);
    expect(parseNumber('12 450')).toBe(12450);
    expect(parseNumber('12 450,5')).toBe(12450.5);
    expect(parseNumber('12 450')).toBe(12450);
    expect(parseNumber(int(-1234567))).toBe(-1234567);
  });
  it('groups with repeated marks, decimal is the last of two marks', () => {
    expect(parseNumber('1,234,567')).toBe(1234567);
    expect(parseNumber('1.234.567')).toBe(1234567);
    expect(parseNumber('12,450.5')).toBe(12450.5);
    expect(parseNumber('12.450,5')).toBe(12450.5);
  });
  it('accepts exponents', () => {
    expect(parseNumber('1e-3')).toBe(0.001);
    expect(parseNumber('2,5E2')).toBe(250);
  });
  it('round-trips every formatter', () => {
    for (const v of [0, 1, -1, 999, 1000, 65535, -12450, 1234567]) {
      expect(parseNumber(int(v))).toBe(v);
    }
    for (const v of [0.012, -0.012, 12.345, -1234.56]) {
      expect(parseNumber(fixed(v, 3, { group: true }))).toBeCloseTo(v, 9);
      expect(parseNumber(signed(v, 3))).toBeCloseTo(v, 9);
    }
  });
  it('refuses what is not a number', () => {
    for (const t of ['', '   ', 'abc', '1.2.3', '1,2,3', '12,45.6', '1-2', '--1', '+-1', '.', ',', 'e5', '1e', '12a', '0x10', 'Infinity', 'NaN']) {
      expect(parseNumber(t), t).toBeNull();
    }
  });
});

describe('time', () => {
  const t = Date.UTC(2026, 10, 1, 21, 34, 5) / 1000;
  it('clocks and dates in UTC', () => {
    expect(clockUtc(t)).toBe('21:34:05');
    expect(clockUtc(t, false)).toBe('21:34');
    expect(clockUtc(59.6)).toBe('00:01:00');
    expect(utcDate(t)).toBe('2026-11-01');
    expect(isoUtc(t)).toBe('2026-11-01 21:34:05 UTC');
    expect(clockUtc(Number.NaN)).toBe(DASH);
  });
  it('durations in the BRAND 5 style', () => {
    expect(duration(45)).toBe('45 s');
    expect(duration(59.6)).toBe('1m 00s');
    expect(duration(750)).toBe('12m 30s');
    expect(duration(3900)).toBe('1h 05m');
    expect(duration(-1)).toBe(DASH);
  });
  it('Julian dates with 5 decimals, never grouped', () => {
    expect(julianDate(0)).toBe(2440587.5);
    expect(julian(2461346.401234)).toBe('2461346.40123');
    expect(julian(Number.NaN)).toBe(DASH);
  });
});
