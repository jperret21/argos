/**
 * Simulated hardware for the specimen (no server). Behaviour follows the
 * spec's API v2 sketches so the controls meet realistic timing:
 *
 * - Focuser (A15 / A16): 900 steps/s, position POLLED every 500 ms while
 *   moving (the UI shows polled values, never an interpolation), range
 *   0 to 100,000; a move out of range is refused with a reason, never
 *   clamped silently (fixes Qt P6). Taps while moving queue a delta sent as
 *   one move when the current one ends (driver-safe: no Move while moving).
 * - Autofocus (A17): 9 coarse + 4 fine + 1 verification, 1.2 s per sample.
 * - Mount jog (A10): per-axis rates, renewed by the client every 250 ms; the
 *   "server" stops an axis not renewed within 1 s (dead-man). Position
 *   polled at 5 Hz. `linkUp = false` drops the renewals (simulated outage).
 * - Park, slew with the angle still to go (polled 2 Hz), a running sequence.
 */

import { grouped } from './format';
import { DEADMAN_MS, type Axis } from './jog';

const now = () => performance.now();

export class FocuserSim {
  readonly maxStep = 100_000;
  readonly speed = 900; // steps per second
  connected = $state(true);
  /** Last polled position (what the UI may show). */
  position = $state(12_450);
  /** Commanded target while moving. */
  target: number | null = $state(null);
  /** Taps queued while moving (sent as one move at the end). */
  queued = $state(0);
  moving = $state(false);
  temperature = $state(12.3);
  /** Best focus and temperature of the last autofocus. */
  afBest = $state(12_380);
  afTemp = $state(14.1);
  af: { stage: 'coarse' | 'fine' | 'verify'; step: number; total: number } | null = $state(null);
  message: string | null = $state(null);

  #true = 12_450;
  #timer: ReturnType<typeof setInterval> | null = null;
  #lastPoll = 0;
  #afCancel = false;

  get busy(): boolean {
    return this.moving || this.af !== null;
  }

  /** A relative step from the buttons; queued while moving. */
  step(delta: number): void {
    if (!this.connected) return;
    if (this.moving) {
      this.queued += delta;
      return;
    }
    this.moveTo(this.position + delta);
  }

  /** Absolute move; throws with the reason when out of range. */
  moveTo(p: number): void {
    if (!this.connected) throw new Error('Connect the focuser first');
    const t = Math.round(p);
    if (t < 0 || t > this.maxStep) throw new Error(`Out of range: 0 to ${grouped(this.maxStep)}`);
    this.message = null;
    this.target = t;
    this.moving = true;
    this.#run();
  }

