import { describe, expect, it } from 'vitest';
import { CurveColumns, drawable, pyHypot, unixFromJd, type LcPoint } from './columns';
import { TrailingBand, fluxBaseline, meanSd, medianOf } from './trailing';
import { LiveCurveStore, catalogueMag, type PointEvent } from './store';
import { checkRung, checkSigma, facetData, flagCounts, niceSplits, padPixels, visibleRange, yExtent } from './facets';
import { TSV_HEADER, curveTsv, isoMs, readoutAt } from './readout';
import { FLAG_SATURATED, FLAG_SUSPECT } from '../uplot/markers';

const JD0 = 2461282.4; // 2026-08-29 21:36 UTC
const DT = 30 / 86400;

function pt(i: number, extra: Partial<LcPoint> = {}): LcPoint {
  return {
    jd_utc: JD0 + i * DT,
    mag: 11 + 0.01 * i,
    mag_err: 0.01,
    formal_mag_err: 0.01,
    bjd_tdb: JD0 + i * DT + 0.0023,
    airmass: 1.2,
    comps_used: 4,
    saturated: false,
    suspect: false,
    relative_flux: 1 + 0.001 * i,
    relative_flux_err: 0.002,
    relative_comps_used: 4,
    ...extra,
  };
}

function ev(key: string, role: string, i: number, extra: Partial<LcPoint> = {}, more: Partial<PointEvent> = {}): PointEvent {
  return { key, role, name: key, auid: '', point: pt(i, extra), ...more };
}

describe('curve columns', () => {
  it('appends, grows, keeps every LcPoint field and turns None into NaN', () => {
    const c = new CurveColumns(4);
    for (let i = 0; i < 10; i++) expect(c.put(pt(i)).how).toBe('appended');
    expect(c.n).toBe(10);
    expect(c.capacity).toBeGreaterThanOrEqual(10);
    expect(c.jd[3]).toBe(JD0 + 3 * DT);
    expect(c.t[3]).toBeCloseTo(unixFromJd(JD0 + 3 * DT), 6);
    c.put(pt(10, { bjd_tdb: null, airmass: null, mag: null, saturated: true, suspect: true }));
    expect(Number.isNaN(c.bjd[10])).toBe(true);
    expect(Number.isNaN(c.mag[10])).toBe(true);
    expect(c.flags[10]).toBe(FLAG_SATURATED | FLAG_SUSPECT);
    expect(c.edits).toBe(0); // appends never edit drawn rows
  });

  it('inserts an older frame in place and keeps a frame measured again as a second row (Qt keeps both)', () => {
    const c = new CurveColumns();
    c.put(pt(0));
    c.put(pt(2));
    expect(c.put(pt(1)).how).toBe('inserted');
    expect([...c.view('jd')]).toEqual([pt(0).jd_utc, pt(1).jd_utc, pt(2).jd_utc]);
    expect(c.put(pt(1, { mag: 9 })).how).toBe('inserted');
    expect(c.n).toBe(4);
    expect([...c.view('mag')]).toEqual([11, 11.01, 9, 11.02]); // after the first measurement
    expect(c.edits).toBe(2);
    expect(c.rowsOfJd(pt(1).jd_utc)).toEqual([1, 2]);
    expect(c.indexOfJd(pt(1).jd_utc)).toBe(2); // the newest measurement
    expect(c.indexOfJd(pt(2).jd_utc)).toBe(3);
    expect(c.indexOfJd(pt(5).jd_utc)).toBe(-1);
    expect(c.put(pt(2, { mag: 8 })).how).toBe('appended'); // the newest frame again
    expect(c.rowsOfJd(pt(2).jd_utc)).toEqual([3, 4]);
  });

  it('skips what Qt skips: no finite time, or neither a magnitude nor a flux (S18 keeps ratio-only points)', () => {
    expect(drawable(pt(0))).toBe(true);
    expect(drawable(pt(0, { mag: null }))).toBe(true); // ratio-only
    expect(drawable(pt(0, { mag: null, relative_flux: null }))).toBe(false);
    expect(drawable({ ...pt(0), jd_utc: NaN })).toBe(false);
  });

  it('computes hypot with the bits of CPython math.hypot (V8 Math.hypot is 1 ulp off on these)', () => {
    // Reference values printed by the project's Python (3.11, math.hypot).
    const ref: [number, number, number][] = [
      [0.0506, 0.022382716183191518, 0.05532943144238248],
      [0.0386, 0.007773898562284994, 0.03937503649340146],
      [0.0444, 0.01743126504387897, 0.047699150946635904],
      [0.0786, 0.026236029080385654, 0.08286307514150583],
      [0.0, 0.004, 0.004],
      [3, 4, 5],
    ];
    for (const [a, b, h] of ref) expect(pyHypot(a, b)).toBe(h);
    expect(ref.slice(0, 4).filter(([a, b, h]) => Math.hypot(a, b) !== h).length).toBeGreaterThan(0);
    expect(Number.isNaN(pyHypot(NaN, 1))).toBe(true);
  });

  it('recomputes the error bars from the systematic floor exactly as uncertainty.py (hypot of formal and sigma)', () => {
    const c = new CurveColumns();
    c.put(pt(0, { formal_mag_err: 0.012, mag_err: 0.012 }));
    c.put(pt(1, { formal_mag_err: null, mag_err: 0.02 })); // Qt falls back to mag_err
    c.put(pt(2, { mag: null, formal_mag_err: 0.03, mag_err: 0.03 })); // no magnitude: untouched
    c.put(pt(3, { formal_mag_err: -0.001, mag_err: 0.001 })); // a negative formal error counts as 0
    expect(c.applyFloor(0.005)).toBe(true);
    expect(c.err[0]).toBe(pyHypot(0.012, 0.005));
    expect(c.err[1]).toBe(pyHypot(0.02, 0.005));
    expect(c.err[2]).toBe(0.03);
    expect(c.err[3]).toBe(0.005);
    expect(c.syst[0]).toBe(0.005);
    expect(c.applyFloor(0.005)).toBe(false); // nothing changed
  });
});

