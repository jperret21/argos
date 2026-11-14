import { describe, expect, it, vi } from 'vitest';
import { checkAttentionItem, type AttentionItem } from '../../api/attention';
import { AttentionStore } from './attention.svelte';
import { actionOf, chipView, CRITICAL_REPEAT_S, newToneState, nextTone, openItems, prefsFrom, sortItems, TONE_GAP_S, whenLine, type SoundPrefs } from './model';
import { AlertSound, armOnGesture, TONES, type ToneContext } from './sound';

const T0 = 1_790_000_000;

function item(over: Partial<Record<string, unknown>> & { id: string }): AttentionItem {
  return checkAttentionItem({ level: 'attention', rule: 'hfd_rise', title: `title ${over.id}`, since: T0, ...over })!;
}

/** A fake AudioContext: counts oscillators and records frequencies. */
class FakeCtx implements ToneContext {
  currentTime = 0;
  state = 'suspended';
  destination = {} as AudioNode;
  oscillators: number[] = [];
  closed = false;
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  close = vi.fn(async () => {
    this.state = 'closed';
    this.closed = true;
  });
  createOscillator(): OscillatorNode {
    const freq = { value: 0 };
    const osc = {
      type: 'sine',
      frequency: freq,
      connect: (n: unknown) => n,
      start: () => this.oscillators.push(freq.value),
      stop: () => undefined,
    };
    return osc as unknown as OscillatorNode;
  }
  createGain(): GainNode {
    const g = { setValueAtTime: () => undefined, linearRampToValueAtTime: () => undefined };
    return { gain: g, connect: (n: unknown) => n } as unknown as GainNode;
  }
}

const NORMAL: SoundPrefs = { level: 'normal', info: false };

describe('attention model', () => {
  it('orders: needing the observer, then level, then active, then newest', () => {
    const items = [
      item({ id: 'info', level: 'info', since: T0 + 50 }),
      item({ id: 'att-old', since: T0 }),
      item({ id: 'crit', level: 'critical', rule: 'no_frame', since: T0 + 10 }),
      item({ id: 'att-new', since: T0 + 20 }),
      item({ id: 'acked-crit', level: 'critical', acked: true, since: T0 + 99 }),
      item({ id: 'att-cleared', since: T0 + 30, active: false }),
    ];
    expect(sortItems(items).map((a) => a.id)).toEqual(['crit', 'att-new', 'att-old', 'acked-crit', 'att-cleared', 'info']);
    // A condition cleared before anyone acknowledged it needs nobody (the server's counts.unacked).
    expect(openItems(items).map((a) => a.id)).toEqual(['crit', 'att-new', 'att-old']);
    expect(chipView(items).count).toBe(3);
  });

  it('builds the chip: level and word of the most urgent, count, headline', () => {
    expect(chipView([]).hidden).toBe(true);
    const quiet = chipView([item({ id: 'i', level: 'info' })]);
    expect(quiet).toMatchObject({ hidden: false, level: null, count: 0 });
    expect(quiet.label).toContain('nothing needs you');
    const c = chipView([item({ id: 'a', short: 'HFD 17.5 px · 2.0× baseline' }), item({ id: 'b', level: 'critical', short: 'No frame for 140 s' })]);
    expect(c).toMatchObject({ level: 'critical', count: 2, text: 'No frame for 140 s' });
    expect(c.label).toBe('Critical: No frame for 140 s · 1 more. Open the attention list');
  });

  it("uses the server's action, else the rule's default view", () => {
    expect(actionOf(item({ id: 'h' }))).toEqual({ to: 'focus', label: 'Focus mode' });
    expect(actionOf(item({ id: 'h', action: { to: 'watch', label: 'Watch' } }))).toEqual({ to: 'watch', label: 'Watch' });
    expect(actionOf(item({ id: 's', rule: 'disk' }))).toBeNull();
  });

  it('says when and which frame', () => {
    expect(whenLine(item({ id: 'x', frame: 152, since: T0 }), () => '22:16')).toBe('22:16 UTC · frame 152');
    expect(whenLine(item({ id: 'x', since: undefined }), () => '22:16')).toBe('');
  });

  it('reads the sound preferences from the config, Normal and no Info tone by default', () => {
    expect(prefsFrom(null)).toEqual({ level: 'normal', info: false });
    expect(prefsFrom({ 'alerts.sound': 'soft', 'alerts.sound_info': true })).toEqual({ level: 'soft', info: true });
    expect(prefsFrom({ 'alerts.sound': 'loud' }).level).toBe('normal');
  });
});

