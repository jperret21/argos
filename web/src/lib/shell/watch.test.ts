import { describe, expect, it, vi } from 'vitest';
import { ageView, altLine, canPause, checkKeepAwake, compsLine, computerLine, endsView, hfdRule, linksView, runSeries, errLine, framesText, isDim, stateWord, watchKey } from './watch';
import { keepScreenOn, type WakeSentinel, type WakeState } from './wakelock';

const T = 1_790_000_000;

describe('Watch values', () => {
  it('says the age, late past 1.5 cadences (as of), overdue past max(2 × cadence, cadence + 60 s)', () => {
    expect(ageView(null, T, 51.5, true)).toMatchObject({ value: '—', late: false, note: 'no frame yet' });
    expect(ageView(T - 12, T, 51.5, true)).toEqual({ value: '12 s', late: false, overdue: false, note: 'last frame · every 52 s' });
    const late = ageView(T - 80, T, 51.5, true);
    expect(late.late).toBe(true);
    expect(late.overdue).toBe(false);
    expect(late.note).toMatch(/^last frame · as of \d\d:\d\d · every 52 s$/);
    // max(103, 111.5) = 111.5 s: the server's "No new frame" limit on the 2026-09-25 run.
    expect(ageView(T - 111, T, 51.5, true).overdue).toBe(false);
    const over = ageView(T - 112, T, 51.5, true);
    expect(over.overdue).toBe(true);
    expect(over.value).toBe('1m 52s');
    expect(over.note).toMatch(/· overdue$/);
    // Paused: no frame expected, nothing is late.
    expect(ageView(T - 600, T, 51.5, false)).toMatchObject({ late: false, overdue: false });
    // No cadence yet: no claim.
    expect(ageView(T - 600, T, null, true)).toMatchObject({ late: false, overdue: false, note: 'last frame' });
  });

  it('writes frames, the end, the error line, the comparisons and the altitude', () => {
    expect(framesText(160, 195)).toBe('160 / 195');
    expect(framesText(1200, 1200)).toBe('1\u202f200 / 1\u202f200');
    expect(framesText(null, 195)).toBe('—');
    expect(endsView(null, T)).toEqual({ value: '—', note: 'after the first frames' });
    expect(endsView(T + 1800, T)).toEqual({ value: expect.stringMatching(/^\d\d:\d\d$/), note: 'UTC · in 30m 00s' });
    // A run that ended says when, never "after the first frames" (wave 6b fixer).
    expect(endsView(null, T, { at: T - 60 })).toEqual({ value: expect.stringMatching(/^\d\d:\d\d$/), note: 'UTC · ended' });
    expect(endsView(null, T, { at: null })).toEqual({ value: '—', note: 'ended' });
    expect(errLine(0.035, 'TG')).toBe('± 0.035 TG');
    expect(compsLine({ used: 5, total: 6, verdict: 'consistent' })).toBe('comps 5 / 6 · consistent');
    expect(compsLine(null)).toBe('comps —');
    expect(altLine(52, 30, null)).toBe('limit 30°');
    expect(altLine(25, 30, null)).toBe('below the 30° limit');
    expect(altLine(52, null, null)).toBe('no limit set');
  });

  it("says whether the server keeps the computer awake (status.keep_awake)", () => {
    expect(computerLine(null)).toBeNull();
    expect(computerLine({ state: 'off', method: null, message: null })).toBeNull();
    expect(computerLine({ state: 'held', method: 'caffeinate', message: null })).toEqual({ text: 'Computer awake (caffeinate)', warn: false });
    expect(computerLine({ state: 'failed', method: null, message: 'caffeinate not found' })).toEqual({ text: 'Computer may sleep: caffeinate not found', warn: true });
    expect(computerLine({ state: 'disabled', method: null, message: null })?.warn).toBe(true);
    // status.keep_awake as the server sends it (protocol.md KeepAwake).
    const held = checkKeepAwake({ state: 'held', method: 'caffeinate', since: '2026-09-25T20:04:53Z', reason: 'A sequence is running (RR Lyr).', message: null });
    expect(held).toEqual({ state: 'held', method: 'caffeinate', message: null, since: Date.UTC(2026, 8, 25, 20, 4, 53) / 1000, reason: 'A sequence is running (RR Lyr).' });
    expect(computerLine(held)?.text).toBe('Computer awake (caffeinate)');
    expect(checkKeepAwake({ state: 'asleep' })).toBeNull();
    expect(checkKeepAwake(undefined)).toBeNull();
    // The run's subs from the conditions columns: since the start, finite only, newest kept.
    const t = Float64Array.from([T - 30, T - 10, T, T + 10, T + 20]);
    const v = Float64Array.from([9, 8.6, NaN, 8.7, 8.8]);
    expect(runSeries(t, v, 5, T - 10)).toEqual([8.6, 8.7, 8.8]);
    expect(runSeries(t, v, 4, null)).toEqual([9, 8.6, 8.7]);
    expect(runSeries(t, v, 5, null, 2)).toEqual([8.7, 8.8]);
    // The HFD rule's line: the server's numbers when its item has them, else the rule on the run's subs.
    const hfd = [9, 8, 10, 8.5, 20];
    expect(hfdRule([], { 'alerts.hfd_factor': 2, 'alerts.baseline_frames': 4 }, hfd)).toBe(2 * 8.75);
    expect(hfdRule([], null, hfd)).toBeNull(); // 20 baseline subs by default: not yet
    expect(hfdRule([{ rule: 'hfd_rise', active: true, values: { baseline_px: 8.63, factor: 1.5 } }], null, hfd)).toBeCloseTo(12.945, 6);
    expect(hfdRule([{ rule: 'hfd_rise', active: false, values: { baseline_px: 8.63, factor: 1.5 } }], { 'alerts.baseline_frames': 3 }, hfd)).toBe(1.5 * 9);
    // The server's baseline for the run (carried from an earlier run): a line from the first sub.
    expect(hfdRule([], null, [9.7, 11.7], { hfdPx: 6.55 })).toBeCloseTo(9.825, 12);
    expect(hfdRule([], { 'alerts.hfd_factor': 2 }, [], { hfdPx: 6.55 })).toBe(13.1);
    expect(hfdRule([], null, [9.7], { hfdPx: null })).toBeNull();
  });

  it('names the state; Pause only while exposing', () => {
    expect(stateWord(null)).toBe('IDLE');
    expect(stateWord('waiting')).toBe('SCHEDULED');
    expect(stateWord('autofocus')).toBe('AUTOFOCUS');
    expect(canPause('running')).toBe(true);
    expect(canPause('paused')).toBe(false);
    expect(canPause('pausing')).toBe(false);
    expect(isDim(60)).toBe(true);
    expect(isDim(50)).toBe(false);
  });

  it('acts only on W, Esc, ? and Mod+K (owner D3)', () => {
    expect(watchKey({ key: 'w' }, true)).toBe('close');
    expect(watchKey({ key: 'W', shiftKey: true }, true)).toBe('close');
    expect(watchKey({ key: 'Escape' }, true)).toBe('close');
    expect(watchKey({ key: '?', shiftKey: true }, false)).toBe('help');
    expect(watchKey({ key: 'k', metaKey: true }, true)).toBe('palette');
    expect(watchKey({ key: 'k', ctrlKey: true }, false)).toBe('palette');
    expect(watchKey({ key: 'k', ctrlKey: true }, true)).toBeNull();
    // A key pressed to wake the screen never takes a shot or starts live view.
    for (const key of ['e', 'v', ' ', 'Enter', 'ArrowUp', 'j', 'd', 'p', 'l', '/', 'F5']) expect(watchKey({ key }, true)).toBeNull();
    expect(watchKey({ key: 'w', metaKey: true }, true)).toBeNull();
    // AZERTY: the KeyW position types "z" (no close); the W key sits at KeyZ (close).
    expect(watchKey({ key: 'z', code: 'KeyW' }, true)).toBeNull();
    expect(watchKey({ key: 'w', code: 'KeyZ' }, true)).toBe('close');
    expect(watchKey({ key: 'ц', code: 'KeyW' }, true)).toBe('close'); // a non-Latin layout
    expect(watchKey({ key: '4', altKey: true, code: 'Digit4' }, true)).toBeNull();
  });

  it('names the links that are down and folds the others (no word cut at 1 280 px)', () => {
    const cam = { label: 'Camera', tone: 'ok' as const, word: 'connected' };
    const srv = { label: 'Server', tone: 'ok' as const, word: 'connected' };
    const mount = { label: 'Mount', tone: 'idle' as const, word: 'not connected' };
    expect(linksView([cam, srv])).toEqual([{ label: 'All linked', tone: 'ok', word: 'Camera connected, Server connected', group: true }]);
    expect(linksView([cam, mount, srv])).toEqual([mount, { label: '2 linked', tone: 'ok', word: 'Camera connected, Server connected', group: true }]);
    expect(linksView([mount])).toEqual([mount]);
  });
});