describe('trailing statistics', () => {
  it('is a trailing mean ± 1 sigma of the last 15 valid values that never moves the past', () => {
    const ys = Array.from({ length: 40 }, (_, i) => Math.sin(i));
    const b = new TrailingBand(15);
    b.extend(ys, 20);
    const before = Array.from(b.mean.subarray(0, 20));
    b.extend(ys, 40);
    expect(Array.from(b.mean.subarray(0, 20))).toEqual(before);
    const last15 = ys.slice(25, 40);
    const { mean, sd } = meanSd(last15);
    expect(b.mean[39]).toBeCloseTo(mean, 12);
    expect(b.sd[39]).toBeCloseTo(sd, 12);
    expect(b.hi[39]).toBeCloseTo(mean + sd, 12);
    expect(b.count[39]).toBe(15);
  });

  it('claims no spread under 3 values and leaves out excluded (saturated) rows', () => {
    const b = new TrailingBand(15);
    const ys = [1, 3, 100, 5, NaN];
    b.extend(ys, 5, (i) => i === 2);
    expect(b.sd[1]).toBe(0);
    expect(b.mean[2]).toBe(2); // row 2 excluded: the window still holds 1 and 3
    expect(b.mean[3]).toBe(3);
    expect(b.count[4]).toBe(3);
    expect(b.mean[4]).toBe(3); // NaN row: same window
  });

  it('normalises the relative flux by the median of the unsaturated points (S16)', () => {
    const flux = [1, 2, 3, 100];
    expect(fluxBaseline(flux, 4, (i) => i === 3)).toBe(2);
    expect(fluxBaseline([5, 7], 2, () => true)).toBe(6); // all saturated: every point
    expect(Number.isNaN(fluxBaseline([-1, -2], 2, () => false))).toBe(true);
    expect(medianOf([3, NaN, 1, 2], 4)).toBe(2);
  });
});