describe('tones: when they sound', () => {
  it('a new item sounds once; the highest level of a batch only', () => {
    const st = newToneState();
    const a = item({ id: 'a' });
    expect(nextTone([a], st, NORMAL, T0)).toBe('attention');
    expect(nextTone([a], st, NORMAL, T0 + 10)).toBeNull();
    const b = item({ id: 'b' });
    const c = item({ id: 'c', level: 'critical', rule: 'no_frame' });
    expect(nextTone([a, b, c], st, NORMAL, T0 + 20)).toBe('critical');
  });

  it('a replay never sounds, except a Critical item still open (it repeats until acknowledged)', () => {
    const st = newToneState();
    const att = item({ id: 'a' });
    expect(nextTone([att], st, NORMAL, T0, true)).toBeNull();
    const st2 = newToneState();
    const crit = item({ id: 'c', level: 'critical', rule: 'no_frame' });
    expect(nextTone([att, crit], st2, NORMAL, T0, true)).toBe('critical');
  });

  it('an open Critical item repeats every 30 s, stops once acknowledged or cleared', () => {
    const st = newToneState();
    const crit = item({ id: 'c', level: 'critical', rule: 'no_frame' });
    expect(nextTone([crit], st, NORMAL, T0)).toBe('critical');
    expect(nextTone([crit], st, NORMAL, T0 + CRITICAL_REPEAT_S - 1, true)).toBeNull();
    expect(nextTone([crit], st, NORMAL, T0 + CRITICAL_REPEAT_S, true)).toBe('critical');
    const acked = { ...crit, acked: true };
    expect(nextTone([acked], st, NORMAL, T0 + 3 * CRITICAL_REPEAT_S, true)).toBeNull();
    const st2 = newToneState();
    nextTone([crit], st2, NORMAL, T0);
    expect(nextTone([{ ...crit, active: false }], st2, NORMAL, T0 + 2 * CRITICAL_REPEAT_S, true)).toBeNull();
  });

  it('Info sounds only when asked; Off plays nothing but remembers what it heard', () => {
    const st = newToneState();
    const info = item({ id: 'i', level: 'info' });
    expect(nextTone([info], st, NORMAL, T0)).toBeNull();
    expect(nextTone([item({ id: 'j', level: 'info' })], newToneState(), { level: 'soft', info: true }, T0)).toBe('info');
    const off = newToneState();
    const a = item({ id: 'a' });
    expect(nextTone([a], off, { level: 'off', info: false }, T0)).toBeNull();
    expect(nextTone([a], off, NORMAL, T0 + 5)).toBeNull();
  });

  it('a burst within 2 s sounds once, but a more urgent level is never held back', () => {
    const st = newToneState();
    expect(nextTone([item({ id: 'a' })], st, NORMAL, T0)).toBe('attention');
    expect(nextTone([item({ id: 'a' }), item({ id: 'b' })], st, NORMAL, T0 + 1)).toBeNull();
    const crit = item({ id: 'c', level: 'critical', rule: 'no_frame' });
    expect(nextTone([item({ id: 'a' }), item({ id: 'b' }), crit], st, NORMAL, T0 + 1.5)).toBe('critical');
    expect(nextTone([item({ id: 'd' })], st, NORMAL, T0 + 1.5 + TONE_GAP_S)).toBe('attention');
  });
});

