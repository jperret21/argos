import { describe, expect, it } from 'vitest';
// The lab's low-precision sky model, in tests only (PROPOSAL section 6, W6): it stands in for
// the server's A65 samples so the model is checked on a realistic night, not on a toy curve.
import { crossings as labCrossings, horizontal, sunAltitude, type RaDec } from '../../lab/charts/sim/astro';
import { SITE } from '../../lab/charts/sim/night';
import type { Visibility } from '../api/sequence';
import { aboveSpans, airmass, crossings, factsLine, hoverRead, nearestIndex, peakWords, runCheck, splitAtLimit, twilightLevel, twilightSpans, zoneLabel } from './visibility';

const T_CRB: RaDec = { ra: (15 + 59 / 60 + 30.2 / 3600) * 15, dec: 25 + 55 / 60 + 13 / 3600 };
const T0 = Date.UTC(2026, 10, 1, 15, 0) / 1000;
const T1 = Date.UTC(2026, 10, 2, 8, 0) / 1000;
const STEP = 600; // A65 default step_min=10

function night(pos: RaDec, withSun = true): Visibility {
  const n = Math.floor((T1 - T0) / STEP) + 1;
  const t = new Float64Array(n);
  const alt = new Float64Array(n);
  const sun = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    t[i] = T0 + i * STEP;
    alt[i] = horizontal(pos, SITE, t[i]).alt;
    sun[i] = sunAltitude(SITE, t[i]);
  }
  const sc = crossings(t, sun, -18);
  const dusk = sc.find((c) => !c.rising)!.t;
  const dawn = sc.find((c) => c.rising)!.t;
  let pk = 0;
  for (let i = 1; i < n; i++) if (alt[i] > alt[pk]) pk = i;
  return { siteName: 'Test site', night: '2026-11-01', t, alt, sun: withSun ? sun : null, peak: { t: t[pk], alt: alt[pk] }, window: null, windows: [], minAlt: 30, dark: { start: dusk, end: dawn }, notes: [] };
}

describe('crossings and spans', () => {
  it('interpolates linearly between samples', () => {
    const c = crossings([0, 10, 20], [20, 40, 20], 30);
    expect(c).toEqual([
      { t: 5, rising: true },
      { t: 15, rising: false },
    ]);
  });

  it('agrees with the lab model on a real night within a minute (10 min samples)', () => {
    const v = night(T_CRB);
    const f = (x: number) => horizontal(T_CRB, SITE, x).alt;
    const ref = labCrossings(f, 30, T0, T1, 60);
    const got = crossings(v.t, v.alt, 30);
    expect(got.length).toBe(ref.length);
    got.forEach((c, i) => {
      expect(c.rising).toBe(ref[i].rising);
      expect(Math.abs(c.t - ref[i].t)).toBeLessThan(60);
    });
  });

  it('keeps the spans above the limit and clips them to the night', () => {
    const t = [0, 100, 200, 300, 400, 500];
    const a = [20, 40, 40, 20, 40, 40];
    expect(aboveSpans(t, a, 30)).toEqual([
      { start: 50, end: 250 },
      { start: 350, end: 500 },
    ]);
    expect(aboveSpans(t, a, 30, { start: 100, end: 400 })).toEqual([
      { start: 100, end: 250 },
      { start: 350, end: 400 },
    ]);
    expect(aboveSpans(t, a, 50)).toEqual([]);
  });
});

describe('twilight', () => {
  it('names the levels at the standard limits', () => {
    expect([5, -0.5, -3, -10, -15, -20].map(twilightLevel)).toEqual([4, 4, 3, 2, 1, 0]);
  });

  it('steps from the Sun samples, the night left clear', () => {
    const v = night(T_CRB);
    const spans = twilightSpans(v);
    expect(spans[0].level).toBe(4); // the afternoon
    expect(spans.map((s) => s.level)).toContain(1);
    // No wash inside the astronomical night.
    const dark = v.dark!;
    for (const s of spans) expect(s.end <= dark.start + STEP || s.start >= dark.end - STEP).toBe(true);
  });

  it('without the Sun, one wash outside the night window', () => {
    const v = night(T_CRB, false);
    const spans = twilightSpans(v);
    expect(spans).toEqual([
      { start: T0, end: v.dark!.start, level: 2 },
      { start: v.dark!.end, end: v.t[v.t.length - 1], level: 2 },
    ]);
    expect(twilightSpans({ ...v, dark: null })).toEqual([]);
  });
});

