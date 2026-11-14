/**
 * Alert tones through the Web Audio API (promoted from src/lab/workspace/model/sound.ts,
 * PROPOSAL §6 W6; BRAND §13): short synthesised sine tones, no sound file, no dependency.
 * Sound emits no light (Night Red) and reaches an observer in another room; it never
 * carries information found nowhere else: every tone has its attention item on screen.
 *
 * Browsers start audio only after a user gesture (WebKit and Chromium autoplay policy):
 * `arm()` creates the ONE AudioContext of the page from a gesture (the first press or key
 * in the app, choosing Soft or Normal, "Test sound"); before that, `play()` does nothing
 * and `armed` says so, so the list can tell the observer. `dispose()` closes the context
 * (app teardown).
 *
 * Critical: three descending tones; Attention: two rising; Info: one soft tone.
 */

import type { AttentionLevel } from '../../api/attention';
import type { SoundLevel } from './model';

/** The part of AudioContext the tones use (tests pass a fake). */
export interface ToneContext {
  readonly currentTime: number;
  readonly state: string;
  readonly destination: AudioNode;
  resume(): Promise<void>;
  close(): Promise<void>;
  createOscillator(): OscillatorNode;
  createGain(): GainNode;
}

export type ContextFactory = () => ToneContext;

const defaultFactory: ContextFactory = () => new AudioContext();

/** Peak gain per level of the setting (Off plays nothing). */
export const VOLUME: Record<Exclude<SoundLevel, 'off'>, number> = { soft: 0.06, normal: 0.16 };

/** The notes of each level: [delay s, frequency Hz, duration s, gain factor]. */
export const TONES: Record<AttentionLevel, readonly (readonly [number, number, number, number])[]> = {
  critical: [
    [0, 880, 0.18, 1],
    [0.24, 740, 0.18, 1],
    [0.48, 587, 0.3, 1],
  ],
  attention: [
    [0, 660, 0.16, 1],
    [0.22, 880, 0.22, 1],
  ],
  info: [[0, 523, 0.2, 0.6]],
};

export class AlertSound {
  private ctx: ToneContext | null = null;
  private failed = false;

  constructor(private readonly factory: ContextFactory = defaultFactory) {}

  /** The context exists and runs (a gesture armed it). */
  get armed(): boolean {
    return !!this.ctx && this.ctx.state === 'running';
  }

  /** The browser has no Web Audio, or refused the context. */
  get unavailable(): boolean {
    return this.failed;
  }

  /** Call from a user gesture. Returns whether the context exists (it may still be resuming). */
  arm(): boolean {
    if (this.failed) return false;
    try {
      this.ctx ??= this.factory();
      if (this.ctx.state !== 'running') void this.ctx.resume().catch(() => undefined);
      return true;
    } catch {
      this.failed = true;
      return false;
    }
  }

  /**
   * The tones of `level` at `volume`; nothing when Off or not armed. Returns whether it
   * played. A context the OS or the browser suspended ('suspended', WebKit's 'interrupted')
   * plays nothing: it is asked to resume and the call says false, so the store does not
   * record a tone nobody heard (a Critical item's repeat tries again).
   */
  play(level: AttentionLevel, volume: SoundLevel): boolean {
    const ctx = this.ctx;
    if (!ctx || volume === 'off' || ctx.state === 'closed') return false;
    if (ctx.state !== 'running') {
      void ctx.resume().catch(() => undefined);
      return false;
    }
    const v = VOLUME[volume];
    const t0 = ctx.currentTime + 0.02;
    try {
      for (const [dt, freq, dur, k] of TONES[level]) this.tone(ctx, t0 + dt, freq, dur, v * k);
      return true;
    } catch {
      return false;
    }
  }

  private tone(ctx: ToneContext, at: number, freq: number, dur: number, gain: number): void {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    // 10 ms attack and release: no click.
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(gain, at + 0.01);
    g.gain.setValueAtTime(gain, at + dur - 0.01);
    g.gain.linearRampToValueAtTime(0, at + dur);
    osc.connect(g).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + dur + 0.02);
  }

  /** Close the context (app teardown); a later arm() makes a new one. */
  dispose(): void {
    const ctx = this.ctx;
    this.ctx = null;
    if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => undefined);
  }
}

/**
 * Arm `sound` on the first press or key anywhere in `target` (the window), then stop
 * listening. Returns the detach. Capture phase: a press that opens a dialog still counts.
 */
export function armOnGesture(sound: AlertSound, target: Pick<EventTarget, 'addEventListener' | 'removeEventListener'>): () => void {
  const types = ['pointerdown', 'keydown'] as const;
  const once = () => {
    sound.arm();
    off();
  };
  const off = () => types.forEach((t) => target.removeEventListener(t, once, true));
  types.forEach((t) => target.addEventListener(t, once, true));
  return off;
}

/** The page's one alert sound (one AudioContext): the attention store and Settings › Alerts share it. */
export const alertSound = new AlertSound();
