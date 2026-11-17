import { describe, expect, it } from 'vitest';
import { settledSlot, wheelBusy, wheelLine, wheelMode, wheelOptions, wheelReason } from './filterwheel';
import {
  afFramesText,
  afReference,
  autofocusProgress,
  commandedTarget,
  commandText,
  driftSinceAf,
  focuserBadge,
  focuserLine,
  manualReason,
  queuedDelta,
  queuedText,
  stepReason,
  TapQueue,
  travelText,
} from './focuser';
import {
  DEADMAN_MS,
  deadmanExpired,
  directionOf,
  directionOfKey,
  JogDriver,
  JogHolds,
  keyWords,
  OWN_STOP_ECHO_MS,
  rateDeg,
  RENEW_MS,
  reportedMoving,
  STOP_RETRIES,
  stoppedAxes,
  type JogTimers,
  type JogTransport,
} from './jog';
import type { AutofocusView, FilterWheelView, FocuserView, MountJogView } from './types';

// -- Jog ------------------------------------------------------------------------------------------

describe('jog holds (H3: every axis on its own)', () => {
  it('tracks the two axes separately: a diagonal, then one axis released', () => {
    const h = new JogHolds();
    h.press('key:ArrowUp', 'north');
    h.press('key:ArrowRight', 'east');
    expect(h.sign('secondary')).toBe(1);
    expect(h.sign('primary')).toBe(1);
    h.release('key:ArrowUp');
    expect(h.sign('secondary')).toBe(0);
    expect(h.sign('primary')).toBe(1);
  });

  it('the newest press of an axis wins, and its release falls back to the other direction', () => {
    const h = new JogHolds();
    h.press('key:ArrowUp', 'north');
    h.press('pointer:south', 'south');
    expect(h.active('secondary')).toBe('south');
    h.release('pointer:south');
    expect(h.active('secondary')).toBe('north');
    h.releaseAll();
    expect(h.empty).toBe(true);
  });

  it('maps keys, directions and the server report', () => {
    expect(directionOfKey('ArrowLeft')).toBe('west');
    expect(directionOfKey('j')).toBeNull();
    expect(directionOf('primary', -2)).toBe('west');
    expect(directionOf('secondary', 0)).toBeNull();
    const r: MountJogView = { primary: -2, secondary: 0 };
    expect(reportedMoving(r, 'west')).toBe(true);
    expect(reportedMoving(r, 'east')).toBe(false);
    expect(reportedMoving(r, 'north')).toBe(false);
    expect(stoppedAxes('primary')).toEqual(['primary']);
    expect(stoppedAxes('both')).toEqual(['primary', 'secondary']);
  });

  it('words follow the geometry (Q-O4): axis words on alt-az and unknown, compass letters on EQ', () => {
    expect(keyWords('altaz').north).toEqual({ short: 'Alt+', label: 'Altitude +' });
    expect(keyWords('altaz').west.short).toBe('Az−');
    expect(keyWords(null).east.short).toBe('Az+');
    expect(keyWords('eq').north).toEqual({ short: 'N', label: 'North' });
    expect(keyWords('eq_gem').west.short).toBe('W');
  });

  it('rates are the Qt speeds, never above the server limit; the dead-man is 1 s', () => {
    expect(rateDeg('slow')).toBe(0.5);
    expect(rateDeg('normal')).toBe(2);
    expect(rateDeg('fast')).toBe(5);
    expect(rateDeg('fast', 3)).toBe(3);
    expect(RENEW_MS).toBe(250);
    expect(DEADMAN_MS).toBe(1000);
    expect(deadmanExpired(0, 1000)).toBe(false);
    expect(deadmanExpired(0, 1001)).toBe(true);
  });
});

