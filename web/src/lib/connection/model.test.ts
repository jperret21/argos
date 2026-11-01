import { describe, expect, it } from 'vitest';
import type { ConnectionState, DeviceState, DevicesState, NetworkState, Profile } from '../api/types';
import { deviceUsable } from '../app/status';
import {
  ago,
  currentLink,
  deviceTooltip,
  deviceView,
  devicesSummary,
  disconnectRisk,
  EMPTY_DEVICE,
  firstRunChecklist,
  isReleaseAction,
  networkView,
  parseDiscoveryResult,
  profileSpecs,
  searchedText,
  siteSummary,
} from './model';

const dev = (patch: Partial<DeviceState>): DeviceState => ({ ...EMPTY_DEVICE, since: '2026-11-01T21:00:00Z', ...patch });
const SEESTAR = { mode: 'alpaca' as const, host: '192.168.1.42', port: 32323 };

function devices(patch: Partial<Record<keyof DevicesState, Partial<DeviceState>>> = {}): DevicesState {
  return {
    mount: dev(patch.mount ?? {}),
    camera: dev(patch.camera ?? {}),
    filterwheel: dev(patch.filterwheel ?? {}),
    focuser: dev(patch.focuser ?? {}),
  };
}

describe('deviceView: every state is a word, a mark shape and an action', () => {
  it('disconnected: ring, Connect', () => {
    const v = deviceView('mount', dev({}));
    expect([v.word, v.mark, v.action, v.ready]).toEqual(['Disconnected', 'ring', 'connect', false]);
  });

  it('connecting: spinner, the address, Cancel (a release action)', () => {
    const v = deviceView('camera', dev({ state: 'connecting', link: SEESTAR }));
    expect([v.word, v.spinning, v.detail, v.action]).toEqual(['Connecting', true, '192.168.1.42:32323', 'cancel']);
    expect(isReleaseAction(v.action)).toBe(true);
    expect(deviceView('camera', dev({ state: 'connecting', link: { mode: 'simulator', host: null, port: null } })).detail).toBe(
      'Simulator',
    );
  });

  it('connected: filled, the name plus what the device says, Disconnect', () => {
    const v = deviceView('filterwheel', dev({ state: 'connected', name: 'Seestar wheel', info: 'IR' }));
    expect([v.word, v.mark, v.detail, v.action, v.ready]).toEqual(['Ready', 'filled', 'Seestar wheel · IR', 'disconnect', true]);
    // info equal to the name is not repeated
    expect(deviceView('mount', dev({ state: 'connected', name: 'S30', info: 'S30' })).detail).toBe('S30');
  });

  it('connected with server warnings: the warning tone, warnings kept', () => {
    const v = deviceView('mount', dev({ state: 'connected', name: 'S30', warnings: ['Mount clock is 2 h off'] }));
    expect(v.problem).toBe('warning');
    expect(v.warnings).toEqual(['Mount clock is 2 h off']);
  });

  it('busy: half mark, the activity as the word, still ready', () => {
    const v = deviceView('mount', dev({ state: 'busy', name: 'S30', info: 'slewing' }));
    expect([v.word, v.mark, v.ready, v.action]).toEqual(['Slewing', 'half', true, 'disconnect']);
  });

  it('error: the FULL text (never cut), cross, Retry', () => {
    const long = `Cannot reach 192.0.2.1:32323 — timed out after 3 s ${'x'.repeat(120)}`;
    const v = deviceView('focuser', dev({ state: 'error', error: long, info: long }));
    expect([v.word, v.mark, v.action, v.problem]).toEqual(['Error', 'cross', 'retry', 'error']);
    expect(v.detail).toBe(long);
  });

  it('mount auto-retry: Lost, retrying every 10 s, Stop retrying', () => {
    const v = deviceView('mount', dev({ state: 'error', retrying: true, error: 'Mount connection lost.' }));
    expect([v.word, v.action, v.problem]).toEqual(['Lost', 'stop-retrying', 'warning']);
    expect(v.detail).toBe('Retrying every 10 s: Mount connection lost.');
  });

  it('tooltip names the device and the state', () => {
    expect(deviceTooltip(deviceView('camera', dev({})))).toBe('Camera: not connected');
    expect(deviceTooltip(deviceView('camera', dev({ state: 'connected', name: 'Sim' })))).toBe('Camera: ready · Sim');
  });
});

