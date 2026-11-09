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

  it('offers Centre target and Sync as hardware with their reasons, and the field actions (W4)', async () => {
    const calls: string[] = [];
    const field = {
      solving: true,
      auto: false,
      centerReason: 'identify the field first (S)',
      centerTarget: 'RR Lyr',
      syncReason: null,
      cancelSolve: async () => calls.push('cancel'),
      setAuto: async (on: boolean) => calls.push(`auto:${on}`),
      center: async () => calls.push('center'),
      sync: async () => calls.push('sync'),
    };
    const idx = buildIndex(source({ fieldCommands: () => field }), none);
    const center = idx.find((c) => c.id === 'hw.center')!;
    expect(center).toMatchObject({ title: 'Centre RR Lyr (sync, then slew)', group: 'Hardware', disabled: 'identify the field first (S)' });
    expect(center.hardware?.confirm).toBe('Centre target');
    const sync = idx.find((c) => c.id === 'hw.sync')!;
    expect(sync.hardware?.question).toBe('Sync the mount to the plate solution?');
    expect(sync.disabled).toBeNull();
    await sync.run();
    await idx.find((c) => c.id === 'act.field-auto')!.run();
    await idx.find((c) => c.id === 'act.field-cancel')!.run();
    expect(calls).toEqual(['sync', 'auto:true', 'cancel']);
    // The Field keys are built now: listed with their keys, never as hardware.
    expect(idx.find((c) => c.id === 'km.field.solve')).toMatchObject({ keys: 'S', group: 'Actions' });
    expect(idx.find((c) => c.id === 'km.field.labels')).toMatchObject({ keys: 'N' });
    // No field record (the tests' fake app of earlier waves): no field commands.
    expect(buildIndex(source(), none).some((c) => c.id === 'hw.center')).toBe(false);
  });

  it('offers the live photometry tabs and the comparison recommendation (W5)', async () => {
    const calls: string[] = [];
    const phot = {
      recommendReason: null as string | null,
      running: false,
      count: 5,
      openTab: (t: string) => void calls.push(`tab:${t}`),
      recommend: async (m: string) => calls.push(`rec:${m}`),
    };
    const idx = buildIndex(source({ photometryCommands: () => phot }), none);
    await idx.find((c) => c.id === 'act.phot-light-curve')!.run();
    await idx.find((c) => c.id === 'act.phot-ensemble')!.run();
    const complete = idx.find((c) => c.id === 'act.phot-complete')!;
    expect(complete).toMatchObject({ title: 'Complete the comparison ensemble (up to 5)', disabled: null });
    expect(complete.hardware).toBeUndefined();
    await complete.run();
    expect(calls).toEqual(['tab:light-curve', 'tab:ensemble', 'rec:complete']);
    expect(rank('leave-one-out', idx)[0].cmd.id).toBe('act.phot-ensemble');
    // The server would answer 409: the reason is shown instead.
    const blocked = buildIndex(source({ photometryCommands: () => ({ ...phot, recommendReason: 'identify the field first (S)', running: true }) }), none);
    expect(blocked.find((c) => c.id === 'act.phot-replace')!.disabled).toBe('identify the field first (S)');
    expect(buildIndex(source({ photometryCommands: () => ({ ...phot, running: true }) }), none).find((c) => c.id === 'act.phot-replace')!.disabled).toMatch(/asks first/);
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
