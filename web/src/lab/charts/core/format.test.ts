import { describe, expect, it } from 'vitest';
import { clockUtc, duration, fixed, GROUP, grouped, mag, MINUS, signed } from './format';

describe('format', () => {
  it('uses U+2212 and never prints a negative zero', () => {
    expect(fixed(-0.0123, 3)).toBe(`${MINUS}0.012`);
    expect(fixed(-0.0001, 3)).toBe('0.000');
    expect(signed(0.004, 3)).toBe('+0.004');
    expect(signed(-0.004, 3)).toBe(`${MINUS}0.004`);
    expect(signed(0, 3)).toBe('0.000');
  });
  it('groups thousands', () => {
    expect(grouped(65535)).toBe(`65${GROUP}535`);
    expect(grouped(999)).toBe('999');
    expect(grouped(-1234567)).toBe(`${MINUS}1${GROUP}234${GROUP}567`);
  });
  it('magnitudes, clocks, durations', () => {
    expect(mag(12.3449, 0.0121)).toBe('12.345 ± 0.012');
    expect(clockUtc(Date.UTC(2026, 10, 1, 21, 34, 5) / 1000)).toBe('21:34:05');
    expect(clockUtc(59.6)).toBe('00:01:00');
    expect(duration(45)).toBe('45 s');
    expect(duration(750)).toBe('12m 30s');
    expect(duration(3900)).toBe('1h 05m');
  });
});