describe('live curve store (A54-A56)', () => {
  it('reads the catalogue magnitude the ensemble uses: the band, else V (session.py _cat_mag)', () => {
    expect(catalogueMag({ V: 11.2, B: 12 }, 'TG')).toBe(11.2);
    expect(catalogueMag({ V: 11.2, TG: 11.25 }, 'TG')).toBe(11.25);
    expect(catalogueMag({ B: 12 }, 'TG')).toBeNull();
    expect(catalogueMag(null, 'V')).toBeNull();
  });

  it('applies the stream in seq order, reports a gap and ignores what the snapshot already holds', () => {
    const s = new LiveCurveStore();
    s.load({ band: 'TG', revision: 2, seq: 10, curves: [{ key: 'T', role: 'target', points: [pt(0)] }] });
    expect(s.apply(ev('T', 'target', 1, {}, { seq: 10, revision: 2 }))).toBe('stale');
    expect(s.apply(ev('T', 'target', 1, {}, { seq: 11, revision: 2, index: 1 }))).toBe('applied');
    expect(s.apply(ev('T', 'target', 3, {}, { seq: 13, revision: 2 }))).toBe('gap'); // seq 12 missed
    expect(s.apply(ev('T', 'target', 2, {}, { seq: 12, revision: 3 }))).toBe('gap'); // a reset not held
    expect(s.apply(ev('T', 'target', 2, {}, { seq: 12, revision: 2, index: 5 }))).toBe('gap'); // points missed
    expect(s.primary('target')!.n).toBe(2);
    expect(s.apply(ev('T', 'target', 2, { mag: null, relative_flux: null }, { seq: 12, revision: 2 }))).toBe('skipped');
    expect(s.seq).toBe(12);
    expect(s.reset({ reason: 'object_changed', seq: 12, revision: 3 })).toBe('stale');
    // A reset clears everything: the events missed before it (seq 13) do not matter.
    expect(s.reset({ reason: 'object_changed', seq: 14, revision: 3 })).toBe('applied');
    expect(s.seq).toBe(14);
    expect(s.apply(ev('T', 'target', 0, {}, { seq: 15, revision: 3, index: 0 }))).toBe('applied');
    s.reset({ reason: 'cleared', seq: 16, revision: 4 });
    expect(s.stars.size).toBe(0);
    expect(s.revision).toBe(4);
  });

  it('keeps a frame measured twice and goes on with the stream (the plot froze on the second point)', () => {
    const s = new LiveCurveStore();
    s.load({ band: 'TG', revision: 1, seq: 0, curves: [] });
    let seq = 0;
    const send = (i: number, index: number) => s.apply(ev('T', 'target', i, {}, { seq: ++seq, revision: 1, index }));
    expect(send(0, 0)).toBe('applied');
    expect(send(1, 1)).toBe('applied');
    expect(send(1, 2)).toBe('applied'); // Identify field twice on the same opened frame
    expect(send(2, 3)).toBe('applied'); // 'gap' before: every later point refused
    expect(s.primary('target')!.n).toBe(4);
    expect(s.primary('target')!.received).toBe(4);
  });

  it('computes every bar from the floor row by row when frames come out of time order', () => {
    // The newest frame first, then older ones (Open FITS of an earlier file): the server's
    // index order is not the time order. A column in index order put the bars on other points.
    const s = new LiveCurveStore();
    const formal = [0.011, 0.012, 0.013, 0.014, 0.015, 0.016, 0.017, 0.018, 0.019, 0.02, 0.021];
    const sigma = (k: number) => (k >= 9 ? 0.004 + 0.0001 * (k - 9) : null);
    formal.forEach((f, k) => {
      const i = formal.length - 1 - k; // frame i, measured k-th
      const sg = sigma(k);
      s.apply(ev('T', 'target', i, { formal_mag_err: f, mag_err: sg === null ? f : pyHypot(f, sg) }, { index: k, sigma_syst: sg }));
    });
    const c = s.primary('target')!.cols;
    const last = sigma(formal.length - 1)!;
    for (let row = 0; row < c.n; row++) {
      // Row `row` is frame `row`, measured (n − 1 − row)-th with formal[n − 1 − row].
      expect(c.formal[row]).toBe(formal[formal.length - 1 - row]);
      expect(c.err[row]).toBe(pyHypot(formal[formal.length - 1 - row], last));
    }
  });

  it('recomputes the earlier error bars when the curve gets a new sigma_syst (S19), and says rows changed', () => {
    const s = new LiveCurveStore();
    for (let i = 0; i < 9; i++) s.apply(ev('T', 'target', i, { formal_mag_err: 0.01, mag_err: 0.01 }));
    const edits = s.edits;
    s.apply(ev('T', 'target', 9, { formal_mag_err: 0.01, mag_err: Math.hypot(0.01, 0.004) }, { sigma_syst: 0.004 }));
    const c = s.primary('target')!.cols;
    for (let i = 0; i < 10; i++) expect(c.err[i]).toBe(pyHypot(0.01, 0.004));
    expect(s.edits).toBe(edits + 1);
  });

  it('draws the check star as check − catalogue V with its trailing band (D10)', () => {
    const s = new LiveCurveStore();
    s.load({ band: 'TG', curves: [{ key: 'K', role: 'check', catalogue_v: 10.5, points: [] }] });
    for (let i = 0; i < 20; i++) s.apply(ev('K', 'check', i, { mag: 10.52 + (i % 2 ? 0.01 : -0.01) }));
    const d = facetData(s, 'check', 'mag')!;
    expect(d.y[0]).toBeCloseTo(0.01, 12);
    expect(d.y[1]).toBeCloseTo(0.03, 12);
    expect(d.band!.mean[19]).toBeCloseTo(0.02 + (0.01 * 1) / 15, 12); // 8 high + 7 low in the last 15
    const sig = checkSigma(s)!;
    expect(sig.count).toBe(15);
    expect(sig.sigma).toBeGreaterThan(0.009);
    // A curve without catalogue magnitude takes the target set's (A51), matched by key.
    const t = new LiveCurveStore();
    t.apply(ev('K', 'check', 0, { mag: 10.52 }, { star_key: 'k1' }));
    expect(t.primary('check')!.catalogue).toBeNull();
    t.applyTargets([{ key: 'k1', role: 'check', mags: { V: 10.6, B: 11 } }], 'TG');
    expect(facetData(t, 'check', 'mag')!.y[0]).toBeCloseTo(-0.08, 12);
    // A reload of curves the stream created (no catalogue magnitudes yet) keeps the set's offset.
    t.load({ band: 'TG', curves: [{ key: 'K', star_key: 'k1', role: 'check', mags: {}, catalogue_v: null, points: [pt(0, { mag: 10.52 })] }] });
    expect(t.primary('check')!.catalogue).toBe(10.6);
    expect(facetData(t, 'check', 'mag')!.y[0]).toBeCloseTo(-0.08, 12);
  });

  it("draws the ensemble facet as the target's zero point ± its rms (the night's transparency)", () => {
    const s = new LiveCurveStore();
    expect(facetData(s, 'ensemble', 'mag')).toBeNull();
    s.apply(ev('T', 'target', 0, { zero_point: 19.4, zp_rms: 0.02 }));
    s.apply(ev('T', 'target', 1, { zero_point: 19.3, zp_rms: null }));
    s.apply(ev('T', 'target', 2, { zero_point: 19.5, zp_rms: 0.01 }));
    const d = facetData(s, 'ensemble', 'mag')!;
    expect(Array.from(d.y)).toEqual([19.4, 19.3, 19.5]);
    expect(d.band!.hi[0]).toBeCloseTo(19.42, 12);
    expect(Number.isNaN(d.band!.hi[1])).toBe(true);
    expect(yExtent(d, -Infinity, Infinity)).toEqual([19.3, 19.51]);
    // Relative flux: the transmission against the run's median zero point (19.4).
    const f = facetData(s, 'ensemble', 'flux')!;
    expect(f.y[0]).toBeCloseTo(1, 12);
    expect(f.y[2]).toBeCloseTo(10 ** 0.04, 12);
    // A target without zero points (ratio only) has no ensemble facet.
    const r = new LiveCurveStore();
    r.apply(ev('T', 'target', 0, { mag: null }));
    expect(facetData(r, 'ensemble', 'mag')).toBeNull();
  });

  it('scales the check facet on a symmetric rung that holds the band and 90 % of the points', () => {
    const d = { n: 10, x: Float64Array.from({ length: 10 }, (_, i) => i), y: Float64Array.from([0.01, -0.02, 0.03, 0.01, 0, -0.01, 0.02, 0.6, 0.01, -0.02]), err: null, flags: null, band: null };
    expect(checkRung(d, -Infinity, Infinity)).toBe(0.05); // one outlier of ten: a caret
    d.y[3] = 0.15;
    expect(checkRung(d, -Infinity, Infinity)).toBe(0.2);
    expect(checkRung(d, 0, 2)).toBe(0.05); // the visible rows only
  });

  it('gives a facet three labelled ticks from 26 px of data, never fewer than two, on a 1-2-5 step', () => {
    for (const [lo, hi, px] of [
      [11.9, 12.05, 27],
      [-0.05, 0.05, 13],
      [9.4, 10.2, 120],
      [19.35, 19.47, 40],
      [12.0, 12.3, 18],
    ] as const) {
      const { splits, step } = niceSplits(lo, hi, px);
      expect(splits.length).toBeGreaterThanOrEqual(px >= 26 ? 3 : 2);
      if (splits.length > 1) expect(((splits[1] - splits[0]) / (hi - lo)) * px).toBeGreaterThanOrEqual(px >= 26 ? 8 : 6);
      expect([1, 2, 5]).toContain(Math.round(step / 10 ** Math.floor(Math.log10(step) + 1e-9)));
      for (const v of splits) expect(v >= lo - 1e-9 && v <= hi + 1e-9).toBe(true);
    }
    expect(niceSplits(0, 1, 200).splits.length).toBeLessThanOrEqual(Math.floor(200 / 13) + 1);
  });

  it('pads the y range in pixels so a marker and its ring stay inside the plot', () => {
    const [lo, hi] = padPixels(0, 1, 50, 5);
    expect(((0 - lo) / (hi - lo)) * 50).toBeCloseTo(5, 9);
    expect(((hi - 1) / (hi - lo)) * 50).toBeCloseTo(5, 9);
  });

  it('builds the relative-flux view from the unsaturated baseline, ratio-only points included', () => {
    const s = new LiveCurveStore();
    s.apply(ev('T', 'target', 0, { relative_flux: 2, relative_flux_err: 0.02, mag: null }));
    s.apply(ev('T', 'target', 1, { relative_flux: 4, relative_flux_err: 0.04 }));
    s.apply(ev('T', 'target', 2, { relative_flux: 400, saturated: true }));
    const d = facetData(s, 'target', 'flux')!;
    expect(Array.from(d.y)).toEqual([2 / 3, 4 / 3, 400 / 3]);
    expect(d.err![1]).toBeCloseTo(0.04 / 3, 15);
    expect(Number.isNaN(facetData(s, 'target', 'mag')!.y[0])).toBe(true);
    expect(flagCounts(d.flags, d.y)).toEqual({ suspect: 0, saturated: 1 });
  });

  it('finds the visible rows by time', () => {
    const x = [1, 2, 3, 4, 5];
    expect(visibleRange(x, 5, 2, 4)).toEqual([1, 3]);
    expect(visibleRange(x, 5, 6, 9)).toEqual([5, 4]);
  });
});

