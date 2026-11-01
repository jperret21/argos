import { describe, expect, it } from 'vitest';
import { clampDrawerHeight, clearAllLayouts, clearSectionLayout, isDrawerPrefs } from './panels';
import { removePrefsWithPrefix } from './prefs';
import { startupView, failureReport } from './startup';

class MemoryStorage {
  private map = new Map<string, string>();
  get length(): number {
    return this.map.size;
  }
  key(i: number): string | null {
    return [...this.map.keys()][i] ?? null;
  }
  getItem(k: string): string | null {
    return this.map.get(k) ?? null;
  }
  setItem(k: string, v: string): void {
    this.map.set(k, v);
  }
  removeItem(k: string): void {
    this.map.delete(k);
  }
  keys(): string[] {
    return [...this.map.keys()].sort();
  }
}

function seeded(): MemoryStorage {
  const s = new MemoryStorage();
  for (const k of [
    'argos.theme',
    'argos.rotation',
    'argos.rail-open',
    'argos.layout.imaging.camera',
    'argos.layout.imaging.statistics',
    'argos.layout.analyze.frames',
    'argos.drawer.imaging',
    'argos.drawer.analyze',
    'argos.rail-width.imaging',
    'argos.card.camera',
  ]) {
    s.setItem(k, 'true');
  }
  return s;
}

describe('Reset layout', () => {
  it('clears one section only, keeping theme, rotation and other sections', () => {
    const s = seeded();
    const removed = clearSectionLayout(s, 'imaging', ['argos.card.camera']);
    expect(removed.sort()).toEqual([
      'argos.card.camera',
      'argos.drawer.imaging',
      'argos.layout.imaging.camera',
      'argos.layout.imaging.statistics',
      'argos.rail-width.imaging',
    ]);
    expect(s.keys()).toEqual([
      'argos.drawer.analyze',
      'argos.layout.analyze.frames',
      'argos.rail-open',
      'argos.rotation',
      'argos.theme',
    ]);
  });

  it('"Reset all layouts" clears every section and the rail, not theme or rotation', () => {
    const s = seeded();
    clearAllLayouts(s);
    expect(s.keys()).toEqual(['argos.card.camera', 'argos.rotation', 'argos.theme']);
  });

  it('survives missing or throwing storage', () => {
    expect(clearSectionLayout(null, 'imaging')).toEqual([]);
    const broken = {
      get length(): number {
        throw new Error('blocked');
      },
      key: () => null,
      removeItem: () => {},
    };
    expect(clearAllLayouts(broken)).toEqual([]);
    expect(removePrefsWithPrefix('argos.', broken as unknown as Storage)).toEqual([]);
  });

  it('keeps the drawer between 160 px and half the section', () => {
    expect(clampDrawerHeight(100, 400)).toBe(160);
    expect(clampDrawerHeight(900, 400)).toBe(400);
    expect(clampDrawerHeight(250.4, 400)).toBe(250);
    expect(clampDrawerHeight(Number.NaN, 400)).toBe(216);
    expect(clampDrawerHeight(300, 100)).toBe(160);
    expect(isDrawerPrefs({ open: true, tab: 'log', height: 216 })).toBe(true);
    expect(isDrawerPrefs({ open: 'yes', tab: 'log', height: 216 })).toBe(false);
  });
});

describe('start-up stages', () => {
  it('browser: one stage, done when health answers and the first status arrives', () => {
    expect(startupView({ desktop: false, health: 'pending', firstStatus: false }).stages).toEqual([
      { id: 'link', label: 'Connecting to the ARGOS server…', state: 'active' },
    ]);
    const ok = startupView({ desktop: false, health: 'ok', firstStatus: true });
    expect(ok.ready).toBe(true);
    expect(startupView({ desktop: false, health: 'ok', firstStatus: false }).ready).toBe(false);
  });

  it('desktop: the server stage first; a failure is kept, never "ready"', () => {
    const starting = startupView({ desktop: true, sidecar: 'starting', health: 'pending', firstStatus: false });
    expect(starting.stages.map((s) => s.state)).toEqual(['active', 'pending']);
    const failed = startupView({
      desktop: true,
      sidecar: 'failed',
      health: 'pending',
      firstStatus: false,
      failure: {
        title: 'ARGOS could not start',
        message: 'The ARGOS server stopped during start-up.',
        detail: "ModuleNotFoundError: No module named 'astropy'",
        logPath: '~/Library/Logs/Argos',
      },
    });
    expect(failed.ready).toBe(false);
    expect(failed.stages[0].state).toBe('failed');
    expect(failed.failure?.logPath).toBe('~/Library/Logs/Argos');
    expect(failureReport(failed.failure!, '0.4.2')).toContain("No module named 'astropy'");
    expect(failureReport(failed.failure!, '0.4.2')).toContain('Log folder: ~/Library/Logs/Argos');
  });

  it('a failed health check shows a failure even without details', () => {
    const v = startupView({ desktop: false, health: 'failed', firstStatus: false });
    expect(v.failure?.title).toBe('ARGOS could not start');
    expect(v.ready).toBe(false);
  });
});