/** A fake server and clock: every call recorded, answers settled by the test. */
function rig() {
  const calls: { kind: 'start' | 'stop' | 'socket'; axis: string | null; rate?: number; seq?: number }[] = [];
  const pending: { resolve: () => void; reject: (e: Error) => void }[] = [];
  let auto: 'ok' | 'fail' | 'hold' = 'ok';
  const answer = () =>
    new Promise<void>((resolve, reject) => {
      if (auto === 'ok') resolve();
      else if (auto === 'fail') reject(new Error('Mount is parked'));
      else pending.push({ resolve, reject });
    });
  const transport: JogTransport = {
    start: (axis, rate, seq) => {
      calls.push({ kind: 'start', axis, rate, seq });
      return answer();
    },
    stop: (axis, seq) => {
      calls.push({ kind: 'stop', axis, seq });
      return answer();
    },
    socketStop: () => calls.push({ kind: 'socket', axis: null }),
  };
  let t = 0;
  let intervals: { fn: () => void; ms: number; next: number; id: number }[] = [];
  let timeouts: { fn: () => void; at: number }[] = [];
  let ids = 0;
  const timers: JogTimers = {
    now: () => t,
    setInterval: (fn, ms) => {
      const id = ++ids;
      intervals.push({ fn, ms, next: t + ms, id });
      return id;
    },
    clearInterval: (id) => {
      intervals = intervals.filter((i) => i.id !== id);
    },
    setTimeout: (fn, ms) => {
      timeouts.push({ fn, at: t + ms });
      return 0;
    },
  };
  const advance = async (ms: number) => {
    const end = t + ms;
    await flush(); // settle the answers already given: they may schedule timers
    for (;;) {
      const nextI = intervals.length ? Math.min(...intervals.map((i) => i.next)) : Infinity;
      const nextT = timeouts.length ? Math.min(...timeouts.map((x) => x.at)) : Infinity;
      const next = Math.min(nextI, nextT);
      if (next > end) break;
      t = next;
      for (const i of intervals.filter((x) => x.next === next)) {
        i.next += i.ms;
        i.fn();
      }
      const due = timeouts.filter((x) => x.at === next);
      timeouts = timeouts.filter((x) => x.at !== next);
      for (const x of due) x.fn();
      await flush();
    }
    t = end;
    await flush();
  };
  return {
    calls,
    pending,
    transport,
    timers,
    advance,
    setAuto: (a: typeof auto) => (auto = a),
    get intervals() {
      return intervals.length;
    },
  };
}
const flush = () => new Promise<void>((r) => setTimeout(r, 0));