describe('readout and TSV', () => {
  function run(): LiveCurveStore {
    const s = new LiveCurveStore();
    s.load({
      band: 'TG',
      curves: [
        { key: 'T', role: 'target', points: [], sigma_syst: null },
        { key: 'K', role: 'check', catalogue_v: 10.5, points: [] },
        { key: 'C1', role: 'comparison', mags: { V: 10 }, points: [] },
        { key: 'C2', role: 'comparison', mags: { V: 11 }, points: [] },
      ],
    });
    for (let i = 0; i < 3; i++) {
      s.apply(ev('T', 'target', i, { comps_used: 2, zero_point: 19.4 + 0.01 * i, zp_rms: 0.014, ...(i === 1 ? { suspect: true } : {}) }));
      // The check's own BJD: 6.4 s after the target's (another direction on the sky).
      s.apply(ev('K', 'check', i, { mag: 10.512, bjd_tdb: JD0 + i * DT + 0.0023 + 6.4 / 86400 }));
      s.apply(ev('C1', 'comparison', i, { mag: 10.01 }));
      s.apply(ev('C2', 'comparison', i, { mag: 10.99 }));
    }
    return s;
  }

  it('reads every series at one time, with UTC, JD and BJD', () => {
    const s = run();
    const r = readoutAt(s, unixFromJd(pt(1).jd_utc) + 0.4, 'mag')!;
    expect(r.point).toBe(2);
    expect(r.jd).toBe((JD0 + DT).toFixed(5));
    expect(r.bjd).toBe((JD0 + DT + 0.0023).toFixed(5));
    expect(r.checkBjd).toBe((JD0 + DT + 0.0023 + 6.4 / 86400).toFixed(5));
    expect(r.target!.value).toBe('11.010 ± 0.010');
    expect(r.target!.flags).toEqual(['suspect (hot pixel?)']);
    expect(r.check!.value).toBe('+0.012 ± 0.010');
    expect(r.check!.what).toBe('check − V 10.500');
    expect(r.ensemble!.value).toBe('ZP 19.410 · σ 0.014');
    expect(r.ensemble!.what).toBe('2 of 2 comparisons');
    expect(r.airmass).toBe('1.200');
    expect(readoutAt(s, unixFromJd(pt(1).jd_utc) + 10, 'mag', {}, 1)).toBeNull();
  });

  it('copies a frame measured twice as two rows, target beside check', () => {
    const s = run();
    s.apply(ev('T', 'target', 1, { mag: 11.5 }));
    s.apply(ev('K', 'check', 1, { mag: 10.6 }));
    const { text, rows } = curveTsv(s);
    expect(rows).toBe(4);
    const cells = text.trim().split('\n').slice(1).map((l) => l.split('\t'));
    const m = TSV_HEADER.indexOf('target_mag');
    const k = TSV_HEADER.indexOf('check_mag');
    expect(cells.map((c) => c[m])).toEqual(['11', '11.01', '11.5', '11.02']);
    expect(cells.map((c) => c[k])).toEqual(['10.512', '10.512', '10.6', '10.512']);
  });

  it('copies one row per frame with full precision', () => {
    const s = run();
    const { text, rows } = curveTsv(s);
    const lines = text.trim().split('\n');
    expect(rows).toBe(3);
    expect(lines[0].split('\t')).toEqual([...TSV_HEADER]);
    const cells = lines[2].split('\t');
    const col = (name: (typeof TSV_HEADER)[number]) => cells[TSV_HEADER.indexOf(name)];
    expect(col('jd_utc')).toBe(String(JD0 + DT));
    expect(col('target_mag')).toBe(String(11 + 0.01));
    expect(col('target_flags')).toBe('suspect');
    expect(Number(col('check_minus_catalogue'))).toBeCloseTo(0.012, 12);
    expect(col('zero_point')).toBe(String(19.4 + 0.01));
    expect(col('zp_rms')).toBe('0.014');
    expect(col('utc')).toBe(isoMs(unixFromJd(JD0 + DT)));
    expect(col('bjd_tdb')).toBe(String(JD0 + DT + 0.0023));
    expect(col('check_bjd_tdb')).toBe(String(JD0 + DT + 0.0023 + 6.4 / 86400));
  });
});
