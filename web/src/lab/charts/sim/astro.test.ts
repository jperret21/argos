import { describe, expect, it } from 'vitest';
import { airmass, bjdApprox, crossings, gmstDeg, horizontal, jdFromUnix, maximum, moonPosition, sunAltitude, sunPosition, TWILIGHT } from './astro';
import { SITE, TARGET } from './night';

const utc = (y: number, mo: number, d: number, h = 0, mi = 0, s = 0) => Date.UTC(y, mo - 1, d, h, mi, s) / 1000;

describe('astro', () => {
  it('Julian dates', () => {
    expect(jdFromUnix(utc(2000, 1, 1, 12))).toBeCloseTo(2451545.0, 9);
    expect(jdFromUnix(utc(2026, 11, 1, 22, 2))).toBeCloseTo(2461346.41806, 4);
  });

  it('GMST at J2000.0', () => {
    expect(gmstDeg(2451545.0)).toBeCloseTo(280.46061837, 6);
  });

  it('Sun at the June solstice: declination +23.44, Paris noon altitude ~64.6', () => {
    const sun = sunPosition(jdFromUnix(utc(2026, 6, 21, 8, 25)));
    expect(sun.dec).toBeCloseTo(23.44, 1);
    // Local apparent noon in Paris is about 11:50 UTC in late June.
    const noon = maximum((t) => sunAltitude(SITE, t), utc(2026, 6, 21, 10), utc(2026, 6, 21, 14));
    expect(noon.value).toBeGreaterThan(64.2);
    expect(noon.value).toBeLessThan(65.0);
    expect(Math.abs(noon.t - utc(2026, 6, 21, 11, 50))).toBeLessThan(6 * 60);
  });

  it('Paris, 2026-11-01: sunset ~16:28 UTC, astronomical dusk ~18:15 UTC', () => {
    const set = crossings((t) => sunAltitude(SITE, t), TWILIGHT.sunset, utc(2026, 11, 1, 14), utc(2026, 11, 1, 20));
    expect(set).toHaveLength(1);
    expect(Math.abs(set[0].t - utc(2026, 11, 1, 16, 28))).toBeLessThan(6 * 60);
    const dusk = crossings((t) => sunAltitude(SITE, t), TWILIGHT.astronomical, utc(2026, 11, 1, 14), utc(2026, 11, 1, 22));
    expect(Math.abs(dusk[0].t - utc(2026, 11, 1, 18, 15))).toBeLessThan(8 * 60);
  });

  it('SW And transits about 70.5 deg high around 21:45 UTC', () => {
    const peak = maximum((t) => horizontal(TARGET.pos, SITE, t).alt, utc(2026, 11, 1, 18), utc(2026, 11, 2, 2));
    expect(peak.value).toBeCloseTo(90 - 48.8566 + 29.4011, 0);
    expect(Math.abs(peak.t - utc(2026, 11, 1, 21, 45))).toBeLessThan(20 * 60);
  });

  it('Moon near last quarter on 2026-11-01', () => {
    const m = moonPosition(jdFromUnix(utc(2026, 11, 1, 23)));
    expect(m.illumination).toBeGreaterThan(0.3);
    expect(m.illumination).toBeLessThan(0.75);
  });

  it('airmass: 1 at the zenith, ~2 at 30 deg', () => {
    expect(airmass(90)).toBeCloseTo(1, 3);
    expect(airmass(30)).toBeCloseTo(1.995, 2);
  });

  it('BJD - JD stays within the light-time bounds (+/- 8.4 min) plus TT-UTC', () => {
    const t = utc(2026, 11, 1, 22);
    const d = (bjdApprox(t, TARGET.pos) - jdFromUnix(t)) * 86400;
    expect(Math.abs(d - 69.184)).toBeLessThan(510);
  });
});