describe('JogDriver (client side of the dead-man, A30)', () => {
  it('starts one axis per press, renews it every 250 ms with increasing seq, stops it on release', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.rate = 2;
    d.press('key:ArrowUp', 'north');
    expect(r.calls).toEqual([{ kind: 'start', axis: 'secondary', rate: 2, seq: 1 }]);
    await r.advance(760);
    const renewals = r.calls.filter((c) => c.kind === 'start');
    expect(renewals.length).toBe(4); // the start + 3 renewals at 250, 500, 750
    expect(renewals.map((c) => c.seq)).toEqual([1, 2, 3, 4]);
    expect(d.renewalAge()).toBe(10);
    d.release('key:ArrowUp');
    expect(r.calls.at(-1)).toEqual({ kind: 'stop', axis: 'secondary', seq: 5 });
    expect(d.moving).toBe(false);
    expect(r.intervals).toBe(0);
    await r.advance(1000);
    expect(r.calls.length).toBe(5); // nothing renewed after the stop
  });

  it('a diagonal moves both axes; releasing one stops only that one (H3)', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.rate = 5;
    d.press('key:ArrowUp', 'north');
    d.press('key:ArrowLeft', 'west');
    expect(d.sent).toEqual({ primary: -5, secondary: 5 });
    d.release('key:ArrowUp');
    expect(r.calls.at(-1)).toMatchObject({ kind: 'stop', axis: 'secondary' });
    expect(d.sent).toEqual({ primary: -5, secondary: 0 });
    await r.advance(260);
    expect(r.calls.at(-1)).toMatchObject({ kind: 'start', axis: 'primary', rate: -5 });
  });

  it('a rate change re-commands the axes moving now', () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('pointer:east', 'east');
    d.setRate(0.5);
    expect(r.calls.at(-1)).toMatchObject({ kind: 'start', axis: 'primary', rate: 0.5 });
  });

  it('blur, a hidden tab and a lost socket stop both axes, also through the socket message', () => {
    for (const reason of ['blur', 'hidden', 'socket'] as const) {
      const r = rig();
      const d = new JogDriver(r.transport, () => {}, r.timers);
      d.press('key:ArrowUp', 'north');
      d.press('key:ArrowRight', 'east');
      d.stopAll(reason);
      expect(r.calls.slice(-2)).toEqual([
        { kind: 'socket', axis: null },
        { kind: 'stop', axis: null, seq: 3 },
      ]);
      expect(d.holds.empty).toBe(true);
      expect(d.moving).toBe(false);
    }
  });

  it('the stop button stops both axes whatever is believed; an idle blur sends nothing', () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.stopAll('blur');
    expect(r.calls).toEqual([]);
    d.stopAll('button');
    expect(r.calls).toEqual([{ kind: 'stop', axis: null, seq: 1 }]);
  });

  it('retries a stop that was not delivered, then says to use Abort', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    r.setAuto('fail');
    d.release('key:ArrowUp');
    await r.advance(2000);
    const stops = r.calls.filter((c) => c.kind === 'stop');
    expect(stops.length).toBe(STOP_RETRIES);
    expect(d.messageKind).toBe('error');
    expect(d.message).toContain('use Abort on the Mount card');
  });

  it('a retry never stops a jog restarted meanwhile', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    r.setAuto('fail');
    d.release('key:ArrowUp');
    await flush();
    r.setAuto('ok');
    d.press('key:ArrowUp', 'north');
    await r.advance(1000);
    expect(r.calls.filter((c) => c.kind === 'stop').length).toBe(1);
    expect(d.sent.secondary).toBe(2);
  });

  it('a refused start is not resent by the renewals; the key is stalled until released', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    r.setAuto('fail');
    d.press('key:ArrowUp', 'north');
    await flush();
    expect(d.stalled.secondary).toBe(2);
    expect(d.message).toBe('Jog refused: Mount is parked');
    await r.advance(1000);
    expect(r.calls.length).toBe(1);
    d.release('key:ArrowUp');
    r.setAuto('ok');
    d.press('key:ArrowUp', 'north');
    expect(r.calls.at(-1)).toMatchObject({ kind: 'start', axis: 'secondary' });
  });

  it('an axis the server stopped while held (dead-man, Abort) is not restarted by the next renewal', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.observe({ primary: 0, secondary: 0, last_stop: null }); // baseline
    d.press('key:ArrowUp', 'north');
    await r.advance(OWN_STOP_ECHO_MS + 100);
    const before = r.calls.length;
    d.observe({ primary: 0, secondary: 0, last_stop: { axis: 'secondary', reason: 'Abort', t: '2026-11-08T21:00:01Z' } });
    expect(d.stalled.secondary).toBe(2);
    expect(d.sent.secondary).toBe(0);
    expect(d.message).toContain('Jog stopped by the server: Abort');
    await r.advance(1000);
    expect(r.calls.length).toBe(before);
  });

  it('the echo of its own recent stop does not stall a new press', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.observe({ primary: 0, secondary: 0, last_stop: null });
    d.press('key:ArrowUp', 'north');
    d.release('key:ArrowUp');
    d.press('key:ArrowUp', 'north');
    d.observe({ primary: 0, secondary: 0, last_stop: { axis: 'secondary', reason: 'client', t: 'x' } });
    expect(d.stalled.secondary).toBe(0);
    expect(d.sent.secondary).toBe(2);
  });

  it('the renewal age grows when renewals are not answered (the meter drains)', async () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    await flush();
    r.setAuto('hold');
    await r.advance(900);
    expect(d.renewalAge()).toBe(900);
    expect(deadmanExpired(r.timers.now() - (d.renewalAge() ?? 0), r.timers.now() + 200)).toBe(true);
  });

  it('dispose stops what moves and the timer', () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    d.dispose();
    expect(r.calls.at(-1)).toMatchObject({ kind: 'stop', axis: null });
    expect(r.intervals).toBe(0);
    d.press('key:ArrowUp', 'north');
    expect(d.moving).toBe(false);
  });
});