describe('AlertSound', () => {
  it('plays nothing before a gesture armed it, then 3 / 2 / 1 notes per level, Off none', () => {
    const ctx = new FakeCtx();
    const factory = vi.fn(() => ctx);
    const s = new AlertSound(factory);
    expect(s.play('critical', 'normal')).toBe(false);
    expect(s.arm()).toBe(true);
    expect(s.arm()).toBe(true);
    expect(factory).toHaveBeenCalledTimes(1); // one AudioContext
    expect(s.play('critical', 'normal')).toBe(true);
    expect(s.play('attention', 'soft')).toBe(true);
    expect(s.play('info', 'normal')).toBe(true);
    expect(s.play('attention', 'off')).toBe(false);
    expect(ctx.oscillators).toEqual([...TONES.critical, ...TONES.attention, ...TONES.info].map((n) => n[1]));
    s.dispose();
    expect(ctx.closed).toBe(true);
    expect(s.play('info', 'normal')).toBe(false);
  });

  it('a context suspended by the OS plays nothing and is asked to resume', () => {
    const ctx = new FakeCtx();
    const s = new AlertSound(() => ctx);
    s.arm();
    expect(s.play('critical', 'normal')).toBe(true);
    ctx.state = 'interrupted'; // WebKit; Chromium says 'suspended'
    ctx.resume.mockClear();
    const before = ctx.oscillators.length;
    expect(s.play('critical', 'normal')).toBe(false); // true, and nothing heard, before the fix
    expect(ctx.oscillators.length).toBe(before);
    expect(ctx.resume).toHaveBeenCalledTimes(1);
    expect(s.armed).toBe(true); // the fake resumes at once
  });

  it('says when Web Audio is missing', () => {
    const s = new AlertSound(() => {
      throw new Error('no audio');
    });
    expect(s.arm()).toBe(false);
    expect(s.unavailable).toBe(true);
  });

  it('arms on the first press or key, then stops listening', () => {
    const listeners = new Map<string, EventListenerOrEventListenerObject>();
    const target = {
      addEventListener: (t: string, fn: EventListenerOrEventListenerObject) => listeners.set(t, fn),
      removeEventListener: (t: string) => listeners.delete(t),
    };
    const ctx = new FakeCtx();
    const s = new AlertSound(() => ctx);
    armOnGesture(s, target);
    expect([...listeners.keys()].sort()).toEqual(['keydown', 'pointerdown']);
    (listeners.get('pointerdown') as () => void)();
    expect(listeners.size).toBe(0);
    expect(ctx.resume).toHaveBeenCalled();
  });
});

