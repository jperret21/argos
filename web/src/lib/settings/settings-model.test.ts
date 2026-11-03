import { describe, expect, it } from 'vitest';
import type { KeyMeta, SiteCheck } from '../api/types';
import {
  CATEGORIES,
  homeCategory,
  isSettingsCategory,
  keyFacts,
  keysOf,
  settingsAttention,
  siteCheckView,
} from './categories';
import {
  currentSite,
  favoritesOf,
  isDefaultFavorite,
  removeFavorite,
  siteChanges,
  siteFromPlace,
  upsertFavorite,
} from './sites';

const meta = (over: Partial<KeyMeta> = {}): KeyMeta => ({
  type: 'float',
  default: 0,
  nullable: false,
  min: null,
  max: null,
  step: null,
  options: null,
  unit: null,
  label: 'X',
  help: '',
  used_by: ['x'],
  category: 'observer_site',
  advanced: false,
  read_only: false,
  ...over,
});

/** The 2026-09-25 incident: Settings site Berkeley, telescope in France (protocol.md "Site check"). */
const BERKELEY: SiteCheck = {
  state: 'mismatch',
  reason: null,
  message: 'Site check: the mount points at altitude 75.4°…',
  tolerance_deg: 5,
  checked_utc: '2026-09-25T20:05:00.000Z',
  trigger: 'connect',
  site: { name: 'Berkeley', latitude: 37.871, longitude: -122.273 },
  mount: { ra_hours: 19.4244, dec_deg: 42.784, alt_deg: 75.4, az_deg: 258.9 },
  expected: { alt_deg: 13.8, az_deg: 45.9 },
  separation_deg: 88.5,
  altitude_diff_deg: 61.6,
  driver_site: null,
};

describe('Settings categories', () => {
  it('has the nine canonical categories of D13, in order', () => {
    expect(CATEGORIES.map((c) => c.label)).toEqual([
      'Observer & site',
      'Instrument',
      'Plate solving',
      'Catalogues',
      'Photometry',
      'Data & storage',
      'Privacy & diagnostics',
      'Appearance',
      'About',
    ]);
    expect(isSettingsCategory('about')).toBe(true);
    expect(isSettingsCategory('connection')).toBe(false);
  });

  it('gives every server key one home: Connection keys none, Observe display in Appearance, the bridge host in Privacy', () => {
    expect(homeCategory('alpaca.host', meta({ category: 'connection' }))).toBeNull();
    expect(homeCategory('stellarium.host', meta({ category: 'connection' }))).toBe('privacy_diagnostics');
    expect(homeCategory('stellarium.online_target_lookup', meta({ category: 'connection' }))).toBe('privacy_diagnostics');
    expect(homeCategory('imaging.star_radius_px', meta({ category: 'observe' }))).toBe('appearance');
    expect(homeCategory('site.latitude', meta())).toBe('observer_site');
    const m = { a: meta({ category: 'photometry' }), b: meta({ category: 'catalogues' }), c: meta({ category: 'photometry' }) };
    expect(keysOf(m, 'photometry')).toEqual(['a', 'c']);
  });
});

describe('site check view', () => {
  it('shows both altitudes, the difference against the limit and when', () => {
    const v = siteCheckView(BERKELEY);
    expect(v.tone).toBe('mismatch');
    expect(v.word).toBe('Disagrees with the mount');
    expect(v.rows.map((r) => `${r.label}: ${r.value}`)).toEqual([
      // Alt / Az with 2 decimals everywhere (BRAND 5, as the Mount card).
      'Mount reports: alt 75.40°, az 258.90°',
      'From the Settings site: alt 13.80°, az 45.90°',
      'Difference: 88.5° apart (altitude +61.6°) · limit 5°',
    ]);
    expect(v.when).toBe('20:05:00 UTC · on connection');
  });

  it('names the driver site and its distance', () => {
    const v = siteCheckView({ ...BERKELEY, driver_site: { latitude: 48.8277, longitude: 2.3826, elevation_m: 60, distance_km: 8941.2, state: 'mismatch' } });
    // U+202F groups the thousands (BRAND 5).
    // Site coordinates with 5 decimals, as the Settings fields.
    expect(v.driver).toBe("The mount's own site: +48.82770° +2.38260°, 8\u202f941 km from the Settings site (more than 100 km).");
  });

  it('says nothing was compared before a report', () => {
    expect(siteCheckView(null)).toMatchObject({ tone: 'unknown', rows: [], when: '' });
  });
});

