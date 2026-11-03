import { describe, expect, it, vi } from 'vitest';
import type { KeyMeta } from '../api/types';
import { GROUP, MINUS } from '../format/number';
import {
  commitKey,
  decimalsFor,
  dependencyReason,
  fieldKind,
  formatValue,
  groupFor,
  isDefault,
  matchesQuery,
  pathMode,
  refusalFor,
  sameValue,
  segmentable,
  selectKeys,
} from './settings';

function meta(over: Partial<KeyMeta>): KeyMeta {
  return {
    type: 'str',
    default: '',
    nullable: false,
    min: null,
    max: null,
    step: null,
    options: null,
    unit: null,
    label: 'Label',
    help: '',
    used_by: [],
    category: 'observer_site',
    advanced: false,
    read_only: false,
    ...over,
  };
}

// The shapes below are copied from argos/server/config_meta.py (KEYS).
const LAT = meta({ type: 'float', default: 0, min: -90, max: 90, step: 0.00001, unit: '°', label: 'Latitude' });
const RADIUS = meta({ type: 'int', default: 30, min: 0, max: 180, step: 1, unit: '°', label: 'Search radius', category: 'plate_solving' });
const DOWNSAMPLE = meta({
  type: 'int',
  default: 2,
  options: [
    { value: 0, label: 'Auto' },
    { value: 1, label: '1×' },
    { value: 2, label: '2×' },
    { value: 3, label: '3×' },
    { value: 4, label: '4×' },
  ],
  category: 'plate_solving',
});
const BUDGET = meta({
  type: 'int',
  default: 400,
  options: [
    { value: 100, label: 'Fast · 100 objects' },
    { value: 200, label: 'Fast · 200 objects' },
    { value: 400, label: 'Balanced · 400 objects' },
    { value: 800, label: 'Detailed · 800 objects' },
    { value: 1600, label: 'Dense field · 1,600 objects' },
  ],
  category: 'catalogues',
});
const FULL_WELL = meta({ type: 'int', default: null, nullable: true, min: 0, max: 65535, step: 1, unit: 'ADU', category: 'instrument' });

describe('fieldKind: the control a key gets', () => {
  it('maps types and options to token-drawn controls', () => {
    expect(fieldKind(meta({ type: 'bool', default: true }))).toBe('switch');
    expect(fieldKind(LAT)).toBe('number');
    expect(fieldKind(DOWNSAMPLE)).toBe('segmented');
    expect(fieldKind(BUDGET)).toBe('select'); // five long labels do not fit side by side
    expect(fieldKind(meta({ type: 'path' }))).toBe('path');
    expect(fieldKind(meta({ type: 'host' }))).toBe('text');
    expect(fieldKind(meta({ type: 'list', default: [] }))).toBe('list');
    expect(fieldKind(meta({ type: 'object', default: {} }))).toBe('object');
  });

  it('keeps segmented controls short', () => {
    expect(segmentable([{ label: 'DEBUG' }, { label: 'INFO' }, { label: 'WARNING' }, { label: 'ERROR' }])).toBe(true);
    expect(segmentable([{ label: 'only' }])).toBe(false);
  });
});

describe('values in words', () => {
  it('uses the BRAND formats (signed coordinates, U+2212, grouped ADU)', () => {
    // ° against the number (BRAND 5: "41.27°").
    expect(formatValue(48.85, LAT, 'site.latitude')).toBe('+48.85000°');
    expect(formatValue(-2.35, LAT, 'site.longitude')).toBe(`${MINUS}2.35000°`);
    // Decimals grouped from 1 000 up too (D5): elevation 2 877.0 m.
    expect(formatValue(2877, meta({ type: 'float', step: 0.1, unit: 'm' }), 'site.elevation')).toBe(`2${GROUP}877.0 m`);
    expect(formatValue(60000, meta({ type: 'int', unit: 'ADU' }), 'camera.full_well_adu')).toBe(`60${GROUP}000 ADU`);
    expect(formatValue(32323, meta({ type: 'int' }), 'alpaca.port')).toBe('32323'); // an identifier
    expect(formatValue(null, FULL_WELL)).toBe('not set');
    expect(formatValue(2, DOWNSAMPLE)).toBe('2×');
    expect(formatValue(true, meta({ type: 'bool' }))).toBe('On');
    expect(formatValue([{}, {}], meta({ type: 'list' }))).toBe('2 items');
    expect(formatValue({}, meta({ type: 'object' }))).toBe('empty');
  });

  it('decimals from the step, grouping for quantities only', () => {
    expect(decimalsFor(LAT)).toBe(5);
    expect(decimalsFor(RADIUS)).toBe(0);
    expect(groupFor('camera.full_well_adu', meta({ type: 'int' }))).toBe(true);
    expect(groupFor('stellarium.port', meta({ type: 'int' }))).toBe(false);
  });
});