  halt(): void {
    this.#afCancel = this.af !== null;
    this.target = null;
    this.queued = 0;
    this.moving = false;
    this.position = Math.round(this.#true);
    this.message = `Halted at ${grouped(this.position)}`;
    this.#stopIfIdle();
  }

  async autofocus(): Promise<void> {
    if (this.af) return;
    this.#afCancel = false;
    this.message = null;
    const start = this.position;
    const coarse = Array.from({ length: 9 }, (_, i) => start - 2000 + i * 500);
    const best = start - 70 + Math.round((Math.random() - 0.5) * 60);
    const fine = [best - 150, best - 50, best + 50, best + 150];
    const plan = [
      ...coarse.map((p) => ({ p, stage: 'coarse' as const })),
      ...fine.map((p) => ({ p, stage: 'fine' as const })),
      { p: best, stage: 'verify' as const },
    ];
    for (let i = 0; i < plan.length; i++) {
      if (this.#afCancel) break;
      this.af = { stage: plan[i].stage, step: i + 1, total: plan.length };
      this.moveTo(plan[i].p);
      await this.#settled();
      if (this.#afCancel) break;
      await new Promise((r) => setTimeout(r, 1200));
    }
    if (this.#afCancel) {
      this.af = null;
      return;
    }
    this.af = null;
    this.afBest = best;
    this.afTemp = this.temperature;
    this.message = `Autofocus complete: ${grouped(best)} · HFD 2.31 px measured`;
  }

  stopAutofocus(): void {
    if (!this.af) return;
    this.#afCancel = true;
    const start = this.afBest;
    this.af = null;
    this.target = null;
    this.moving = false;
    this.moveTo(start);
    this.message = `Autofocus cancelled: returning to ${grouped(start)}`;
  }

  #settled(): Promise<void> {
    return new Promise((resolve) => {
      const check = () => (this.moving && !this.#afCancel ? setTimeout(check, 50) : resolve());
      check();
    });
  }

  #run(): void {
    if (this.#timer) return;
    let last = now();
    this.#timer = setInterval(() => {
      const t = now();
      const dt = (t - last) / 1000;
      last = t;
      if (this.moving && this.target !== null) {
        const d = this.target - this.#true;
        const stepNow = Math.sign(d) * Math.min(Math.abs(d), this.speed * dt);
        this.#true += stepNow;
        if (Math.abs(this.target - this.#true) < 0.5) {
          this.#true = this.target;
          this.position = this.target;
          if (this.queued !== 0 && !this.af) {
            const next = this.target + this.queued;
            this.queued = 0;
            try {
              this.moveTo(next);
            } catch (err) {
              this.moving = false;
              this.target = null;
              this.message = err instanceof Error ? err.message : String(err);
            }
          } else {
            this.moving = false;
            this.target = null;
          }
        } else if (t - this.#lastPoll >= 500) {
          this.#lastPoll = t;
          this.position = Math.round(this.#true); // the poll: 2 Hz
        }
      }
      this.#stopIfIdle();
    }, 50);
  }

  #stopIfIdle(): void {
    if (!this.moving && this.#timer) {
      clearInterval(this.#timer);
      this.#timer = null;
    }
  }
}

export class MountSim {
  connected = $state(true);
  parked = $state(false);
  tracking = $state(true);
  /** Polled pointing (5 Hz while jogging). */
  az = $state(182.3);
  alt = $state(41.27);
  /** Signed rates in deg/s commanded per axis. */
  rate = $state<Record<Axis, number>>({ primary: 0, secondary: 0 });
  /** Is the client's renewal reaching the server? */
  linkUp = $state(true);
  lastRenew = $state<Record<Axis, number>>({ primary: 0, secondary: 0 });
  deadmanStop: string | null = $state(null);
  /** Slew in progress: degrees still to go (polled 2 Hz). */
  slewToGo: number | null = $state(null);
  /** Trail of polled offsets since the session start (az, alt deltas). */
  trail = $state.raw<{ daz: number; dalt: number }[]>([]);

  #az = 182.3;
  #alt = 41.27;
  readonly origin = { az: 182.3, alt: 41.27 };
  #timer: ReturnType<typeof setInterval> | null = null;
  #lastPoll = 0;

  start(axis: Axis, rateDeg: number): void {
    if (!this.connected || this.parked) return;
    this.deadmanStop = null;
    this.rate = { ...this.rate, [axis]: rateDeg };
    // The start command counts as the first renewal (it reached the server);
    // a link lost afterwards only drops the renewals that follow.
    this.lastRenew = { ...this.lastRenew, [axis]: now() };
    this.#run();
  }

  stop(axis: Axis): void {
    if (this.rate[axis] === 0) return;
    this.rate = { ...this.rate, [axis]: 0 };
  }

  stopAll(): void {
    this.rate = { primary: 0, secondary: 0 };
  }

  /** Client renewal; lost while the link is down. */
  renew(axis: Axis): void {
    if (!this.linkUp) return;
    this.lastRenew = { ...this.lastRenew, [axis]: now() };
  }

  async park(): Promise<void> {
    if (this.parked) throw new Error('Already parked');
    this.stopAll();
    await new Promise((r) => setTimeout(r, 1600));
    this.parked = true;
    this.tracking = false;
  }

  unpark(): void {
    this.parked = false;
  }

  slew(deg = 12.4): void {
    if (this.parked) throw new Error('Unpark the mount first');
    this.slewToGo = deg;
    const t = setInterval(() => {
      if (this.slewToGo === null) return clearInterval(t);
      const next = Math.max(0, this.slewToGo - 1.5); // 3°/s, polled at 2 Hz
      this.slewToGo = next > 0.05 ? next : null;
      if (this.slewToGo === null) clearInterval(t);
    }, 500);
  }

  abortSlew(): void {
    this.slewToGo = null;
  }

  resetTrail(): void {
    this.#az = this.origin.az;
    this.#alt = this.origin.alt;
    this.az = this.#az;
    this.alt = this.#alt;
    this.trail = [];
  }

  #run(): void {
    if (this.#timer) return;
    let last = now();
    this.#timer = setInterval(() => {
      const t = now();
      const dt = (t - last) / 1000;
      last = t;
      // Server-side dead-man: an axis not renewed in time stops on its own.
      for (const axis of ['primary', 'secondary'] as Axis[]) {
        if (this.rate[axis] !== 0 && t - this.lastRenew[axis] > DEADMAN_MS) {
          this.rate = { ...this.rate, [axis]: 0 };
          this.deadmanStop = `Stopped by the server: no renewal for ${(DEADMAN_MS / 1000).toFixed(1)} s`;
        }
      }
      this.#az += this.rate.primary * dt;
      this.#alt += this.rate.secondary * dt;
      const moving = this.rate.primary !== 0 || this.rate.secondary !== 0;
      if (t - this.#lastPoll >= 200) {
        this.#lastPoll = t;
        this.az = this.#az;
        this.alt = this.#alt;
        if (moving) {
          const p = { daz: this.#az - this.origin.az, dalt: this.#alt - this.origin.alt };
          this.trail = [...this.trail.slice(-79), p];
        }
      }
      if (!moving && this.#timer) {
        this.az = this.#az;
        this.alt = this.#alt;
        clearInterval(this.#timer);
        this.#timer = null;
      }
    }, 40);
  }
}

/** A running exposure: progress is computed from real elapsed time by the caller. */
export class ExposureSim {
  seconds = $state(2);
  startedAt: number | null = $state(null);
  frame = $state(128);
  #timer: ReturnType<typeof setTimeout> | null = null;
  loop = $state(false);

  start(loop = false): void {
    this.loop = loop;
    this.#begin();
  }

  #begin(): void {
    this.startedAt = now();
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = setTimeout(() => {
      this.frame += 1;
      if (this.loop) this.#begin();
      else this.startedAt = null;
    }, this.seconds * 1000);
  }

  stop(): void {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = null;
    this.startedAt = null;
    this.loop = false;
  }
}

/** Frame clock for progress rings: re-renders at display rate only while something runs. */
export class Clock {
  t = $state(now());
  #raf = 0;
  #users = 0;

  use(): () => void {
    this.#users++;
    if (this.#users === 1) {
      const loop = () => {
        this.t = now();
        this.#raf = requestAnimationFrame(loop);
      };
      this.#raf = requestAnimationFrame(loop);
    }
    return () => {
      this.#users--;
      if (this.#users === 0) cancelAnimationFrame(this.#raf);
    };
  }
}

export const clock = new Clock();
