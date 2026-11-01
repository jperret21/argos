import { describe, expect, it } from 'vitest';
import { FrameRateMeter, formatFps, formatLatency } from './metrics';
import {
  ariaShortcut,
  detectMac,
  formatShortcut,
  isTypingTarget,
  matchesShortcut,
  type KeyLike,
} from './shortcuts';
import { DEFAULT_THEME, loadTheme, nextTheme, parseCssColor, saveTheme, THEME_STORAGE_KEY } from './theme';

const key = (k: string, extra: Partial<KeyLike> = {}): KeyLike => ({
  key: k,
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...extra,
});

describe('shortcuts', () => {
  it('formats with macOS glyphs or words', () => {
    expect(formatShortcut('Shift+A', true)).toBe('⇧A');
    expect(formatShortcut('Shift+A', false)).toBe('Shift+A');
    expect(formatShortcut('e', false)).toBe('E');
    expect(formatShortcut('Escape', true)).toBe('Esc');
    expect(formatShortcut('+', true)).toBe('+');
    expect(formatShortcut('F2', false)).toBe('F2');
  });

  it('builds aria-keyshortcuts values', () => {
    expect(ariaShortcut('+')).toBe('Plus');
    expect(ariaShortcut('-')).toBe('Minus');
    expect(ariaShortcut('Shift+A')).toBe('Shift+A');
  });

  it('matches letters with the exact Shift state, ignoring case', () => {
    expect(matchesShortcut(key('a'), 'A')).toBe(true);
    expect(matchesShortcut(key('A', { shiftKey: true }), 'A')).toBe(false);
    expect(matchesShortcut(key('A', { shiftKey: true }), 'Shift+A')).toBe(true);
    expect(matchesShortcut(key('a'), 'Shift+A')).toBe(false);
  });

  it('ignores Shift for digits and symbols (AZERTY types them shifted)', () => {
    expect(matchesShortcut(key('1', { shiftKey: true }), '1')).toBe(true);
    expect(matchesShortcut(key('&', { code: 'Numpad1' }), '1')).toBe(true);
    expect(matchesShortcut(key('+', { shiftKey: true }), '+')).toBe(true);
    expect(matchesShortcut(key('='), '+')).toBe(true);
    expect(matchesShortcut(key('-'), '-')).toBe(true);
  });

  it('never fires with Ctrl, Cmd or Alt held', () => {
    expect(matchesShortcut(key('e', { metaKey: true }), 'E')).toBe(false);
    expect(matchesShortcut(key('F2', { ctrlKey: true }), 'F2')).toBe(false);
  });

  it('matches named keys', () => {
    expect(matchesShortcut(key('Escape'), 'Escape')).toBe(true);
    expect(matchesShortcut(key('F3'), 'F3')).toBe(true);
  });

  it('detects text fields', () => {
    const field = { closest: (s: string) => (s.includes('input') ? {} : null) };
    expect(isTypingTarget(field as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ closest: () => null } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it('detects the platform', () => {
    expect(detectMac('MacIntel')).toBe(true);
    expect(detectMac('Linux x86_64')).toBe(false);
  });
});

describe('FrameRateMeter', () => {
  it('reports fps over the last frames and the display latency', () => {
    const m = new FrameRateMeter(4);
    const t0 = Date.parse('2026-11-01T21:00:00.000Z');
    expect(m.record(t0 + 40, '2026-11-01T21:00:00.000Z')).toEqual({ fps: null, latencyMs: 40, frames: 1 });
    m.record(t0 + 1040, '2026-11-01T21:00:01.000Z');
    m.record(t0 + 2040, '2026-11-01T21:00:02.000Z');
    const s = m.record(t0 + 3040, '2026-11-01T21:00:03.000Z');
    expect(s.fps).toBeCloseTo(1, 10);
    expect(s.latencyMs).toBe(40);
    expect(s.frames).toBe(4);
  });

  it('restarts the cadence after a long pause and clamps clock jitter', () => {
    const m = new FrameRateMeter(4, 5000);
    m.record(0, null);
    m.record(500, null);
    const s = m.record(60_000, new Date(60_010).toISOString());
    expect(s.fps).toBeNull();
    expect(s.latencyMs).toBe(0);
  });

  it('times the cadence by frame timestamps, so a replayed frame does not inflate it', () => {
    const m = new FrameRateMeter(4);
    const t0 = Date.parse('2026-11-01T21:00:00.000Z');
    // Replay of the latest frame (exposure ended at t0), then the next live
    // frame only 150 ms later on screen, but one exposure later in time.
    m.record(t0 + 850, '2026-11-01T21:00:00.000Z', 41);
    const s = m.record(t0 + 1000 + 40, '2026-11-01T21:00:01.000Z', 42);
    expect(s.fps).toBeCloseTo(1, 10);
    // The same frame drawn again (viewer remount) is not a new frame.
    expect(m.record(t0 + 1500, '2026-11-01T21:00:01.000Z', 42).frames).toBe(2);
  });

  it('formats', () => {
    expect(formatFps(0.987)).toBe('1.0 fps');
    expect(formatFps(23.4)).toBe('23 fps');
    expect(formatFps(null)).toBe('—');
    expect(formatLatency(38.4)).toBe('38 ms');
    expect(formatLatency(1240)).toBe('1.24 s');
  });
});

describe('theme persistence', () => {
  it('round-trips and cycles', () => {
    const data = new Map<string, string>();
    const storage = {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
    };
    expect(loadTheme(storage)).toBe(DEFAULT_THEME);
    expect(saveTheme('night-red', storage)).toBe(true);
    expect(data.get(THEME_STORAGE_KEY)).toBe('night-red');
    expect(loadTheme(storage)).toBe('night-red');
    expect(nextTheme('observatory')).toBe('charcoal');
    expect(nextTheme('charcoal')).toBe('night-red');
    expect(nextTheme('night-red')).toBe('observatory');
  });

  it('survives storage that throws or holds garbage', () => {
    const throwing = {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {
        throw new Error('QuotaExceededError');
      },
    };
    expect(loadTheme(throwing)).toBe(DEFAULT_THEME);
    expect(saveTheme('charcoal', throwing)).toBe(false);
    expect(loadTheme({ getItem: () => 'neon', setItem: () => {} })).toBe(DEFAULT_THEME);
    expect(loadTheme(null)).toBe(DEFAULT_THEME);
  });

  it('parses the viewer tint token', () => {
    expect(parseCssColor('#d80000')).toEqual([216 / 255, 0, 0]);
    expect(parseCssColor(' #FFF ')).toEqual([1, 1, 1]);
    expect(parseCssColor('rgb(216, 0, 0)')).toEqual([216 / 255, 0, 0]);
    expect(parseCssColor('red')).toBeNull();
  });
});

describe('per-viewer preferences', () => {
  it('round-trips JSON values and falls back on bad or blocked storage', async () => {
    const { isBoolean, loadPref, savePref } = await import('./prefs');
    const data = new Map<string, string>();
    const store = {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
    };
    expect(loadPref('rail', isBoolean, true, store)).toBe(true);
    savePref('rail', false, store);
    expect(loadPref('rail', isBoolean, true, store)).toBe(false);
    data.set('rail', '{not json');
    expect(loadPref('rail', isBoolean, true, store)).toBe(true);
    const blocked = {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {
        throw new Error('SecurityError');
      },
    };
    expect(loadPref('rail', isBoolean, true, blocked)).toBe(true);
    expect(() => savePref('rail', false, blocked)).not.toThrow();
  });
});

describe('status wording', () => {
  it('claims no device state while the server link is down', async () => {
    const { cameraStatus, connectionStatus, mountStatus } = await import('./status');
    const cam = { state: 'live', exposure_s: 1, gain: 80, last_frame_seq: 3, sensor: null } as const;
    expect(cameraStatus(cam, true).label).toBe('Live');
    expect(cameraStatus(cam, true, true)).toEqual({ tone: 'idle', label: 'No link' });
    expect(mountStatus(null, true, true).label).toBe('No link');
    expect(connectionStatus(null, 'forbidden')).toEqual({ tone: 'error', label: 'Origin refused' });
    expect(connectionStatus(null, 'reconnecting').label).toBe('Server offline');
  });
});

describe('tooltip timing', () => {
  it('waits on the first hover, then shows neighbours at once', async () => {
    const { hoverDelay, HOVER_DELAY_MS, WARM_MS } = await import('../components/tooltip');
    expect(hoverDelay(10_000, -Infinity, false)).toBe(HOVER_DELAY_MS);
    expect(hoverDelay(10_000, 10_000 - WARM_MS / 2, false)).toBe(0);
    expect(hoverDelay(10_000, 10_000 - WARM_MS * 2, false)).toBe(HOVER_DELAY_MS);
    expect(hoverDelay(10_000, -Infinity, true)).toBe(0);
  });
});

