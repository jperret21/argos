/**
 * The screen wake lock while Watch is shown (PROPOSAL §3.1 "Keep the computer awake": the
 * server's OS assertion keeps the COMPUTER awake during a run; this second layer keeps the
 * DISPLAY on while the observer watches from across the room). `navigator.wakeLock` is in
 * Chromium and Safari 16.4+; WKWebView and WebKitGTK are untested (functional-spaces
 * §4.10). The browser drops the lock when the page is hidden: it is asked again when the
 * page shows, while Watch is still open. A closed laptop lid still sleeps: out of software
 * reach (the preflight says so).
 *
 *   const stop = keepScreenOn(navigator, document, (s) => (lock = s));
 *   stop();   // on leaving Watch: released, listeners removed
 */

export type WakeState = 'pending' | 'held' | 'released' | 'refused' | 'unsupported';

/** What the lock needs from `navigator` and `document` (tests pass fakes). */
export interface WakeNavigator {
  wakeLock?: { request(type: 'screen'): Promise<WakeSentinel> };
}
export interface WakeSentinel {
  readonly released: boolean;
  release(): Promise<void>;
  addEventListener(type: 'release', fn: () => void): void;
  removeEventListener(type: 'release', fn: () => void): void;
}
export interface WakeDocument {
  readonly visibilityState: string;
  addEventListener(type: 'visibilitychange', fn: () => void): void;
  removeEventListener(type: 'visibilitychange', fn: () => void): void;
}

export const WAKE_WORDS: Record<WakeState, string> = {
  pending: 'Asking to keep the screen on…',
  held: 'Screen kept on',
  released: 'Screen may sleep (page hidden)',
  refused: 'Screen may sleep: the browser refused to keep it on',
  unsupported: 'Screen may sleep: this browser cannot keep it on',
};

/** The footer's short form (the full sentence is its tooltip). */
export const WAKE_SHORT: Record<WakeState, string> = {
  pending: 'screen: asking',
  held: 'screen on',
  released: 'screen may sleep',
  refused: 'screen may sleep (refused)',
  unsupported: 'screen may sleep (no wake lock)',
};

export function keepScreenOn(nav: WakeNavigator | null | undefined, doc: WakeDocument | null | undefined, onstate: (s: WakeState) => void): () => void {
  const api = nav?.wakeLock;
  if (!api || typeof api.request !== 'function') {
    onstate('unsupported');
    return () => undefined;
  }
  let sentinel: WakeSentinel | null = null;
  let stopped = false;
  // One request at a time: a 'visible' event while the first was pending started a second,
  // whose sentinel replaced the first, which was never released (technical review).
  let pending = false;
  const onRelease = () => {
    if (!stopped) onstate('released');
  };
  const request = async () => {
    if (stopped || pending || (sentinel && !sentinel.released)) return;
    pending = true;
    onstate('pending');
    try {
      const s = await api.request('screen');
      if (stopped || (sentinel && !sentinel.released)) {
        await s.release().catch(() => undefined);
        return;
      }
      sentinel = s;
      s.addEventListener('release', onRelease);
      onstate('held');
    } catch {
      if (!stopped) onstate('refused');
    } finally {
      pending = false;
    }
  };
  const onVisible = () => {
    if (doc?.visibilityState === 'visible') void request();
  };
  doc?.addEventListener('visibilitychange', onVisible);
  void request();
  return () => {
    stopped = true;
    doc?.removeEventListener('visibilitychange', onVisible);
    const s = sentinel;
    sentinel = null;
    if (s) {
      s.removeEventListener('release', onRelease);
      if (!s.released) void s.release().catch(() => undefined);
    }
  };
}
