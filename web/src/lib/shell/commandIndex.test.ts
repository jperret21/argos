import { describe, expect, it, vi } from 'vitest';
import type { KeyMeta, MountState } from '../api/types';
import { KEYMAP } from '../app/keymap';
import { ShortcutRegistry } from '../app/shortcuts';
import { buildIndex, type IndexSource } from './commandIndex';
import { rank } from './commands';

const MOUNT: MountState = { state: 'tracking', ra_hours: 19.42, dec_deg: 42.78, alt_deg: 56, az_deg: 278, tracking: true, pier_side: null, target: null };

function source(over: Partial<IndexSource> = {}): IndexSource & { calls: string[]; registry: ShortcutRegistry } {
  const calls: string[] = [];
  const registry = new ShortcutRegistry(KEYMAP, { mac: true, desktop: false });
  const meta: Record<string, KeyMeta> = {
    'site.latitude': {
      type: 'float', default: 0, nullable: false, min: -90, max: 90, step: 0.00001, options: null, unit: '°',
      label: 'Latitude', help: 'Geodetic latitude', used_by: ['FITS SITELAT'], category: 'observer_site', advanced: false, read_only: false,
    },
    'alpaca.host': {
      type: 'host', default: '', nullable: false, min: null, max: null, step: null, options: null, unit: null,
      label: 'Seestar address', help: '', used_by: ['connect'], category: 'connection', advanced: false, read_only: false,
    },
  };
  const app: IndexSource & { calls: string[]; registry: ShortcutRegistry } = {
    calls,
    registry,
    section: 'configuration',
    configMeta: meta,
    configValues: { 'site.latitude': 48.8277, 'alpaca.host': '' },
    mount: MOUNT,
    theme: 'observatory',
    density: 'compact',
    linkOpen: true,
    canMount: true,
    canCamera: true,
    live: false,
    slewing: false,
    cameraBusy: false,
    equipment: { ready: 2, anyLinked: true },
    appInfo: { docs_url: 'https://perretjules.com/argos/' },
    shortcuts: registry,
    connectProblem: () => null,
    exposureProblem: () => null,
    go: (s) => void calls.push(`go:${s}`),
    openSettings: (c, k) => void calls.push(`settings:${c}:${k ?? ''}`),
    connectAll: async () => calls.push('connectAll'),
    disconnectAll: async () => calls.push('disconnectAll'),
    park: async () => calls.push('park'),
    unpark: async () => calls.push('unpark'),
    setTracking: async (on) => calls.push(`tracking:${on}`),
    stopMount: async () => calls.push('stopMount'),
    capture: async () => calls.push('capture'),
    toggleLive: async () => calls.push('live'),
    startDiscovery: async () => calls.push('discover'),
    checkSite: async () => calls.push('checkSite'),
    setTheme: (t) => void calls.push(`theme:${t}`),
    setDensity: (d) => void calls.push(`density:${d}`),
    resetAllLayouts: () => void calls.push('resetLayouts'),
    shortcutSheetOpen: false,
    supportBundleOpen: false,
    ...over,
  };
  return app;
}

const none = async () => {};

describe('command palette index', () => {
  it('marks every equipment and mount action as hardware (Enter opens the confirmation)', () => {
    const idx = buildIndex(source(), none);
    const hw = idx.filter((c) => c.group === 'Hardware');
    expect(hw.map((c) => c.id)).toEqual(['hw.connect-all', 'hw.disconnect-all', 'hw.park', 'hw.unpark', 'hw.tracking']);
    expect(hw.every((c) => c.hardware && c.hardware.confirm)).toBe(true);
    expect(idx.find((c) => c.id === 'hw.unpark')?.disabled).toBe('the mount is not parked');
  });

  it('gives the buttons\' reasons when the mount or the server is not there', () => {
    expect(buildIndex(source({ canMount: false }), none).find((c) => c.id === 'hw.park')?.disabled).toBe('connect the mount first (Connection, F1)');
    expect(buildIndex(source({ linkOpen: false }), none).find((c) => c.id === 'hw.park')?.disabled).toBe('the ARGOS server is not reachable');
  });

  it('indexes the registry with its keys, the sections and every Settings key', () => {
    const idx = buildIndex(source(), none);
    expect(idx.find((c) => c.id === 'nav.imaging')).toMatchObject({ title: 'Observe', keys: 'F2', group: 'Sections' });
    expect(idx.find((c) => c.id === 'km.log.toggle')).toMatchObject({ keys: 'L' });
    expect(idx.find((c) => c.id === 'km.view.crosshair')).toMatchObject({ keys: 'X', hint: 'opens Observe' });
    expect(idx.find((c) => c.id === 'set.site.latitude')).toMatchObject({ title: 'Observer & site › Latitude', hint: '+48.82770°' }); // ° against the number (BRAND 5)
    expect(idx.find((c) => c.id === 'set.alpaca.host')?.title).toBe('Connection › Seestar address');
    // Planned keys are not offered; Escape and the palette itself are not commands.
    expect(idx.some((c) => c.id === 'km.observe.watch' || c.id === 'km.motion.abort' || c.id === 'km.palette.open')).toBe(false);
  });

  it('opens Settings at a key, and runs an Observe key after opening Observe', async () => {
    const app = source();
    const after = vi.fn(async () => {});
    const idx = buildIndex(app, after);
    await idx.find((c) => c.id === 'set.site.latitude')!.run();
    expect(app.calls).toContain('settings:observer_site:site.latitude');
    const run = vi.fn();
    app.registry.handle('view.crosshair', run);
    await idx.find((c) => c.id === 'km.view.crosshair')!.run();
    expect(app.calls).toContain('go:imaging');
    expect(after).toHaveBeenCalled();
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('ranks "park" to the Park command and "latitude" to the field', () => {
    const idx = buildIndex(source(), none);
    expect(rank('park', idx)[0].cmd.id).toBe('hw.park');
    expect(rank('latitude', idx)[0].cmd.id).toBe('set.site.latitude');
    expect(rank('comfortable', idx)[0].cmd.id).toBe('density.comfortable');
  });
});

describe('registry trigger (palette)', () => {
  it('runs a bound, active binding with its guard, and refuses the others', () => {
    const r = new ShortcutRegistry(KEYMAP, { mac: false, desktop: false });
    const fn = vi.fn();
    expect(r.canTrigger('log.toggle')).toBe(false); // not bound yet
    r.handle('log.toggle', fn);
    expect(r.trigger('log.toggle')).toBe(true);
    expect(fn).toHaveBeenCalledTimes(1);
    const cross = vi.fn();
    r.handle('view.crosshair', cross, () => false);
    expect(r.canTrigger('view.crosshair', ['imaging'])).toBe(false); // guard false
    expect(r.trigger('observe.watch')).toBe(false); // planned
    expect(cross).not.toHaveBeenCalled();
  });
});