describe('changed from default', () => {
  it('compares deeply (lists of saved sites)', () => {
    expect(isDefault(30, RADIUS)).toBe(true);
    expect(isDefault(45, RADIUS)).toBe(false);
    expect(isDefault(null, FULL_WELL)).toBe(true);
    const sites = [{ name: 'Home', latitude: 48.8, longitude: 2.3, elevation: 35 }];
    expect(sameValue(sites, [{ elevation: 35, longitude: 2.3, latitude: 48.8, name: 'Home' }])).toBe(true);
    expect(sameValue(sites, [])).toBe(false);
    expect(sameValue({ a: 1 }, [1] as never)).toBe(false);
  });
});

describe('which keys a form shows', () => {
  const all: Record<string, KeyMeta> = {
    'site.latitude': LAT,
    'astrometry.search_radius_deg': RADIUS,
    'astrometry.downsample': DOWNSAMPLE,
    'astrometry.live_timeout_s': meta({ type: 'float', category: 'plate_solving', advanced: true, label: 'Automatic solve timeout' }),
  };

  it('keeps the server order, splits the advanced keys, filters by words', () => {
    expect(selectKeys(all, { category: 'plate_solving', advanced: false })).toEqual([
      'astrometry.search_radius_deg',
      'astrometry.downsample',
    ]);
    expect(selectKeys(all, { category: 'plate_solving', advanced: true })).toEqual(['astrometry.live_timeout_s']);
    expect(selectKeys(all, { query: 'search radius' })).toEqual(['astrometry.search_radius_deg']);
    expect(selectKeys(all, { keys: ['astrometry.downsample', 'nope', 'site.latitude'] })).toEqual([
      'astrometry.downsample',
      'site.latitude',
    ]);
    expect(matchesQuery('site.latitude', LAT, 'LATI')).toBe(true);
  });
});

describe('dependent keys and pickers', () => {
  it('is unavailable with the reason while the parent is off', () => {
    expect(dependencyReason('catalog.field_stars_mag_limit', { 'catalog.field_stars_enabled': false })).toMatch(/Gaia/);
    expect(dependencyReason('catalog.field_stars_mag_limit', { 'catalog.field_stars_enabled': true })).toBeNull();
    expect(dependencyReason('astrometry.database', { 'astrometry.database_path': '/data/d50' })).toMatch(/Ignored/);
    expect(dependencyReason('astrometry.database', { 'astrometry.database_path': '' })).toBeNull();
  });

  it('picks folders, files or the ASTAP program', () => {
    expect(pathMode('sessions_path', meta({ type: 'path' }))).toBe('open-folder');
    expect(pathMode('astrometry.astap_path', meta({ type: 'path' }))).toBe('executable');
    expect(pathMode('data_paths.exoplanet_cache', meta({ type: 'path', help: 'NASA ephemerides (file).' }))).toBe('open-file');
    expect(pathMode('x', { ...meta({ type: 'path' }), path_kind: 'file' } as KeyMeta)).toBe('open-file');
  });
});

describe('one PATCH per commit', () => {
  it('sends one key and returns its own warnings', async () => {
    const patch = vi.fn(async () => ({
      warnings: [
        { key: 'sessions_path', message: 'does not exist, it will be created' },
        { key: 'other', message: 'not mine' },
      ],
    }));
    const r = await commitKey(patch, 'sessions_path', '/data/new');
    expect(patch).toHaveBeenCalledWith({ sessions_path: '/data/new' });
    expect(r.warnings).toEqual(['does not exist, it will be created']);
  });

  it("refuses with that key's words from `fields`", async () => {
    const err = Object.assign(new Error('Invalid configuration'), { fields: { 'site.latitude': 'must be at most 90' } });
    await expect(commitKey(() => Promise.reject(err), 'site.latitude', 120)).rejects.toThrow('must be at most 90');
    expect(refusalFor(err, 'other')).toBe('Invalid configuration');
  });
});
