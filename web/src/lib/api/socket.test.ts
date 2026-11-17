import { describe, expect, it } from 'vitest';
import {
  backoffDelay,
  DEFAULT_BACKOFF,
  type LinkState,
  ReconnectingSocket,
  type WebSocketLike,
  withToken,
  WS_FORBIDDEN,
  WS_UNAUTHORIZED,
} from './socket';

class FakeSocket implements WebSocketLike {
  binaryType: BinaryType = 'blob';
  readyState = 0;
  onopen: ((ev: Event) => unknown) | null = null;
  onclose: ((ev: CloseEvent) => unknown) | null = null;
  onerror: ((ev: Event) => unknown) | null = null;
  onmessage: ((ev: MessageEvent) => unknown) | null = null;
  closedWith: number | null = null;
  constructor(readonly url: string) {}
  close(code?: number): void {
    this.closedWith = code ?? 1000;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }
  message(data: unknown): void {
    this.onmessage?.({ data } as MessageEvent);
  }
  drop(code = 1006, reason = ''): void {
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

function harness() {
  const sockets: FakeSocket[] = [];
  const timers: Array<{ fn: () => void; ms: number; cleared: boolean }> = [];
  const states: LinkState[] = [];
  const messages: unknown[] = [];
  const rs = new ReconnectingSocket({
    url: 'ws://127.0.0.1:8742/ws/events?token=t',
    binaryType: 'arraybuffer',
    onMessage: (d) => messages.push(d),
    onState: (s) => states.push(s),
    createSocket: (url) => {
      const s = new FakeSocket(url);
      sockets.push(s);
      return s;
    },
    setTimer: (fn, ms) => {
      const t = { fn, ms, cleared: false };
      timers.push(t);
      return t;
    },
    clearTimer: (h) => {
      (h as { cleared: boolean }).cleared = true;
    },
  });
  const fire = () => {
    const t = timers.filter((x) => !x.cleared).pop();
    if (!t) throw new Error('no pending timer');
    t.cleared = true;
    t.fn();
  };
  return { rs, sockets, timers, states, messages, fire };
}

describe('backoffDelay', () => {
  it('grows exponentially up to the ceiling', () => {
    const mid = () => 0.5; // no jitter
    expect(backoffDelay(0, DEFAULT_BACKOFF, mid)).toBe(500);
    expect(backoffDelay(1, DEFAULT_BACKOFF, mid)).toBe(1000);
    expect(backoffDelay(3, DEFAULT_BACKOFF, mid)).toBe(4000);
    expect(backoffDelay(10, DEFAULT_BACKOFF, mid)).toBe(10_000);
  });

  it('jitters within +/- 20 %', () => {
    expect(backoffDelay(2, DEFAULT_BACKOFF, () => 0)).toBe(1600);
    expect(backoffDelay(2, DEFAULT_BACKOFF, () => 1)).toBe(2400);
  });
});

describe('withToken', () => {
  it('appends an encoded token', () => {
    expect(withToken('ws://h:1/ws/events', 'a b')).toBe('ws://h:1/ws/events?token=a%20b');
    expect(withToken('ws://h:1/ws/events?x=1', 'k')).toBe('ws://h:1/ws/events?x=1&token=k');
  });
});

describe('ReconnectingSocket', () => {
  it('opens, forwards messages and reconnects after a drop', () => {
    const h = harness();
    h.rs.start();
    expect(h.sockets).toHaveLength(1);
    expect(h.sockets[0]!.binaryType).toBe('arraybuffer');
    expect(h.states).toEqual(['connecting']);

    h.sockets[0]!.open();
    h.sockets[0]!.message('hello');
    expect(h.messages).toEqual(['hello']);
    expect(h.rs.state).toBe('open');

    h.sockets[0]!.drop(1006);
    expect(h.rs.state).toBe('reconnecting');
    expect(h.timers).toHaveLength(1);
    h.fire();
    expect(h.sockets).toHaveLength(2);
    h.sockets[1]!.open();
    expect(h.rs.state).toBe('open');
  });

  it('backs off while the server stays down and resets after a success', () => {
    const h = harness();
    h.rs.start();
    for (let i = 0; i < 4; i++) {
      h.sockets[i]!.drop(1006);
      h.fire();
    }
    const delays = h.timers.map((t) => t.ms);
    // Jittered exponential: each delay within +/-20 % of 500, 1000, 2000, 4000.
    [500, 1000, 2000, 4000].forEach((base, i) => {
      expect(delays[i]).toBeGreaterThanOrEqual(base * 0.8);
      expect(delays[i]).toBeLessThanOrEqual(base * 1.2);
    });
    // Success = a delivered message (an accepted socket may still be closed at once).
    h.sockets[4]!.open();
    h.sockets[4]!.message('status');
    h.sockets[4]!.drop(1006);
    expect(h.timers.at(-1)!.ms).toBeLessThanOrEqual(600); // back to the first step
  });

  it('keeps backing off when the server accepts then closes at once', () => {
    const h = harness();
    h.rs.start();
    for (let i = 0; i < 4; i++) {
      h.sockets[i]!.open(); // accepted…
      h.sockets[i]!.drop(1013); // …then closed (overloaded, shutting down)
      h.fire();
    }
    expect(h.timers.at(-1)!.ms).toBeGreaterThanOrEqual(4000 * 0.8);
  });

  it('stops retrying on 4403 (refused origin) like on 4401', () => {
    const h = harness();
    h.rs.start();
    h.sockets[0]!.open();
    h.sockets[0]!.drop(WS_FORBIDDEN, 'forbidden origin');
    expect(h.rs.state).toBe('forbidden');
    expect(h.timers).toHaveLength(0);
  });

  it('stops retrying on 4401 (bad token) until restart()', () => {
    const h = harness();
    h.rs.start();
    h.sockets[0]!.drop(WS_UNAUTHORIZED, 'unauthorized');
    expect(h.rs.state).toBe('unauthorized');
    expect(h.timers).toHaveLength(0);
    h.rs.restart();
    expect(h.sockets).toHaveLength(2);
    expect(h.rs.state).toBe('connecting');
  });

  it('stop() closes the socket, cancels the retry and ignores late events', () => {
    const h = harness();
    h.rs.start();
    h.sockets[0]!.open();
    h.rs.stop();
    expect(h.sockets[0]!.closedWith).toBe(1000);
    expect(h.rs.state).toBe('idle');
    h.sockets[0]!.message('late'); // handlers were detached
    expect(h.messages).toEqual([]);

    h.rs.start();
    h.sockets[1]!.drop(1006);
    h.rs.stop();
    expect(h.timers.at(-1)!.cleared).toBe(true);
    expect(h.sockets).toHaveLength(2);
  });
});
