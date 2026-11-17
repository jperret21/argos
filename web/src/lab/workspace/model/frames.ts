/**
 * Frame sources for the workspace lab.
 *
 * - FrameSynth: synthetic frames from frame.worker.ts (default). Each one is
 *   shaped as the server's DecodedFrame, so the real FitsViewer shows it
 *   through its normal path (upload, auto stretch, rotation, readouts).
 * - serverFrames(): the real /ws/frames stream of a running ARGOS server
 *   (?frames=server&api=http://127.0.0.1:8784&token=dev), through the app's
 *   own FrameStream. Overlays and readouts then still come from the
 *   synthetic field: positions are illustrative on a simulator frame.
 */

import type { DecodedFrame } from '../../../lib/api/frames';
import { FrameStream } from '../../../lib/api/frames';
import { resolveConfig } from '../../../lib/config';
import type { FrameStats } from '../../../lib/api/types';
import { FRAME_H, FRAME_W, STARS, ZERO_POINT } from './field';

export interface SynthParams {
  seq: number;
  hfd: number;
  sky: number;
  /** Read noise + sky noise, ADU (sigma). */
  noise?: number;
  mags?: Record<number, number>;
  transparency?: number;
  exposure: number;
  /** Frame time, unix seconds (header timestamp). */
  t: number;
  /** Star ids whose peak ADU to measure. */
  measure?: number[];
}

export interface SynthFrame {
  frame: DecodedFrame;
  peaks: Record<number, number>;
  clipped: number;
  /** Worker time to synthesise and measure, ms. */
  ms: number;
}

interface WorkerReply {
  type: 'frame';
  seq: number;
  buffer: ArrayBuffer;
  stats: FrameStats;
  peaks: Record<number, number>;
  clipped: number;
  ms: number;
}

export class FrameSynth {
  private worker: Worker;
  private waiting = new Map<number, { p: SynthParams; resolve: (f: SynthFrame) => void }>();

  constructor() {
    this.worker = new Worker(new URL('./frame.worker.ts', import.meta.url), { type: 'module' });
    const packed = new Float32Array(STARS.length * 4);
    STARS.forEach((s, i) => packed.set([s.x, s.y, s.v, s.id], i * 4));
    this.worker.postMessage({ type: 'init', width: FRAME_W, height: FRAME_H, stars: packed, zeroPoint: ZERO_POINT }, [
      packed.buffer,
    ]);
    this.worker.onmessage = (e: MessageEvent<WorkerReply>) => {
      const r = e.data;
      const w = this.waiting.get(r.seq);
      if (!w) return;
      this.waiting.delete(r.seq);
      const pixels = new Uint16Array(r.buffer);
      w.resolve({
        frame: {
          header: {
            seq: r.seq,
            width: FRAME_W,
            height: FRAME_H,
            channels: 1,
            dtype: 'uint16',
            pixel_offset: 0,
            exposure_s: w.p.exposure,
            timestamp: new Date(w.p.t * 1000).toISOString(),
            source: 'simulator',
            stats: r.stats,
          },
          pixels,
          byteLength: r.buffer.byteLength,
          decodeMs: r.ms,
        },
        peaks: r.peaks,
        clipped: r.clipped,
        ms: r.ms,
      });
    };
  }

  render(p: SynthParams): Promise<SynthFrame> {
    return new Promise((resolve) => {
      this.waiting.set(p.seq, { p, resolve });
      this.worker.postMessage({
        type: 'render',
        seq: p.seq,
        hfd: p.hfd,
        sky: p.sky,
        noise: p.noise ?? 21,
        mags: p.mags ?? {},
        transparency: p.transparency ?? 1,
        seed: p.seq + 1,
        measure: p.measure ?? [],
      });
    });
  }

  dispose(): void {
    this.worker.terminate();
    this.waiting.clear();
  }
}

/** Subscribe to a real server's frames; returns a stop function. */
export function serverFrames(onFrame: (f: DecodedFrame) => void, onState?: (s: string) => void): () => void {
  const config = resolveConfig(location.search, import.meta.env);
  const stream = new FrameStream(config, { onFrame, onState: (s) => onState?.(String(s)) });
  stream.start();
  return () => stream.stop();
}