describe('devicesSummary', () => {
  it('counts ready devices (the toolbar button, not the summary, says "Equipment ready")', () => {
    expect(devicesSummary(null).text).toBe('0 of 4 devices ready');
    const two = devicesSummary(devices({ mount: { state: 'connected' }, camera: { state: 'busy', info: 'live' } }));
    expect([two.ready, two.text, two.anyLinked, two.allReady]).toEqual([2, '2 of 4 devices ready', true, false]);
    const all = devicesSummary(
      devices({
        mount: { state: 'connected' },
        camera: { state: 'connected' },
        filterwheel: { state: 'connected' },
        focuser: { state: 'connected' },
      }),
    );
    expect([all.text, all.allReady, all.tone, all.progress]).toEqual(['4 of 4 devices ready', true, 'ok', null]);
  });

  it('says what a running Connect all does: the address check, then the device being opened', () => {
    const queued = { state: 'connecting' as const, info: 'queued' };
    const checking = devicesSummary(devices({ mount: queued, camera: queued, filterwheel: queued, focuser: queued }));
    expect([checking.progress, checking.anyLinked, checking.tone]).toEqual(['checking the address…', true, 'busy']);
    const opening = devicesSummary(
      devices({ mount: { state: 'connected' }, camera: { state: 'connecting' }, filterwheel: queued, focuser: queued }),
    );
    expect([opening.text, opening.progress]).toEqual(['1 of 4 devices ready', 'connecting camera…']);
  });

  it('a queued device reads "Queued" (idle ring, no spinner) and can be cancelled', () => {
    const v = deviceView('focuser', dev({ state: 'connecting', info: 'queued' }));
    expect([v.word, v.mark, v.tone, v.spinning, v.action, v.detail]).toEqual(['Queued', 'ring', 'idle', false, 'cancel', '']);
    const opening = deviceView('focuser', dev({ state: 'connecting', link: SEESTAR }));
    expect([opening.word, opening.spinning]).toEqual(['Connecting', true]);
  });

  it('an error wins the tone; a retrying mount holds the link', () => {
    const s = devicesSummary(devices({ camera: { state: 'error', error: 'refused' } }));
    expect([s.tone, s.anyError, s.anyLinked]).toEqual(['error', true, false]);
    expect(devicesSummary(devices({ mount: { state: 'error', retrying: true } })).anyLinked).toBe(true);
    expect(devicesSummary(devices({ focuser: { state: 'connecting' } })).anyConnecting).toBe(true);
  });
});

describe('currentLink', () => {
  it('is the link of the first device that holds one', () => {
    expect(currentLink(devices())).toBeNull();
    expect(currentLink(devices({ camera: { state: 'error', link: SEESTAR } }))).toEqual(SEESTAR);
    expect(currentLink(devices({ focuser: { state: 'disconnected', link: SEESTAR } }))).toBeNull();
  });
});

describe('networkView: three states each, never "down" for "not configured" (Q-G13)', () => {
  const now = Date.parse('2026-11-01T21:00:10Z');
  const base: NetworkState = { seestar: null, internet: null, host: null, port: null, t: null, internet_t: null };
  it('not configured / not checked', () => {
    const n = networkView(base, now);
    expect([n.seestar.word, n.seestar.mark, n.internet.word, n.checked]).toEqual(['not configured', 'none', 'not checked', '']);
  });
  it('reachable / offline with the time of the check', () => {
    const n = networkView({ ...base, seestar: true, internet: false, t: '2026-11-01T21:00:06Z', internet_t: '2026-11-01T20:58:10Z' }, now);
    expect([n.seestar.word, n.seestar.mark, n.checked]).toEqual(['reachable', 'filled', '4 s ago']);
    expect([n.internet.word, n.internet.mark, n.internetChecked]).toEqual(['offline', 'ring', '2 min ago']);
  });
  it('an unreachable address the devices do not use is "not in use", never a red alarm', () => {
    const down = { ...base, seestar: false, host: '192.168.0.39', port: 32323, t: '2026-11-01T21:00:06Z' };
    expect(networkView(down, now).seestar).toEqual({ mark: 'ring', word: 'unreachable', tone: 'error' });
    expect(networkView(down, now, false).seestar).toEqual({ mark: 'none', word: 'not in use', tone: 'idle' });
    // Reachable stays reachable either way.
    expect(networkView({ ...down, seestar: true }, now, false).seestar.word).toBe('reachable');
  });
  it('ago() formats seconds, minutes and hours', () => {
    expect(ago(null, now)).toBe('');
    expect(ago('2026-11-01T19:45:10Z', now)).toBe('1 h 15 min ago');
  });
});

