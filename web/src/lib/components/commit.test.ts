import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CommitModel, refusalText } from './commit.svelte';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

/** A send whose answer the test decides. */
function deferredSend() {
  const calls: { v: number; resolve: () => void; reject: (e: unknown) => void }[] = [];
  const send = vi.fn(
    (v: number) =>
      new Promise<void>((resolve, reject) => {
        calls.push({ v, resolve, reject });
      }),
  );
  return { send, calls };
}

describe('CommitModel: one value per commit', () => {
  it('holds an edit as "not sent" and sends nothing until commit', () => {
    const { send } = deferredSend();
    const m = new CommitModel<number>(30, { send });
    m.edit(45);
    expect(m.phase).toBe('dirty');
    expect(m.current).toBe(45);
    expect(m.value).toBe(30);
    expect(send).not.toHaveBeenCalled();
  });

  it('goes sending -> applied -> idle, and adopts the value', async () => {
    const { send, calls } = deferredSend();
    const m = new CommitModel<number>(30, { send, appliedMs: 2000 });
    m.edit(45);
    const done = m.commit();
    expect(m.phase).toBe('sending');
    expect(m.busy).toBe(true);
    calls[0].resolve();
    expect(await done).toBe(true);
    expect(m.phase).toBe('applied');
    expect(m.value).toBe(45);
    expect(m.hasDraft).toBe(false);
    vi.advanceTimersByTime(2000);
    expect(m.phase).toBe('idle');
  });

  it('keeps the refused value with the server words; Esc reverts', async () => {
    const { send, calls } = deferredSend();
    const m = new CommitModel<number>(30, { send });
    m.edit(200);
    const done = m.commit();
    calls[0].reject(new Error('Radius must be at most 180 °'));
    expect(await done).toBe(false);
    expect(m.phase).toBe('refused');
    expect(m.refused).toBe('Radius must be at most 180 °');
    expect(m.current).toBe(200); // the field keeps the rejected value
    m.revert();
    expect(m.phase).toBe('idle');
    expect(m.current).toBe(30);
    expect(m.refused).toBeNull();
  });

  it('an unchanged value is not sent', async () => {
    const { send } = deferredSend();
    const m = new CommitModel<number>(30, { send });
    m.edit(30);
    expect(m.phase).toBe('idle');
    expect(await m.commit()).toBe(true);
    expect(send).not.toHaveBeenCalled();
  });

  it('sends once after the settle pause of arrow steps, not per step', async () => {
    const { send, calls } = deferredSend();
    const m = new CommitModel<number>(1, { send });
    m.offer(2, 600);
    vi.advanceTimersByTime(300);
    m.offer(3, 600);
    vi.advanceTimersByTime(599);
    expect(send).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(3);
    calls[0].resolve();
    await vi.runAllTimersAsync();
    expect(m.value).toBe(3);
  });

  it('a late answer to an older commit never changes the field', async () => {
    const { send, calls } = deferredSend();
    const m = new CommitModel<number>(1, { send });
    const first = m.commit(2);
    const second = m.commit(3);
    calls[0].reject(new Error('old refusal'));
    expect(await first).toBe(false);
    expect(m.phase).toBe('sending');
    calls[1].resolve();
    expect(await second).toBe(true);
    expect(m.value).toBe(3);
    expect(m.refused).toBeNull();
  });

  it('applies at once without a send (local values)', async () => {
    const onapplied = vi.fn();
    const m = new CommitModel<number>(1, { onapplied });
    expect(await m.commit(4)).toBe(true);
    expect(m.value).toBe(4);
    expect(m.phase).toBe('idle');
    expect(onapplied).toHaveBeenCalledWith(4);
  });
});

