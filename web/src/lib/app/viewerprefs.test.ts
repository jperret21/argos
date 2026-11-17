import { describe, expect, it } from 'vitest';
import { loadDensity, rotationFromQt, saveDensity, SEEDED_KEY, seedFromQt, themeFromQt } from './viewerprefs';

function store(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    map: m,
  };
}

describe('density (owner D7)', () => {
  it('defaults to Compact and keeps the choice raw (index.html reads it before paint)', () => {
    const s = store();
    expect(loadDensity(s)).toBe('compact');
    saveDensity('comfortable', s);
    expect(s.map.get('argos.density')).toBe('comfortable');
    expect(loadDensity(s)).toBe('comfortable');
    expect(loadDensity(store({ 'argos.density': 'huge' }))).toBe('compact');
  });

  it('survives a storage that throws', () => {
    const bad = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    };
    expect(loadDensity(bad)).toBe('compact');
    expect(() => saveDensity('comfortable', bad)).not.toThrow();
  });
});

describe('seeding from the Qt keys (Q-G6)', () => {
  it('maps the Qt palette names and rotation values', () => {
    expect(themeFromQt('Night (Red)')).toBe('night-red');
    expect(themeFromQt('Charcoal')).toBe('charcoal');
    expect(themeFromQt('Solarized')).toBeNull();
    expect(rotationFromQt('90')).toBe('90');
    expect(rotationFromQt(270)).toBe('270');
    expect(rotationFromQt('45')).toBeNull();
  });

  it('seeds once, and only what this browser never chose', () => {
    const s = store();
    const values = { 'ui.theme.preset': 'Night (Red)', 'ui.display.rotation': '180' };
    expect(seedFromQt(values, { theme: false, rotation: true }, s)).toEqual({ theme: 'night-red', rotation: null });
    expect(s.map.get(SEEDED_KEY)).toBe('1');
    // Later Qt changes never override the viewer's choice.
    expect(seedFromQt({ 'ui.theme.preset': 'Charcoal' }, { theme: false, rotation: false }, s)).toEqual({ theme: null, rotation: null });
  });
});