describe('screen wake lock', () => {
  function fakeSentinel(): WakeSentinel & { fire: () => void } {
    let fn: (() => void) | null = null;
    const s = {
      released: false,
      release: vi.fn(async () => {
        s.released = true;
      }),
      addEventListener: (_t: 'release', f: () => void) => (fn = f),
      removeEventListener: () => (fn = null),
      fire: () => {
        s.released = true;
        fn?.();
      },
    };
    return s;
  }
  function fakeDoc() {
    let fn: (() => void) | null = null;
    return {
      visibilityState: 'visible',
      addEventListener: (_t: 'visibilitychange', f: () => void) => (fn = f),
      removeEventListener: () => (fn = null),
      show() {
        this.visibilityState = 'visible';
        fn?.();
      },
      get listening() {
        return fn !== null;
      },
    };
  }
  const flush = () => new Promise((r) => setTimeout(r, 0));

  it('says when the browser has no wake lock', () => {
    const states: WakeState[] = [];
    keepScreenOn({}, null, (s) => states.push(s));
    expect(states).toEqual(['unsupported']);
  });

  it('holds the lock, asks again when the page shows after the browser dropped it, releases on leaving', async () => {
    const sentinels: ReturnType<typeof fakeSentinel>[] = [];
    const nav = { wakeLock: { request: vi.fn(async () => (sentinels.push(fakeSentinel()), sentinels[sentinels.length - 1])) } };
    const doc = fakeDoc();
    const states: WakeState[] = [];
    const stop = keepScreenOn(nav, doc, (s) => states.push(s));
    await flush();
    expect(states).toEqual(['pending', 'held']);
    sentinels[0].fire(); // the page was hidden
    expect(states.at(-1)).toBe('released');
    doc.show();
    await flush();
    expect(nav.wakeLock.request).toHaveBeenCalledTimes(2);
    expect(states.at(-1)).toBe('held');
    stop();
    expect(sentinels[1].release).toHaveBeenCalled();
    expect(doc.listening).toBe(false);
  });

  it('never holds two locks: a page shown while the first request waits asks nothing more', async () => {
    const sentinels: ReturnType<typeof fakeSentinel>[] = [];
    let grant: (() => void) | null = null;
    const nav = {
      wakeLock: {
        request: vi.fn(
          () =>
            new Promise<WakeSentinel>((resolve) => {
              const s = fakeSentinel();
              sentinels.push(s);
              grant = () => resolve(s);
            }),
        ),
      },
    };
    const doc = fakeDoc();
    const stop = keepScreenOn(nav, doc, () => undefined);
    doc.show(); // visibilitychange while the first request is pending
    (grant as unknown as () => void)();
    await flush();
    expect(nav.wakeLock.request).toHaveBeenCalledTimes(1); // 2 before the fix
    stop();
    expect(sentinels.every((s) => s.released)).toBe(true);
  });

  it('reports a refusal and releases a lock granted after leaving', async () => {
    const states: WakeState[] = [];
    keepScreenOn({ wakeLock: { request: () => Promise.reject(new Error('NotAllowedError')) } }, fakeDoc(), (s) => states.push(s));
    await flush();
    expect(states).toEqual(['pending', 'refused']);
    const late = fakeSentinel();
    const stop = keepScreenOn({ wakeLock: { request: async () => late } }, fakeDoc(), () => undefined);
    stop();
    await flush();
    expect(late.release).toHaveBeenCalled();
  });
});