// -- Focuser ----------------------------------------------------------------------------------------

const idle: FocuserView = { state: 'idle', position: 12_450, target: 12_450, queued: null, max_step: 100_000, temperature_c: 12.3 };
const movingF: FocuserView = { state: 'moving', position: 12_100, target: 12_450, queued: 12_750, max_step: 100_000 };
const afRun: AutofocusView = { state: 'running', stage: 'fine', step: 7, total: 14, start_position: 12_450, samples: [{ position: 12_300, hfd_px: 3.42 }] };

describe('focuser rules (H10, D9, S23)', () => {
  it('steps add to the queued target, then the move in progress, then the position', () => {
    expect(commandedTarget(idle)).toBe(12_450);
    expect(commandedTarget(movingF)).toBe(12_750);
    expect(commandedTarget({ state: 'idle', position: 10 })).toBe(10);
    expect(queuedDelta(movingF)).toBe(300);
    expect(queuedDelta(movingF, 100)).toBe(400);
    expect(queuedDelta(idle)).toBe(0);
    expect(queuedText(300)).toBe('+300 queued');
    expect(queuedText(-1000)).toBe('−1 000 queued');
    expect(queuedText(0)).toBe('');
  });

  it('manual motion is refused offline and while autofocus owns the focuser (H10)', () => {
    expect(manualReason({ state: 'disconnected', position: null })).toBe('Connect the focuser first');
    expect(manualReason(idle)).toBeNull();
    expect(manualReason({ ...idle, locked_by: 'autofocus' })).toBe('Autofocus owns the focuser');
    expect(manualReason(idle, afRun)).toBe('Autofocus owns the focuser');
    expect(manualReason(idle, { state: 'stopping' })).toBe('Autofocus is returning the focuser to its start');
    expect(manualReason(idle, { state: 'done' })).toBeNull();
    expect(manualReason({ ...idle, state: 'error', message: 'Focuser not responding' })).toBe('Focuser not responding');
  });

  it('a step is refused only at the travel end; past it the server clamps and says so', () => {
    expect(stepReason(-1, { ...idle, position: 0, target: 0 })).toBe('At the travel limit 0');
    expect(stepReason(-1, { ...idle, position: 50, target: 50 })).toBeNull();
    expect(stepReason(1, { ...idle, position: 100_000, target: 100_000 })).toBe('At the travel limit 100 000 (MaxStep)');
    expect(stepReason(1, { ...idle, position: 99_900, target: 99_900 }, null, 100)).toBe('At the travel limit 100 000 (MaxStep)');
    expect(stepReason(1, idle, afRun)).toBe('Autofocus owns the focuser');
    expect(commandText({ requested: 0, sent: 0, clamped: true, queued: false }, 100_000)).toBe('Clamped to 0: the end of the travel (MaxStep)');
    expect(commandText({ requested: 100_000, sent: 100_000, clamped: true, queued: false }, 100_000)).toBe(
      'Clamped to 100 000: the end of the travel (MaxStep)',
    );
    expect(commandText({ requested: 12_750, sent: null, clamped: false, queued: true })).toBe('Queued: to 12 750 when the move in progress ends');
    expect(commandText({ requested: 12_750, sent: 12_750, clamped: false, queued: false })).toBeNull();
    expect(travelText(idle)).toBe('0–100 000');
    expect(travelText({ state: 'idle', position: 1 })).toBe('0–?');
  });

  it('the badge names what drives the focuser, with a word', () => {
    expect(focuserBadge({ state: 'disconnected', position: null })).toEqual({ tone: 'idle', label: 'Offline' });
    expect(focuserBadge(idle)).toEqual({ tone: 'ok', label: 'Ready' });
    expect(focuserBadge(movingF)).toEqual({ tone: 'busy', label: 'Moving' });
    expect(focuserBadge(idle, afRun)).toEqual({ tone: 'active', label: 'Autofocus' });
    expect(focuserBadge(idle, { state: 'stopping' })).toEqual({ tone: 'busy', label: 'Returning' });
    expect(focuserBadge(idle, { state: 'rejected' }).label).toBe('Rejected');
    expect(focuserBadge({ ...idle, state: 'error' }).tone).toBe('error');
  });

  it('the line says what autofocus does, and only "done" reads as a success (P43)', () => {
    expect(autofocusProgress(afRun)).toBe(0.5);
    expect(autofocusProgress({ state: 'done' })).toBeNull();
    expect(focuserLine(idle, afRun).text).toBe('Autofocus fine sweep: the focuser moves on its own. Stop AF returns it to its start.');
    expect(focuserLine(idle, { state: 'stopping', start_position: 12_450 }).text).toBe('Stopping autofocus: returning to 12 450…');
    expect(
      focuserLine(idle, { state: 'done', best: { position: 12_380, hfd_px: 3.1, method: 'parabola' } }).text,
    ).toBe('Best focus 3.10 px at 12 380 · parabola · measured');
    expect(focuserLine(idle, { state: 'rejected', message: 'Flat HFD curve: focus unchanged' })).toEqual({
      kind: 'reason',
      text: 'Flat HFD curve: focus unchanged',
    });
    expect(focuserLine(idle, { state: 'cancelled', message: 'Returned to 12450.' }).text).toBe('Returned to 12450.');
    expect(focuserLine(idle, { state: 'failed', message: 'Camera timeout' })).toEqual({ kind: 'bad', text: 'Camera timeout' });
    expect(focuserLine(idle, null, { lastError: 'Position 120000 is outside 0–100000' }).kind).toBe('bad');
    expect(focuserLine(idle, null, { frames: { exposure_s: 2, gain: 80 } })).toEqual({ kind: 'muted', text: 'AF frames: 2.0 s, gain 80' });
    expect(afFramesText(null)).toBe('Autofocus frames: exposure and gain of the Camera card');
  });

  it('remembers the temperature of the last finished autofocus once per run', () => {
    const done: AutofocusView = { state: 'done', run: 3 };
    const a = afReference(null, done, { ...idle, temperature_c: 14.1 });
    expect(a).toEqual({ run: 3, temperature_c: 14.1 });
    expect(afReference(a, done, { ...idle, temperature_c: 12 })).toBe(a);
    expect(afReference(a, { state: 'done', run: 4 }, { ...idle, temperature_c: 12 })).toEqual({ run: 4, temperature_c: 12 });
    expect(afReference(a, afRun, idle)).toBe(a);
    expect(driftSinceAf(12.3, 14.1)).toBeCloseTo(-1.8);
    expect(driftSinceAf(null, 14.1)).toBeNull();
  });
});