describe('profile and site', () => {
  const p: Profile = {
    key: 's30pro',
    name: 'ZWO Seestar S30 Pro',
    validated: true,
    caveats: [],
    aperture_mm: 30,
    focal_length_mm: 160,
    focal_ratio: 5.333,
    sensor: 'IMX585',
    pixel_size_um: 2.9,
    sensor_px: [3840, 2160],
    bayer: 'GRBG',
    arcsec_per_px: 3.7385,
    fov_deg: [3.988, 2.243],
    adc_bits: 12,
    full_well_adu: 60000,
    linearity_max_adu: 50000,
    filter_names: [],
    ap_host: '10.0.0.1',
    overrides: {},
  };
  it('specs line in BRAND 5 formats', () => {
    expect(profileSpecs(p)).toBe('30 mm · f/5.3 · IMX585 · 2.9 µm · 3.74″/px · 3.99° × 2.24° · GRBG');
  });
  it('site summary: signed coordinates with U+2212, missing at (0, 0)', () => {
    const s = siteSummary({ 'site.name': 'Home', 'site.latitude': 48.8277, 'site.longitude': -2.3826, 'site.elevation': 60.4 });
    expect([s.missing, s.name, s.coords, s.elevation]).toEqual([false, 'Home', '+48.82770° −2.38260°', '60 m']);
    expect(siteSummary({}).missing).toBe(true);
    expect(siteSummary(null).name).toBe('No site set');
  });
  it('first-run checklist (Q-G11)', () => {
    const c = firstRunChecklist({ 'observer.obscode': 'PJUA', 'site.latitude': 1, 'site.longitude': 0 }, false);
    expect(c.map((i) => [i.id, i.done])).toEqual([
      ['obscode', true],
      ['site', true],
      ['astap', false],
    ]);
  });
});

describe('discovery result', () => {
  it('keeps every device found and drops malformed entries', () => {
    const r = parseDiscoveryResult({
      devices: [{ host: '192.168.1.42', port: 32323, name: 'Seestar' }, { host: 'x' }, { host: '10.0.0.1', port: 32323, name: null }],
      method: 'broadcast',
      searched: ['broadcast'],
    });
    expect(r?.devices).toEqual([
      { host: '192.168.1.42', port: 32323, name: 'Seestar' },
      { host: '10.0.0.1', port: 32323, name: null },
    ]);
    expect(r && searchedText(r)).toBe('Searched: broadcast');
    expect(parseDiscoveryResult(null)).toBeNull();
    expect(searchedText({ devices: [], method: null, searched: ['broadcast', 'probe', 'subnet'] })).toBe(
      'Searched: broadcast, then direct probes, then subnet scan',
    );
  });
});

describe('disconnectRisk (02 W10b, Q-C5): asked only while something runs', () => {
  const idle = { live: false, exposing: false, slewing: false };
  it('nothing runs: no confirmation', () => {
    expect(disconnectRisk(idle)).toBeNull();
  });
  it('names what stops, limited to the devices released', () => {
    expect(disconnectRisk({ ...idle, live: true })).toMatch(/Live view is running/);
    expect(disconnectRisk({ ...idle, exposing: true }, ['mount'])).toBeNull();
    expect(disconnectRisk({ ...idle, slewing: true }, ['mount'])).toMatch(/slewing/);
    expect(disconnectRisk({ ...idle, slewing: true }, ['camera'])).toBeNull();
  });
});

describe('deviceUsable: each device by its own record (technical review, camera-only repro)', () => {
  const connected: ConnectionState = { state: 'connected', mode: 'simulator', device_name: 'Sim', message: null };
  it('the camera alone makes the v1 record "connected" but not the mount usable', () => {
    const only = devices({ camera: { state: 'connected' } });
    expect(deviceUsable(only, 'camera', connected)).toBe(true);
    expect(deviceUsable(only, 'mount', connected)).toBe(false);
  });
  it('a mount in error (or retrying) with the camera connected is not usable; busy is', () => {
    const d = devices({ camera: { state: 'busy', info: 'live' }, mount: { state: 'error', retrying: true } });
    expect(deviceUsable(d, 'mount', connected)).toBe(false);
    expect(deviceUsable(d, 'camera', connected)).toBe(true);
    expect(deviceUsable(devices({ mount: { state: 'busy', info: 'slewing' } }), 'mount', connected)).toBe(true);
  });
  it('an API 1 server (no device records) falls back to the v1 pair', () => {
    expect(deviceUsable(null, 'mount', connected)).toBe(true);
    expect(deviceUsable(null, 'mount', { ...connected, state: 'disconnected' })).toBe(false);
  });
});