describe('Settings attention (Q-G11, wave 2)', () => {
  const good = { 'observer.obscode': 'PJUA', 'site.latitude': 48.8277, 'site.longitude': 2.3826 };
  it('is empty when the code and the site are set and the check agrees', () => {
    expect(settingsAttention(good, { ...BERKELEY, state: 'ok' })).toEqual([]);
  });
  it('flags a missing code, a missing site, and a site that disagrees with the mount', () => {
    expect(settingsAttention({ ...good, 'observer.obscode': '' }, null).map((a) => a.text)).toEqual([
      'No AAVSO observer code: AAVSO exports cannot be stamped',
    ]);
    expect(settingsAttention({ ...good, 'site.latitude': 0, 'site.longitude': 0 }, null)[0].text).toMatch(/No observing site/);
    expect(settingsAttention(good, BERKELEY)).toEqual([
      { category: 'observer_site', text: 'The Settings site disagrees with the mount', level: 'attention' },
    ]);
    // One shape per level (BRAND 8): a missing code is info (ring), a missing or wrong site attention.
    expect(settingsAttention({ ...good, 'observer.obscode': '' }, null)[0].level).toBe('info');
    expect(settingsAttention({ ...good, 'site.latitude': 0, 'site.longitude': 0 }, null)[0].level).toBe('attention');
  });
  it('waits for the configuration', () => {
    expect(settingsAttention(null, BERKELEY)).toEqual([]);
  });
});

describe('About this setting (Q-C8)', () => {
  it('lists the key, default, value and range', () => {
    const f = keyFacts('site.latitude', meta({ min: -90, max: 90, step: 0.00001, unit: '°', label: 'Latitude', used_by: ['FITS SITELAT'] }), 48.8277);
    expect(f.key).toBe('site.latitude');
    expect(f.facts).toEqual([
      { label: 'Default', value: '+0.00000°', mono: true },
      { label: 'Now', value: '+48.82770°', mono: true },
      // One range notation (format/number.ts formatRange): natural precision, signed, ° on both.
      { label: 'Range', value: '−90° … +90°', mono: true },
    ]);
    expect(f.usedBy).toEqual(['FITS SITELAT']);
  });

  it('says a personal key has no default to go back to', () => {
    const f = keyFacts('site.latitude', { ...meta({ min: -90, max: 90, step: 0.00001, unit: '°', label: 'Latitude' }), personal: true } as never, 48.8277);
    expect(f.facts[0]).toEqual({ label: 'Default', value: 'None: your own value' });
  });

  it('groups a range from 1 000 up and keeps the unit once', () => {
    const f = keyFacts('astrometry.live_resolve_s', meta({ type: 'float', min: 1, max: 3600, step: 1, unit: 's', label: 'Re-solve' }), 20);
    expect(f.facts.find((x) => x.label === 'Range')?.value).toBe('1 … 3\u202f600 s');
  });
});

describe('sites', () => {
  const values = { 'site.name': 'Home', 'site.latitude': 48.8277, 'site.longitude': 2.3826, 'site.elevation': 60 };

  it('names a found place by its first label part and keeps the elevation when none came back (Qt :915-919)', () => {
    const s = siteFromPlace({ label: "Saint-Michel-l'Observatoire, Forcalquier, France", latitude: 43.9097123, longitude: 5.7168999, elevation_m: null }, currentSite(values));
    expect(s).toEqual({ name: "Saint-Michel-l'Observatoire", latitude: 43.90971, longitude: 5.7169, elevation: 60 });
  });

  it('writes the four site keys in one commit', () => {
    expect(siteChanges(currentSite(values))).toEqual(values);
  });

  it('replaces a saved site of the same name, any case (Qt :954-972), and removes by name', () => {
    const list = favoritesOf([{ name: 'Home', latitude: 1, longitude: 2, elevation: 3 }, { name: '', latitude: 0, longitude: 0, elevation: 0 }, 'x']);
    expect(list).toHaveLength(1);
    const r = upsertFavorite(list, { name: 'home', latitude: 48.8277, longitude: 2.3826, elevation: 60 });
    expect(r.replaced).toBe(true);
    expect(r.list).toEqual([{ name: 'home', latitude: 48.8277, longitude: 2.3826, elevation: 60 }]);
    expect(removeFavorite(r.list, 'HOME')).toEqual([]);
  });

  it('marks the saved site that is the default', () => {
    expect(isDefaultFavorite({ name: 'Home', latitude: 48.8277, longitude: 2.3826, elevation: 60 }, currentSite(values))).toBe(true);
    expect(isDefaultFavorite({ name: 'Home', latitude: 48.9, longitude: 2.3826, elevation: 60 }, currentSite(values))).toBe(false);
  });
});