describe('TapQueue (D9: one request at a time, taps coalesced)', () => {
  it('sends the first tap, then the taps made meanwhile as one step', async () => {
    const sent: number[] = [];
    let release: () => void = () => {};
    const q = new TapQueue((d) => {
      sent.push(d);
      return new Promise<void>((r) => (release = r));
    });
    q.tap(100);
    q.tap(100);
    q.tap(100);
    expect(sent).toEqual([100]);
    expect(q.unsent).toBe(300);
    release();
    await flush();
    expect(sent).toEqual([100, 200]);
    release();
    await flush();
    expect(q.unsent).toBe(0);
    expect(q.busy).toBe(false);
  });

  it('a refused step drops the taps behind it and reports the refusal; Halt clears the queue', async () => {
    const errors: unknown[] = [];
    let reject: (e: Error) => void = () => {};
    const q = new TapQueue(
      () => new Promise((_, rj) => (reject = rj)),
      () => {},
      () => {},
      (e) => errors.push(e),
    );
    q.tap(-50);
    q.tap(-50);
    reject(new Error('Autofocus owns the focuser.'));
    await flush();
    expect(errors.length).toBe(1);
    expect(q.unsent).toBe(0);
    q.clear();
    expect(q.pending).toBe(0);
  });
});

// -- Filter wheel ------------------------------------------------------------------------------------