describe('CommitModel: edits and commits while a value is on its way (technical review)', () => {
  /** The server: holds the last value it accepted, in the order requests are answered. */
  function server(initial: number) {
    const d = deferredSend();
    const state = { held: initial };
    const answer = async (i: number) => {
      state.held = d.calls[i].v;
      d.calls[i].resolve();
      await vi.advanceTimersByTimeAsync(0); // flush the answer, without running the 2 s "Applied"
    };
    return { ...d, state, answer };
  }

  it('(a) a commit back to the applied value while another is in flight is still sent', async () => {
    const srv = server(10);
    const m = new CommitModel<number>(10, { send: srv.send });
    m.edit(20);
    void m.commit(); // 20 on its way
    m.edit(10);
    expect(m.phase).toBe('dirty'); // 10 differs from what the server will hold (20)
    const last = m.commit();
    expect(m.phase).toBe('sending');
    expect(srv.send).toHaveBeenCalledTimes(1); // one request at a time
    await srv.answer(0);
    expect(srv.send).toHaveBeenCalledTimes(2);
    expect(srv.calls[1].v).toBe(10);
    await srv.answer(1);
    expect(await last).toBe(true);
    expect(m.value).toBe(10);
    expect(srv.state.held).toBe(10); // the observer's last Enter wins
    expect(m.phase).toBe('applied');
  });

  it('(b) a step back while the settled value is in flight keeps the spinner, then sends it', async () => {
    const srv = server(10);
    const m = new CommitModel<number>(10, { send: srv.send });
    m.offer(11, 600);
    vi.advanceTimersByTime(600); // the settle sends 11
    expect(srv.send).toHaveBeenCalledWith(11);
    m.offer(10, 600);
    expect(m.phase).toBe('dirty'); // never 'idle' while 11 is on its way
    expect(m.current).toBe(10);
    vi.advanceTimersByTime(600);
    expect(m.phase).toBe('sending');
    await srv.answer(0);
    expect(srv.calls[1].v).toBe(10);
    await srv.answer(1);
    expect(m.value).toBe(10);
    expect(srv.state.held).toBe(10);
  });

  it('(c) a draft typed while sending survives the answer and is sent on blur', async () => {
    const srv = server(10);
    const m = new CommitModel<number>(10, { send: srv.send });
    m.edit(20);
    void m.commit();
    m.edit(30); // typed while 20 is on its way
    await srv.answer(0);
    expect(m.value).toBe(20);
    expect(m.hasDraft).toBe(true);
    expect(m.current).toBe(30);
    expect(m.phase).toBe('dirty'); // so the blur commit (phase 'dirty') sends it
    void m.commit();
    expect(srv.calls[1].v).toBe(30);
    await srv.answer(1);
    expect(m.value).toBe(30);
    expect(srv.state.held).toBe(30);
  });

  it('a newer commit replaces one still waiting; only the last is sent after the first', async () => {
    const srv = server(1);
    const m = new CommitModel<number>(1, { send: srv.send });
    void m.commit(2);
    const middle = m.commit(3);
    const last = m.commit(4);
    expect(await middle).toBe(false); // superseded before it was sent
    await srv.answer(0);
    expect(srv.calls.map((c) => c.v)).toEqual([2, 4]);
    await srv.answer(1);
    expect(await last).toBe(true);
    expect(m.value).toBe(4);
  });

  it('Esc while a value is in flight: its answer no longer changes the field', async () => {
    const srv = server(1);
    const m = new CommitModel<number>(1, { send: srv.send });
    const first = m.commit(2);
    m.revert();
    expect(m.phase).toBe('idle');
    await srv.answer(0);
    expect(await first).toBe(false);
    expect(m.phase).toBe('idle');
    m.sync(2); // the server's echo then updates the field like any outside value
    expect(m.current).toBe(2);
  });
});

describe('CommitModel: sync between clients (README 3.4)', () => {
  it('takes a value from elsewhere while the field holds nothing of its own', () => {
    const m = new CommitModel<number>(30);
    m.sync(40);
    expect(m.current).toBe(40);
    expect(m.elsewhere).toBeNull();
  });

  it('keeps the field being edited and says "changed elsewhere"', () => {
    const m = new CommitModel<number>(30);
    m.edit(45);
    m.sync(40);
    expect(m.current).toBe(45);
    expect(m.elsewhere).toEqual({ v: 40 });
    m.reload();
    expect(m.current).toBe(40);
    expect(m.phase).toBe('idle');
    expect(m.elsewhere).toBeNull();
  });

  it('recognises the echo of its own commit', async () => {
    const { send, calls } = deferredSend();
    const m = new CommitModel<number>(30, { send });
    const done = m.commit(45);
    m.sync(45); // the config event arrives before the PATCH answer
    expect(m.elsewhere).toBeNull();
    calls[0].resolve();
    await done;
    expect(m.value).toBe(45);
    expect(m.elsewhere).toBeNull();
  });

  it('Esc takes the newer value from elsewhere', () => {
    const m = new CommitModel<number>(30);
    m.edit(45);
    m.sync(40);
    m.revert();
    expect(m.current).toBe(40);
  });

  it('a refusal from outside (one PATCH for several keys)', () => {
    const m = new CommitModel<number>(30);
    m.edit(45);
    m.refuse('not writable');
    expect(m.phase).toBe('refused');
    expect(m.refused).toBe('not writable');
  });
});

describe('refusalText', () => {
  it('reads the words of an error, a string or an object', () => {
    expect(refusalText(new Error('Device busy'))).toBe('Device busy');
    expect(refusalText('Out of range')).toBe('Out of range');
    expect(refusalText({ message: 'Nope' })).toBe('Nope');
    expect(refusalText(undefined)).toBe('The server refused this value');
  });
});
