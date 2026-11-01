/**
 * Frame cadence and latency of the frames actually drawn (FitsViewer
 * ondisplay), not of the frames received (the viewer may coalesce some).
 *
 * - fps: drawn frames per second over the last few frames (at most `window`
 *   intervals), timed by the frames' own timestamps (end of exposure) when
 *   they have one. Display times would be skewed by the frame the server
 *   replays to every new socket, which arrives right before the next live
 *   one. A pause longer than `staleMs` starts a new measurement, so a
 *   capture taken after a quiet minute does not report 0.02 fps.
 * - latency: draw time minus the frame's own timestamp (end of the exposure,
 *   server clock): download + encode + transfer + decode + upload + draw. The
 *   server and the UI run on the same machine, so the clocks agree; clamped at
 *   0 against small clock jitter.
 */

export interface FrameMetrics {
  /** Frames per second, or null until two frames have been drawn. */
  fps: number | null;
  /** Milliseconds from end of exposure to display, or null if unknown. */
  latencyMs: number | null;
  /** Number of frames drawn since the meter was created or reset. */
  frames: number;
}

export class FrameRateMeter {
  private times: number[] = [];
  private lastSeq: number | null = null;
  private frames = 0;
  private latency: number | null = null;
  private readonly window: number;
  private readonly staleMs: number;

  constructor(window = 8, staleMs = 15_000) {
    this.window = window;
    this.staleMs = staleMs;
  }

  /**
   * @param shownAt   epoch ms when the frame was drawn
   * @param timestamp ISO 8601 time of the frame (end of exposure), if any
   * @param seq       frame sequence number; a frame drawn twice counts once
   */
  record(shownAt: number, timestamp?: string | null, seq?: number): FrameMetrics {
    if (seq !== undefined && seq === this.lastSeq) return this.snapshot();
    this.lastSeq = seq ?? null;
    const t = timestamp ? Date.parse(timestamp) : Number.NaN;
    const at = Number.isFinite(t) ? t : shownAt;
    const last = this.times[this.times.length - 1];
    if (last !== undefined && (at - last > this.staleMs || at < last)) this.times = [];
    this.times.push(at);
    if (this.times.length > this.window + 1) this.times.shift();
    this.frames += 1;
    this.latency = Number.isFinite(t) ? Math.max(0, shownAt - t) : null;
    return this.snapshot();
  }

  snapshot(): FrameMetrics {
    const n = this.times.length;
    let fps: number | null = null;
    if (n >= 2) {
      const span = this.times[n - 1] - this.times[0];
      fps = span > 0 ? ((n - 1) * 1000) / span : null;
    }
    return { fps, latencyMs: this.latency, frames: this.frames };
  }

  reset(): void {
    this.times = [];
    this.lastSeq = null;
    this.frames = 0;
    this.latency = null;
  }
}

/** "1.0 fps", "12 fps", "—". */
export function formatFps(fps: number | null): string {
  if (fps === null || !Number.isFinite(fps)) return '—';
  return fps < 10 ? `${fps.toFixed(1)} fps` : `${Math.round(fps)} fps`;
}

/** "38 ms", "1.24 s", "—". */
export function formatLatency(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return '—';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}