describe('filter wheel (H9, S1, Q-O5)', () => {
  const wheel: FilterWheelView = { state: 'idle', slots: ['Dark', 'IR', 'LP'], dark_slot: true, position: 1, slot: 'IR' };

  it('shows the slot the wheel reports, never the one asked for', () => {
    expect(settledSlot(wheel)).toBe('IR');
    expect(settledSlot({ ...wheel, slot: null, position: 2 })).toBe('LP');
    expect(settledSlot({ ...wheel, state: 'moving', target: 'Dark', position: null, slot: null })).toBeNull();
    expect(settledSlot({ ...wheel, slot: null, position: null })).toBeNull();
    expect(wheelOptions(wheel.slots).map((o) => o.value)).toEqual(['Dark', 'IR', 'LP']);
  });

  it('spins the requested slot while turning; says why a choice is refused', () => {
    expect(wheelBusy({ ...wheel, state: 'moving', target: 'Dark' })).toBe('Dark');
    expect(wheelBusy(wheel)).toBeNull();
    expect(wheelReason(wheel, { cameraOwner: 'autofocus' })).toBe('Autofocus owns the camera');
    expect(wheelReason(wheel, { cameraOwner: 'sequence' })).toBe('The sequence owns the camera');
    expect(wheelReason(wheel, { cameraOwner: 'live' })).toBeNull();
  });

  it('a refused move says so and where the wheel really is (H9); an unknown position says so', () => {
    expect(wheelLine(wheel)).toBeNull();
    expect(wheelLine({ ...wheel, state: 'moving', target: 'Dark' })).toEqual({ kind: 'plain', text: 'Turning to Dark…' });
    expect(wheelLine({ ...wheel, message: 'Move refused by the driver.' })).toEqual({
      kind: 'reason',
      text: 'Move refused by the driver. The wheel is on IR.',
    });
    expect(wheelLine({ ...wheel, state: 'error', position: null, slot: null, message: 'Still turning after 20 s: position unknown' })).toEqual({
      kind: 'bad',
      text: 'Still turning after 20 s: position unknown',
    });
    expect(wheelLine({ ...wheel, position: null, slot: null })?.kind).toBe('reason');
  });

  it('without a wheel the slot is FITS metadata only', () => {
    const none: FilterWheelView = { state: 'disconnected', slots: ['Dark', 'IR', 'LP'], position: null };
    expect(wheelMode(none)).toBe('metadata');
    expect(wheelMode(null)).toBe('metadata');
    expect(wheelMode(wheel)).toBe('wheel');
    expect(wheelLine(none, 'LP')).toEqual({ kind: 'muted', text: 'No filter wheel: ‘LP’ is written to FITS FILTER only' });
    expect(wheelReason({ state: 'disconnected', slots: [], position: null })).toBe('No filter slots in the active profile');
  });
});

