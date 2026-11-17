/**
 * The main-thread side of the frame statistics worker: one request in flight
 * at most, latest frame wins (a frame arriving while the worker measures the
 * previous one replaces any frame still waiting), and the result is tagged
 * with the frame's seq so a late answer is never shown against another frame.
 *
 * Without workers (tests, an engine that refuses them) `supported` is false
 * and the exposure check simply shows no star peaks; nothing else depends
 * on it.
 */

import type { DecodedFrame } from '../api/frames';
import type { StarPeaks } from './framestats';
import type { PeaksReply, PeaksRequest } from './framestats.worker';

export class FrameStatsWorker {
  /** The newest measured frame's peaks (with its seq), or null. */
  peaks: { seq: number; result: StarPeaks; ms: number } | null = $state.raw(null);
  readonly supported: boolean;
  private worker: Worker | null = null;
  private busy = false;
  /** The newest frame that arrived while the worker was busy (older ones are skipped). */
  private waiting: DecodedFrame | null = null;
  private waitingBayer: string | null = null;

  constructor() {
    let w: Worker | null = null;
    try {
      if (typeof Worker !== 'undefined') {
        w = new Worker(new URL('./framestats.worker.ts', import.meta.url), { type: 'module' });
      }
    } catch {
      w = null;
    }
    this.worker = w;
    this.supported = !!w;
    w?.addEventListener('message', (e: MessageEvent<PeaksReply>) => this.onReply(e.data));
    w?.addEventListener('error', () => {
      this.busy = false;
    });
  }

  /** Measure this frame (single-channel frames only; colour previews have no raw peaks). */
  measure(frame: DecodedFrame, bayer: string | null): void {
    if (!this.worker || frame.header.channels !== 1) return;
    if (this.busy) {
      this.waiting = frame;
      this.waitingBayer = bayer;
      return;
    }
    this.send(frame, bayer);
  }

  private send(frame: DecodedFrame, bayer: string | null): void {
    const h = frame.header;
    const req: PeaksRequest = { type: 'peaks', seq: h.seq, width: h.width, height: h.height, bayer, pixels: frame.pixels.slice() };
    this.busy = true;
    this.worker!.postMessage(req, [req.pixels.buffer]);
  }

  private onReply(r: PeaksReply): void {
    this.busy = false;
    if (r.result) this.peaks = { seq: r.seq, result: r.result, ms: r.ms };
    const next = this.waiting;
    this.waiting = null;
    if (next) this.send(next, this.waitingBayer);
  }

  dispose(): void {
    this.worker?.terminate();
    this.worker = null;
  }
}