describe('AttentionStore', () => {
  function setup(answer: unknown = { active: [], history: [] }) {
    const handlers = new Map<string, (m: Record<string, unknown>) => void>();
    const events = { on: (t: string, fn: (m: Record<string, unknown>) => void) => (handlers.set(t, fn), () => handlers.delete(t)) };
    const calls: string[] = [];
    const client = {
      request: async <T,>(method: string, path: string): Promise<T> => {
        calls.push(`${method} ${path}`);
        if (method === 'GET') return answer as T;
        const id = decodeURIComponent(path.split('/')[3]);
        return { active: [{ id, level: 'attention', rule: 'hfd_rise', title: 'HFD', acked: true, acked_by: 'me' }], history: [], revision: 9 } as T;
      },
    };
    const ctx = new FakeCtx();
    ctx.state = 'running';
    let now = T0;
    const sound = new AlertSound(() => ctx);
    sound.arm();
    const store = new AttentionStore({ sound, clock: () => now });
    store.attach(events, client);
    return { store, handlers, calls, ctx, advance: (s: number) => (now += s) };
  }

  it('a client joining mid-run reads the list and history quietly, then sounds what happens next', async () => {
    const { store, handlers, ctx } = setup({ active: [{ id: 'a', level: 'attention', rule: 'hfd_rise', title: 'HFD', since_utc: '2026-09-25T22:16:14Z' }], history: [{ id: 'i', level: 'info', rule: 'run_started', title: 'Run started' }] });
    await store.refresh();
    expect(store.items.map((a) => a.id)).toEqual(['a', 'i']);
    expect(store.chip.count).toBe(1);
    expect(ctx.oscillators).toHaveLength(0);
    handlers.get('attention')!({ type: 'attention', item: { id: 'b', level: 'attention', rule: 'star_count_drop', title: 'Stars', since_utc: '2026-09-25T22:30:00Z' } });
    expect(ctx.oscillators).toHaveLength(TONES.attention.length);
    expect(store.lastTone?.level).toBe('attention');
    expect(store.top?.id).toBe('b');
  });

  it('acknowledges through the server; the shared answer updates the list', async () => {
    const { store, handlers, calls } = setup();
    handlers.get('attention')!({ type: 'attention', items: [{ id: 'a', level: 'attention', rule: 'hfd_rise', title: 'HFD' }] });
    expect(store.open).toHaveLength(1);
    await store.ack('a');
    expect(calls).toContain('POST /api/attention/a/ack');
    expect(store.open).toHaveLength(0);
    expect(store.items[0].ackedBy).toBe('me');
    expect(store.pending.size).toBe(0);
  });

  it('keeps the refusal in words', async () => {
    const { store, handlers } = setup();
    handlers.get('attention')!({ type: 'attention', items: [{ id: 'a', level: 'attention', rule: 'r', title: 'T' }] });
    (store as unknown as { client: { request: () => Promise<never> } }).client = { request: () => Promise.reject(new Error('Unknown attention item')) };
    await expect(store.ack('a')).rejects.toThrow('Unknown attention item');
    expect(store.error).toBe('Unknown attention item');
  });

  it('repeats an open Critical item every 30 s from its timer check', () => {
    const { store, handlers, ctx, advance } = setup();
    handlers.get('attention')!({ type: 'attention', items: [] });
    handlers.get('attention')!({ type: 'attention', item: { id: 'c', level: 'critical', rule: 'no_frame', title: 'No new frame for 140 s' } });
    const n = TONES.critical.length;
    expect(ctx.oscillators).toHaveLength(n);
    advance(10);
    store.tick();
    expect(ctx.oscillators).toHaveLength(n);
    advance(25);
    store.tick();
    expect(ctx.oscillators).toHaveLength(2 * n);
  });

  it('sounds a new item of a snapshot, drops an older snapshot, and a reopened item sounds again', () => {
    const { store, handlers, ctx, advance } = setup();
    const a = { id: 'a', level: 'attention', rule: 'hfd_rise', title: 'HFD' };
    handlers.get('attention')!({ type: 'attention', active: [a], history: [], revision: 1 });
    expect(ctx.oscillators).toHaveLength(0); // the first snapshot after connecting is a replay
    const b = { id: 'b', level: 'attention', rule: 'star_drop', title: 'Stars', since_utc: '2026-09-25T22:30:00Z' };
    handlers.get('attention')!({ type: 'attention', active: [a, b], history: [], revision: 2 });
    expect(ctx.oscillators).toHaveLength(TONES.attention.length);
    expect(store.ingest({ type: 'attention', active: [a], history: [], revision: 1 })).toBe(false);
    expect(store.items).toHaveLength(2);
    // The same cause fires again soon after its clear: the server reopens the item.
    advance(60);
    handlers.get('attention')!({ type: 'attention', active: [{ ...a, occurrences: 2 }, b], history: [], revision: 3 });
    expect(ctx.oscillators).toHaveLength(2 * TONES.attention.length);
  });

  it('a condition cleared before anyone acknowledged it needs nobody (the server moved it to the history)', () => {
    const { store, handlers, ctx } = setup();
    // protocol.md AttentionState: the HFD rise cleared (`resolved`), never acknowledged.
    const base = { run_id: 'r1', kind: 'condition', acked: false, acked_utc: null, acked_by: null, occurrences: 1, sound: true, repeat_s: null };
    const hfd = { ...base, id: 'hfd_rise-r1-3', rule: 'hfd_rise', cause: 'hfd_rise:TG', name: 'HFD rise', level: 'attention', title: 'HFD 17.0 px = 2.0× the first 20 frames', short: 'HFD 17.0 px · 2.0× baseline', since: '2026-09-25T22:12:46Z', frame: 150 };
    handlers.get('attention')!({ type: 'attention', active: [{ ...hfd, active: true, cleared_utc: null, cleared_reason: null }], history: [], counts: { critical: 0, attention: 1, info: 0, unacked: 1 }, revision: 4 });
    expect(store.chip.count).toBe(1);
    handlers.get('attention')!({ type: 'attention', active: [], history: [{ ...hfd, active: false, cleared_utc: '2026-09-25T22:30:00Z', cleared_reason: 'resolved' }], counts: { critical: 0, attention: 0, info: 0, unacked: 0 }, revision: 5 });
    expect(store.open).toHaveLength(0);
    expect(store.top).toBeNull();
    expect(store.chip).toMatchObject({ hidden: false, level: null, count: 0 });
    expect(store.items[0].clearedReason).toBe('resolved');
    expect(ctx.oscillators).toHaveLength(0);
  });

  it("follows the server's sound flag and repeat (0: once)", () => {
    const { store, handlers, ctx, advance } = setup();
    handlers.get('attention')!({ type: 'attention', active: [], revision: 1 });
    handlers.get('attention')!({ type: 'attention', active: [{ id: 'q', level: 'attention', rule: 'r', title: 'T', sound: false }], revision: 2 });
    expect(ctx.oscillators).toHaveLength(0);
    handlers.get('attention')!({ type: 'attention', active: [{ id: 'c', level: 'critical', rule: 'no_frame', title: 'No frame', repeat_s: 0 }], revision: 3 });
    expect(ctx.oscillators).toHaveLength(TONES.critical.length);
    advance(120);
    store.tick();
    expect(ctx.oscillators).toHaveLength(TONES.critical.length);
  });

  it("takes the snapshot's sound settings until the config's are set", () => {
    const { store, handlers } = setup();
    handlers.get('attention')!({ type: 'attention', active: [], sound: { level: 'soft', info: true, repeat_s: 60 }, revision: 1 });
    expect(store.prefs).toEqual({ level: 'soft', info: true, repeatS: 60 });
    store.setPrefs({ level: 'off', info: false });
    handlers.get('attention')!({ type: 'attention', active: [], sound: { level: 'normal', info: false, repeat_s: 30 }, revision: 2 });
    expect(store.prefs.level).toBe('off');
  });

  it('acknowledges everything at once', async () => {
    const { store, handlers, calls } = setup();
    handlers.get('attention')!({ type: 'attention', active: [{ id: 'a', level: 'attention', rule: 'r', title: 'T' }, { id: 'b', level: 'critical', rule: 'no_frame', title: 'N' }] });
    (store as unknown as { client: unknown }).client = {
      request: async (m: string, p: string) => (calls.push(`${m} ${p}`), { active: [], history: [], revision: 2 }),
    };
    await store.ackAll();
    expect(calls).toContain('POST /api/attention/ack-all');
    expect(store.open).toHaveLength(0);
  });

  it('reads the list carried by a status record as a replay', () => {
    const { store, handlers, ctx } = setup();
    handlers.get('status')!({ type: 'status', attention: { active: [{ id: 'a', level: 'attention', rule: 'r', title: 'T' }] } });
    expect(store.items).toHaveLength(1);
    expect(ctx.oscillators).toHaveLength(0);
  });

  it('marks an older server (no route) as unsupported', async () => {
    const { store } = setup();
    (store as unknown as { client: unknown }).client = { request: () => Promise.reject(Object.assign(new Error('Not found'), { status: 404 })) };
    await store.refresh();
    expect(store.supported).toBe(false);
  });
});
