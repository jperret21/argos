/**
 * Live-update timings: how long one append costs, from setData to the end of
 * the last chart's draw hook (all synchronous canvas work), and how many
 * paints per second the page delivers while appending.
 */

export interface PerfSummary {
  samples: number;
  last: number;
  median: number;
  p95: number;
  max: number;
  /** Paints per second over the last second (requestAnimationFrame cadence). */
  fps: number;
}

export class PerfRecorder {
  private buf: number[] = [];
  private frames: number[] = [];
  last = 0;
  constructor(private size = 240) {}

  record(ms: number): void {
    this.last = ms;
    this.buf.push(ms);
    if (this.buf.length > this.size) this.buf.shift();
  }

  frame(ts: number): void {
    this.frames.push(ts);
    while (this.frames.length && ts - this.frames[0] > 1000) this.frames.shift();
  }

  reset(): void {
    this.buf = [];
    this.frames = [];
    this.last = 0;
  }

  summary(): PerfSummary {
    const s = this.buf.slice().sort((a, b) => a - b);
    const q = (p: number) => (s.length ? s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))] : 0);
    return { samples: s.length, last: this.last, median: q(0.5), p95: q(0.95), max: s.length ? s[s.length - 1] : 0, fps: this.frames.length };
  }
}
