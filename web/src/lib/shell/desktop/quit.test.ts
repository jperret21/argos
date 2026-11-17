import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/client';
import type { ShutdownAnswer, ShutdownEvent } from '../../api/desktop';
import { CLOSE_STALL_MS, QuitFlow, STUCK_MS } from './quit.svelte';
import type { LocalActivity } from './words';

const RUNNING: LocalActivity = { sequence: { state: 'running', object: 'SS Cyg', done: 34, total: 120 }, camera: 'exposing' };
const ev = (stage: string, done = false): ShutdownEvent => ({ stage, label: null, t: null, index: null, count: null, done });
const ACCEPTED: ShutdownAnswer = { outcome: 'accepted', stages: [], budgetS: null };
const PLAN = [
  { id: 'sequence', label: 'Stopping the sequence' },
  { id: 'services', label: 'Stopping background tasks' },
  { id: 'devices', label: 'Closing the equipment connections' },
  { id: 'exit', label: 'Stopping the ARGOS server' },
];

function setup(answers: (ShutdownAnswer | Error)[], opts: { desktop?: boolean; activity?: LocalActivity } = {}) {
  let clock = 1_000;
  const asked: boolean[] = [];
  let exits = 0;
  const nows: boolean[] = [];
  const flow = new QuitFlow({
    desktop: opts.desktop ?? true,
    now: () => clock,
    activity: () => opts.activity ?? {},
    exit: (now) => {
      exits++;
      nows.push(!!now);
    },
    shutdown: async (force) => {
      asked.push(force);
      const a = answers.shift();
      if (!a) throw new Error('no answer prepared');
      if (a instanceof Error) throw a;
      return a;
    },
  });
  return {
    flow,
    asked,
    exits: () => exits,
    nows,
    advance: (ms: number) => {
      clock += ms;
      vi.advanceTimersByTime(ms);
    },
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('QuitFlow', () => {
  it('idle server: the scrim at once, the stages, then the window closes', async () => {
    const t = setup([ACCEPTED]);
    await t.flow.request();
    expect(t.asked).toEqual([false]);
    expect(t.flow.phase).toBe('stopping');
    expect(t.flow.scrim).toBe(true);
    expect(t.flow.stages.map((s) => s.label)).toEqual(['Shutting down']);
    t.advance(300);
    t.flow.onShutdownEvent(ev('devices'));
    t.advance(1_200);
    t.flow.onShutdownEvent(ev('devices')); // a repeat changes nothing
    expect(t.flow.current?.label).toBe('Closing the equipment connections');
    expect(t.flow.stages[0]).toMatchObject({ from: 1_000, to: 1_300 });
    t.flow.onShutdownEvent(ev('done', true));
    expect(t.flow.phase).toBe('closing');
    expect(t.flow.stages.every((s) => s.to !== null)).toBe(true);
    expect(t.exits()).toBe(1);
  });

  it("the server's plan: every stage listed, marked as the events arrive", async () => {
    const t = setup([{ outcome: 'accepted', stages: PLAN, budgetS: 60 }]);
    await t.flow.request();
    expect(t.flow.budgetS).toBe(60);
    expect(t.flow.stages.map((s) => [s.id, s.from])).toEqual([
      ['sequence', null],
      ['services', null],
      ['devices', null],
      ['exit', null],
    ]);
    expect(t.flow.current).toBeNull();
    t.flow.onShutdownEvent(ev('sequence'));
    t.advance(500);
    // services passed without a word: done at once when devices begins
    t.flow.onShutdownEvent(ev('devices'));
    expect(t.flow.stages.map((s) => [s.id, s.from, s.to])).toEqual([
      ['sequence', 1_000, 1_500],
      ['services', 1_500, 1_500],
      ['devices', 1_500, null],
      ['exit', null, null],
    ]);
    expect(t.flow.current?.id).toBe('devices');
    t.advance(200);
    t.flow.onShutdownEvent({ ...ev('exit', true), label: 'Stopping the ARGOS server' });
    expect(t.flow.stages.every((s) => s.to !== null)).toBe(true);
    expect(t.flow.phase).toBe('closing');
  });

  it('a link that closes early leaves the stages not reached unmarked', async () => {
    const t = setup([{ outcome: 'accepted', stages: PLAN, budgetS: 60 }]);
    await t.flow.request();
    t.flow.onShutdownEvent(ev('sequence'));
    t.advance(100);
    t.flow.onLink(false);
    expect(t.flow.stages.map((s) => s.to === null)).toEqual([false, true, true, true]);
    expect(t.flow.phase).toBe('closing');
  });

  it('busy: the dialog with what runs; Cancel stops nothing', async () => {
    const t = setup([{ outcome: 'busy', items: [{ kind: 'sequence', label: null, detail: null }], message: 'A sequence is running.' }], { activity: RUNNING });
    await t.flow.request();
    expect(t.flow.phase).toBe('confirm');
    expect(t.flow.sentences).toEqual(['A sequence is running: SS Cyg, 34 of 120 frames.']);
    expect(t.flow.message).toBe('A sequence is running.');
    t.flow.cancel();
    expect(t.flow.phase).toBe('idle');
    expect(t.exits()).toBe(0);
    expect(t.asked).toEqual([false]);
  });

  it('busy with no list: what the UI sees running', async () => {
    const t = setup([{ outcome: 'busy', items: [], message: 'Busy' }], { activity: RUNNING });
    await t.flow.request();
    expect(t.flow.busy.map((i) => i.kind)).toEqual(['sequence', 'exposure']);
  });

  it('held Quit forces the shutdown, then follows its stages', async () => {
    const t = setup([{ outcome: 'busy', items: [{ kind: 'live', label: null, detail: null }], message: 'Busy' }, ACCEPTED]);
    await t.flow.request();
    const forcing = t.flow.force();
    expect(t.flow.phase).toBe('forcing');
    await forcing;
    expect(t.asked).toEqual([false, true]);
    expect(t.flow.phase).toBe('stopping');
    t.flow.onLink(false); // the link closes: the server is gone
    expect(t.flow.phase).toBe('closing');
    expect(t.exits()).toBe(1);
  });

  it('a refused forced request still quits (through the shell)', async () => {
    const t = setup([{ outcome: 'busy', items: [], message: 'Busy' }, new ApiError(500, 'internal_error', 'Boom')]);
    await t.flow.request();
    await t.flow.force();
    expect(t.flow.phase).toBe('closing');
    expect(t.exits()).toBe(1);
  });

  it('another refusal shows in the dialog; Quit ARGOS still quits', async () => {
    const t = setup([new ApiError(500, 'internal_error', 'Boom')], { activity: { camera: 'live' } });
    await t.flow.request();
    expect(t.flow.phase).toBe('confirm');
    expect(t.flow.error).toBe('Boom');
    expect(t.flow.busy.map((i) => i.kind)).toEqual(['live']);
  });

  it('a server without A7: the UI checks what runs; forcing quits through the shell', async () => {
    const idle = setup([{ outcome: 'unsupported' }]);
    await idle.flow.request();
    expect(idle.flow.phase).toBe('closing');
    expect(idle.exits()).toBe(1);

    const busy = setup([{ outcome: 'unsupported' }], { activity: RUNNING });
    await busy.flow.request();
    expect(busy.flow.phase).toBe('confirm');
    await busy.flow.force();
    expect(busy.asked).toEqual([false]); // no second request to a server without the route
    expect(busy.flow.phase).toBe('closing');
  });

  it('no server answering: the window closes at once', async () => {
    const t = setup([{ outcome: 'unreachable', message: 'Cannot reach' }]);
    await t.flow.request();
    expect(t.flow.phase).toBe('closing');
    expect(t.exits()).toBe(1);
  });

  it('one request at a time; Quit again while closing asks the shell again', async () => {
    const t = setup([ACCEPTED]);
    const first = t.flow.request();
    await t.flow.request();
    await first;
    expect(t.asked).toEqual([false]);
    t.flow.onShutdownEvent(ev('done', true));
    await t.flow.request();
    expect(t.exits()).toBe(2);
  });

  it('a stuck shutdown offers Quit now; a window that stays says so', async () => {
    const t = setup([ACCEPTED]);
    await t.flow.request();
    t.advance(STUCK_MS - 1);
    expect(t.flow.stuck).toBe(false);
    t.advance(1);
    expect(t.flow.stuck).toBe(true);
    t.flow.quitNow();
    expect(t.flow.phase).toBe('closing');
    expect(t.flow.stuck).toBe(false);
    // "Quit now" asks the shell to stop the server at once (no shutdown bound to wait).
    expect(t.nows.at(-1)).toBe(true);
    t.advance(CLOSE_STALL_MS);
    expect(t.flow.closeStalled).toBe(true);
  });

  it('stages that arrive before the 202 start the scrim', async () => {
    let release: (a: ShutdownAnswer) => void = () => {};
    const flow = new QuitFlow({
      desktop: true,
      activity: () => ({}),
      exit: () => {},
      shutdown: () => new Promise<ShutdownAnswer>((r) => (release = r)),
    });
    const req = flow.request();
    flow.onShutdownEvent(ev('sequence'));
    expect(flow.phase).toBe('stopping');
    release({ outcome: 'accepted', stages: PLAN, budgetS: 60 });
    await req;
    expect(flow.phase).toBe('stopping');
    expect(flow.stages.map((s) => s.id)).toEqual(['sequence', 'services', 'devices', 'exit']);
  });

  it('a shutdown asked elsewhere: remote stages, then stopped, then back when the server returns', () => {
    const t = setup([], { desktop: false });
    t.flow.onShutdownEvent(ev('sequence'));
    expect(t.flow.phase).toBe('remote');
    expect(t.flow.sawShutdown).toBe(true);
    t.flow.onLink(false);
    expect(t.flow.phase).toBe('stopped');
    expect(t.exits()).toBe(0);
    t.flow.onLink(true);
    expect(t.flow.phase).toBe('idle');
    // A later stop of the new server is not that shutdown (a crash stays a crash).
    expect(t.flow.sawShutdown).toBe(false);
  });

  it('Quit during a shutdown asked elsewhere: the window closes once the server is gone', async () => {
    const t = setup([]);
    t.flow.onShutdownEvent(ev('sequence'));
    expect(t.flow.phase).toBe('remote');
    await t.flow.request();
    expect(t.asked).toEqual([]);
    expect(t.flow.phase).toBe('stopping');
    t.flow.onLink(false);
    expect(t.flow.phase).toBe('closing');
    expect(t.exits()).toBe(1);
  });

  it('there is no Quit in a browser', async () => {
    const t = setup([ACCEPTED], { desktop: false });
    await t.flow.request();
    t.flow.exitNow();
    expect(t.asked).toEqual([]);
    expect(t.flow.phase).toBe('idle');
  });

  it('exitNow closes with no server to ask (crash notice)', () => {
    const t = setup([]);
    t.flow.exitNow();
    expect(t.flow.phase).toBe('closing');
    expect(t.exits()).toBe(1);
  });
});
