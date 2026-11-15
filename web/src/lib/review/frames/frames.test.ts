import { describe, expect, it } from 'vitest';
import { applySort, toTsv } from '../../components/table';
import {
  countsText,
  filterRows,
  FRAME_COLUMNS,
  frameAt,
  frameCounts,
  frameRows,
  isoSeconds,
  openableLights,
  openReason,
  parseFrame,
  statusGlyph,
  utcText,
  visibleColumns,
} from './frames';

const F = (n: number, extra: Record<string, unknown> = {}) => ({
  filename: `RR_Lyr_ir_light_e010000ms_g080_${String(n).padStart(5, '0')}.fit`,
  image_type: 'Light',
  filter_name: 'IR',
  exposure_s: 10,
  gain: 80,
  timestamp: `2026-09-25T20:${String(5 + n).padStart(2, '0')}:00`,
  hfd: 6.8123,
  fwhm: 2.214,
  star_count: 4281,
  sky_adu: 1364.4,
  peak_adu: 65535,
  eccentricity: 0.513,
  ccd_temp: -1.25,
  path: `/s/lights/RR_Lyr_${n}.fit`,
  ...extra,
});

describe('frames model', () => {
  it('parses an A68 frame, tolerating missing numbers', () => {
    expect(parseFrame({ filename: 'a.fit' })).toMatchObject({ filename: 'a.fit', exposure_s: null, path: null, image_type: '' });
    expect(parseFrame({ image_type: 'Light' })).toBeNull();
    expect(parseFrame(null)).toBeNull();
    expect(parseFrame({ filename: 'a.fit', gain: Number.NaN })!.gain).toBeNull();
    const h = parseFrame({ filename: 'a.fit', index: 3, filter: 'ir', header: { airmass: 1.234, bayer: 'GRBG', mid_utc: '2026-09-25T20:05:01Z' } })!;
    expect(h.index).toBe(3);
    expect(h.filter).toBe('ir');
    expect(h.header).toMatchObject({ airmass: 1.234, bayer: 'GRBG', jd_mid: null });
    expect(parseFrame({ filename: 'a.fit', index: -1 }, 9)!.index).toBe(9);
  });

  it('reads DATE-OBS without a zone as UTC', () => {
    expect(isoSeconds('2026-09-25T20:04:53')).toBe(Date.UTC(2026, 8, 25, 20, 4, 53) / 1000);
    expect(isoSeconds('2026-09-25T20:04:53+00:00')).toBe(Date.UTC(2026, 8, 25, 20, 4, 53) / 1000);
    expect(isoSeconds('2026-09-25T20:04:53.500Z')).toBe(Date.UTC(2026, 8, 25, 20, 4, 53, 500) / 1000);
    expect(isoSeconds('nonsense')).toBeNull();
    expect(isoSeconds(null)).toBeNull();
  });

  it('keys rows uniquely, flags missing files and lights', () => {
    const rows = frameRows([F(1), F(2, { path: null }), F(1), { filename: 'dark_001.fit', image_type: 'Dark', path: '/d' }, 'junk']);
    // No server index: the position; a repeated index never gives a repeated key.
    expect(rows.map((r) => r.key)).toEqual(['f0', 'f1', 'f2', 'f3']);
    const indexed = frameRows([F(1, { index: 4 }), F(2, { index: 4 }), F(3, { index: 7 })]);
    expect(indexed.map((r) => r.key)).toEqual(['f4', 'f7', 'f10']);
    expect(indexed[0].index).toBe(4);
    expect(rows.map((r) => r.missing)).toEqual([false, true, false, false]);
    expect(rows.map((r) => r.light)).toEqual([true, true, true, false]);
    expect(frameCounts(rows)).toEqual({ total: 4, lights: 3, missing: 1 });
    expect(countsText(frameCounts(rows))).toBe('3 lights · 1 other · 1 missing');
    expect(countsText({ total: 1195, lights: 1195, missing: 0 })).toBe('1\u202f195 lights · 0 missing');
    expect(countsText({ total: 1, lights: 1, missing: 0 })).toBe('1 light · 0 missing');
    // The server's `light` (core light_frames) wins over the type text when sent.
    const typed = frameRows([F(1, { image_type: 'Light Frame', light: false }), { filename: 'x.fit', image_type: 'Science', light: true, path: '/x' }]);
    expect(typed.map((r) => r.light)).toEqual([false, true]);
  });

  it('formats every column with fixed decimals, true minus and grouped digits', () => {
    const [r] = frameRows([F(1)]);
    const text = Object.fromEntries(FRAME_COLUMNS.map((c) => [c.id, c.format ? c.format(r) : '']));
    expect(text).toMatchObject({
      utc: '2026-09-25 20:06:00',
      exposure: '10.0',
      gain: '80',
      fwhm: '2.21',
      hfd: '6.81',
      stars: '4\u202f281',
      sky: '1\u202f364',
      peak: '65\u202f535',
      ecc: '0.51',
      temp: '−1.3',
      airmass: '—',
      file: r.filename,
    });
    const [h] = frameRows([F(1, { header: { airmass: 1.08349 } })]);
    expect(FRAME_COLUMNS.find((c) => c.id === 'airmass')!.format!(h)).toBe('1.083');
    const [m] = frameRows([F(2, { path: null, fwhm: null })]);
    expect(FRAME_COLUMNS.find((c) => c.id === 'fwhm')!.format!(m)).toBe('—');
    expect(FRAME_COLUMNS.find((c) => c.id === 'file')!.format!(m)).toBe(`${m.filename} (missing)`);
    expect(utcText(null)).toBe('—');
  });

  it('hides columns but never UTC or File', () => {
    const ids = visibleColumns(new Set(['peak', 'utc', 'file', 'gain'])).map((c) => c.id);
    expect(ids).not.toContain('peak');
    expect(ids).not.toContain('gain');
    // The target's status glyph leads (design review), then the row's identity.
    expect(ids.slice(0, 2)).toEqual(['status', 'utc']);
    expect(ids[ids.length - 1]).toBe('file');
  });

  it('filters on file, type, filter and "missing", every word matching', () => {
    const rows = frameRows([F(1), F(2, { path: null }), { filename: 'flat_01.fit', image_type: 'Flat', filter_name: 'LP', path: '/f' }]);
    expect(filterRows(rows, '').length).toBe(3);
    expect(filterRows(rows, 'flat').map((r) => r.filename)).toEqual(['flat_01.fit']);
    expect(filterRows(rows, 'light ir').length).toBe(2);
    expect(filterRows(rows, 'missing').map((r) => r.index)).toEqual([1]);
    expect(filterRows(rows, 'LP light').length).toBe(0);
  });

  it('marks the target’s flagged frames (⚑), sorts them up and filters them ("flagged")', () => {
    const rows = frameRows([F(1), F(2), F(3)]).map((r, i) => ({ ...r, flags: [[], ['low_snr', 'zp_outlier'], ['few_anchors']][i], comps: [6, 2, 5][i] }));
    expect(rows.map(statusGlyph)).toEqual(['', '▮', '▯']);
    expect(filterRows(rows, 'flagged').map((r) => r.index)).toEqual([rows[1].index, rows[2].index]);
    const cols = visibleColumns(new Set());
    expect(applySort(rows, cols, { column: 'status', dir: 'desc' }).map(statusGlyph)).toEqual(['▮', '▯', '']);
    expect(cols.find((c) => c.id === 'comps')!.format!(rows[1])).toBe('2');
  });

  it('sorts numbers numerically with missing values last, and copies what is shown', () => {
    const rows = frameRows([F(1, { fwhm: 3.1 }), F(2, { fwhm: null }), F(3, { fwhm: 2.0 })]);
    const cols = visibleColumns(new Set(['peak']));
    expect(applySort(rows, cols, { column: 'fwhm', dir: 'asc' }).map((r) => r.fwhm)).toEqual([2.0, 3.1, null]);
    expect(applySort(rows, cols, { column: 'fwhm', dir: 'desc' }).map((r) => r.fwhm)).toEqual([3.1, 2.0, null]);
    const tsv = toTsv(cols, rows.slice(0, 1)).split('\n');
    expect(tsv[0]).toBe('⚑\tUTC\tType\tFilter\tExp (s)\tGain\tFWHM\tHFD\tStars\tSky (ADU)\tEcc\tAirmass\tTemp (°C)\tComps\tFile');
    expect(tsv[1].split('\t')[6]).toBe('3.10'); // FWHM, after the ⚑ column
  });

  it('finds the frame a mid-exposure time falls on', () => {
    const rows = frameRows([F(1), F(2), F(3, { timestamp: null })]);
    const t1 = rows[0].t!;
    expect(frameAt(rows, t1 + 5)?.key).toBe(rows[0].key);
    expect(frameAt(rows, t1 + 10)?.key).toBe(rows[0].key);
    // Between exposures (60 s apart): the nearest middle within the exposure length.
    expect(frameAt(rows, t1 + 58)?.key).toBe(rows[1].key);
    expect(frameAt(rows, t1 + 15)?.key).toBe(rows[0].key);
    expect(frameAt(rows, t1 + 35)).toBeNull();
    expect(frameAt(rows, t1 - 1000)).toBeNull();
    expect(frameAt(rows, t1 + 15, 1)).toBeNull();
  });

  it('steps through openable lights in time order and says why a missing frame cannot open', () => {
    const rows = frameRows([F(3), F(1), F(2, { path: null }), { filename: 'd.fit', image_type: 'Dark', path: '/d', timestamp: '2026-09-25T19:00:00' }]);
    expect(openableLights(rows).map((r) => r.filename)).toEqual([F(1).filename, F(3).filename]);
    expect(openReason(rows[2])).toBe(`File not found: ${F(2).filename}`);
    expect(openReason(rows[0])).toBeNull();
  });
});