describe('the curve split at the limit', () => {
  it('joins the solid and the dashed parts at the crossing samples', () => {
    const s = splitAtLimit([10, 20, 35, 40, 45, 25], 30);
    expect(s.above).toEqual([null, 20, 35, 40, 45, 25]);
    expect(s.below).toEqual([10, 20, 35, null, 45, 25]);
  });
});

describe('airmass', () => {
  it('matches sky_geometry.compute_airmass (Pickering 2002, Qt values)', () => {
    // Values printed by argos.core.imaging.sky_geometry.compute_airmass on the fixed code.
    const ref: [number, number | null][] = [
      [90, 1.0],
      [60, 1.1541],
      [30, 1.9932],
      [15, 3.8082],
      [5, 10.3337],
      [1, 26.6438],
      [0.5, 31.7423],
      [0, null],
      [-3, null],
    ];
    for (const [a, m] of ref) expect(airmass(a)).toBe(m);
  });
});

describe('the planning check', () => {
  const above = [{ start: 0, end: 5000 }];
  const win = [{ start: 1000, end: 5000 }];
  const dark = { start: 1000, end: 6000 };

  it('says the run stays above the limit', () => {
    expect(runCheck({ start: 2000, end: 3000 }, above, win, 30, dark, 'T CrB')).toEqual({ ok: true, text: 'Planned run 00:33 → 00:50 UTC stays above 30°' });
  });

  it('tells "below the limit" from "outside the night", and never moves the run', () => {
    // High before dusk: outside the night, not below the limit.
    const c = runCheck({ start: 400, end: 5600 }, above, win, 30, dark, 'T CrB')!;
    expect(c.ok).toBe(false);
    expect(c.text).toBe('Planned run 00:06 → 01:33 UTC: last 10m 00s below 30°; starts 10m 00s before astronomical dusk');
    // Rising through the limit after dusk: the first part is below it.
    const r = runCheck({ start: 1200, end: 3000 }, [{ start: 1800, end: 5000 }], [{ start: 1800, end: 5000 }], 30, dark, 'T CrB')!;
    expect(r.text).toBe('Planned run 00:20 → 00:50 UTC: first 10m 00s below 30°');
  });

  it('says when the source never clears the limit at night, and nothing without a run', () => {
    expect(runCheck({ start: 0, end: 10 }, above, [], 30, dark, 'T CrB')?.text).toBe('T CrB stays below 30° during the astronomical night');
    expect(runCheck(null, above, win, 30, dark, 'T CrB')).toBeNull();
  });
});

describe('readouts', () => {
  it('finds the nearest sample', () => {
    const t = [0, 10, 20, 30];
    expect([-5, 4, 6, 14, 26, 40].map((x) => nearestIndex(t, x))).toEqual([0, 0, 1, 1, 3, 3]);
  });

  it('names the zone by its offset', () => {
    expect([0, 60, -180, 330, -570].map(zoneLabel)).toEqual(['UTC', 'UTC+1', 'UTC−3', 'UTC+5:30', 'UTC−9:30']);
  });

  it('reads a sample in words: UTC, local, altitude, airmass, phase', () => {
    const v = night(T_CRB);
    const i = nearestIndex(v.t, v.dark!.start + 1800);
    const r = hoverRead(v, i, 60);
    expect(r.phase).toBe('night');
    expect(r.alt).toMatch(/^\d+\.\d°$/);
    expect(hoverRead({ ...v, sun: null }, i, 60).phase).toBe('astronomical night');
    expect(hoverRead({ ...v, sun: null }, 0, 60).phase).toBe('outside the astronomical night');
  });

  it('writes the facts line with UTC named once per time range', () => {
    const v = night(T_CRB);
    const line = factsLine(v, aboveSpans(v.t, v.alt, 30, v.dark), 30);
    expect(line).toMatch(/^night \d\d:\d\d → \d\d:\d\d UTC · peak \d+\.\d° at \d\d:\d\d · (above 30° .*|never above 30° at night)$/);
  });
});

describe('peak words (design review W6a)', () => {
  const dark = { start: 1000, end: 40000 };
  it('says "highest at night" with the edge when the source culminates outside the night', () => {
    expect(peakWords({ dark, peak: { t: 1000, alt: 65.94 } })).toMatch(/^highest at night 65\.9° at \d\d:\d\d \(dusk\)$/);
    expect(peakWords({ dark, peak: { t: 39800, alt: 41 } })).toMatch(/\(dawn\)$/);
  });
  it('keeps "peak" for a culmination inside the night', () => {
    expect(peakWords({ dark, peak: { t: 20000, alt: 80 } })).toMatch(/^peak 80\.0° at \d\d:\d\d$/);
    expect(peakWords({ dark, peak: null })).toBeNull();
  });
});