describe('JogDriver against the server admission rules (review of wave 3)', () => {
  it('takes its numbers from the page counter, so a remounted pad never restarts at 0', () => {
    let counter = 0;
    const seqs: number[] = [];
    const transport: JogTransport = {
      nextSeq: () => ++counter,
      start: (_a, _r, seq) => (seqs.push(seq), Promise.resolve()),
      stop: (_a, seq) => (seqs.push(seq), Promise.resolve()),
    };
    const first = new JogDriver(transport);
    first.press('key:ArrowUp', 'north');
    first.release('key:ArrowUp');
    first.dispose();
    const second = new JogDriver(transport); // the pad was closed and opened again
    second.press('key:ArrowUp', 'north');
    expect(seqs).toEqual([1, 2, 3]);
    second.dispose();
  });

  it('never queues a renewal behind an unanswered request of the same axis', async () => {
    const r = rig();
    r.setAuto('hold');
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowRight', 'east');
    await r.advance(800); // a slow mount: the start is still unanswered
    expect(r.calls.filter((c) => c.kind === 'start').length).toBe(1);
    r.pending.shift()?.resolve();
    r.setAuto('ok');
    await r.advance(260);
    expect(r.calls.filter((c) => c.kind === 'start').length).toBe(2);
    d.dispose();
  });

  it('a renewal the server ignores because it stopped the axis stalls it, and the meter is not refreshed', async () => {
    const r = rig();
    let n = 0;
    const transport: JogTransport = {
      ...r.transport,
      start: (axis, rate, seq, renew) => {
        r.calls.push({ kind: 'start', axis, rate, seq });
        n += 1;
        return Promise.resolve(renew && n > 1 ? { jog_command: { outcome: 'ignored', why: 'stopped' } } : { jog_command: { outcome: 'started', why: null } });
      },
    };
    const d = new JogDriver(transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    await r.advance(260);
    expect(d.sent.secondary).toBe(0);
    expect(d.stalled.secondary).toBe(2);
    expect(d.message).toMatch(/stopped by the server/);
    await r.advance(1000);
    expect(r.calls.filter((c) => c.kind === 'start').length).toBe(2); // nothing more sent
  });

  it('a start dropped as late (it waited behind a slow mount) is sent again once', async () => {
    const r = rig();
    let n = 0;
    const transport: JogTransport = {
      ...r.transport,
      start: (axis, rate, seq) => {
        r.calls.push({ kind: 'start', axis, rate, seq });
        n += 1;
        return Promise.resolve(n === 1 ? { jog_command: { outcome: 'ignored', why: 'late' } } : { jog_command: { outcome: 'started', why: null } });
      },
    };
    const d = new JogDriver(transport, () => {}, r.timers);
    d.press('key:ArrowLeft', 'west');
    await r.advance(10);
    expect(r.calls.filter((c) => c.kind === 'start').map((c) => c.seq)).toEqual([1, 2]);
    expect(d.sent.primary).toBe(-2);
    d.dispose();
  });

  it('releaseKeys (Cmd pressed on macOS) releases every arrow hold but not a pointer hold', () => {
    const r = rig();
    const d = new JogDriver(r.transport, () => {}, r.timers);
    d.press('key:ArrowUp', 'north');
    d.press('pointer:east', 'east');
    d.releaseKeys();
    expect(d.sent).toEqual({ primary: 2, secondary: 0 });
    expect(r.calls.at(-1)).toMatchObject({ kind: 'stop', axis: 'secondary' });
    d.dispose();
  });
});

describe('jog offset readout in the mount frame (review of wave 3)', () => {
  it('words ΔRA as time and ΔDec in arcmin, and grows the scope scale', async () => {
    const { formatDeltaRA, formatDeltaDec, scopeRange, isEquatorial } = await import('./jog');
    expect(formatDeltaRA(12.4 / 3600)).toBe('+12.4s');
    expect(formatDeltaRA(-185 / 3600)).toBe('−3m05s');
    expect(formatDeltaRA(68 / 60)).toBe('+1h08m');
    expect(formatDeltaDec(3.2 / 60)).toBe('+3.2′');
    expect(formatDeltaDec(-1.25)).toBe('−1.25°');
    expect(scopeRange(0.5)).toBe(2);
    expect(scopeRange(17.7)).toBe(45);
    expect(isEquatorial('eq_gem')).toBe(true);
    expect(isEquatorial('altaz')).toBe(false);
  });
});
