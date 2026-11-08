/**
 * Local fakes for the wave-3 gallery (development only): a focuser with
 * autofocus, a filter wheel and a mount jog that behave like the server's
 * records of argos/server/protocol.md (wave 3) at realistic timing, so the
 * "Live" rows run the real instruments without a server.
 *
 * - Focuser (A34-A36): 900 steps/s, position POLLED every 500 ms while
 *   moving (the needle jumps); a move or step while moving is queued and sent
 *   as one move (D9); Go to outside 0…MaxStep is refused (400 words, never
 *   clamped); a step past an end is clamped and reported; autofocus 9 coarse
 *   + 4 fine + 1 verify samples at 0.9 s, Stop AF returns to the start
 *   ("stopping" meanwhile, S23), Halt during autofocus ends it where it is.
 * - Filter wheel (A28): 1.4 s per move; a move to "LP" is refused by the
 *   "driver" (H9: the record reports the slot it is really on).
 * - Mount jog (A30): per-axis rates, the server dead-man stops an axis not
 *   renewed within 1 s (last_stop), pointing polled at 5 Hz; `linkUp =
 *   false` drops the renewals (a simulated outage).
 */

import type {
  AutofocusSample,
  AutofocusView,
  FilterWheelView,
  FocuserCommandResult,
  FocuserView,
  JogAxis,
  MountJogView,
} from '../../imaging/instruments/types';
import type { JogTransport } from '../../imaging/instruments/jog';

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const iso = () => new Date().toISOString();

export class FakeFocuser {
  readonly maxStep = 100_000;
  readonly speed = 900;
  rec: FocuserView = $state({
    state: 'idle',
    name: 'Seestar focuser (gallery)',
    position: 12_450,
    target: 12_450,
    queued: null,
    temperature_c: 12.3,
    max_step: 100_000,
    max_increment: 100_000,
    absolute: true,
    locked_by: null,
  });
  af: AutofocusView = $state({ state: 'idle', run: 0 });

  #true = 12_450;
  #timer: ReturnType<typeof setInterval> | null = null;
  #lastPoll = 0;
  #cancel: 'stop' | 'halt' | null = null;
  #afRunning = false;

  #moveTo(p: number): void {
    this.rec.target = p;
    this.rec.state = 'moving';
    if (this.#timer) return;
    this.#lastPoll = performance.now();
    let last = performance.now();
    this.#timer = setInterval(() => {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      const goal = this.rec.target ?? this.#true;
      const d = goal - this.#true;
      const stepN = Math.sign(d) * Math.min(Math.abs(d), this.speed * dt);
      this.#true += stepN;
      const arrived = Math.abs(goal - this.#true) < 0.5;
      if (now - this.#lastPoll >= 500 || arrived) {
        this.#lastPoll = now;
        this.rec.position = Math.round(this.#true);
      }
      if (arrived) {
        this.#true = goal;
        this.rec.position = goal;
        if (this.rec.queued !== null && this.rec.queued !== undefined) {
          const q = this.rec.queued;
          this.rec.queued = null;
          this.rec.target = q; // the queued taps, sent as one move
          return;
        }
        this.rec.state = 'idle';
        if (this.#timer) clearInterval(this.#timer);
        this.#timer = null;
      }
    }, 50);
  }

  #refuseManual(): void {
    if (this.#afRunning || this.af.state === 'stopping') throw new Error('Autofocus owns the focuser.');
    if (this.rec.state === 'disconnected') throw new Error('The focuser is not connected.');
  }

  async step(delta: number): Promise<FocuserCommandResult> {
    await wait(60);
    this.#refuseManual();
    const base = this.rec.queued ?? this.rec.target ?? this.rec.position ?? 0;
    const want = base + delta;
    const p = Math.min(this.maxStep, Math.max(0, want));
    const clamped = p !== want;
    if (this.rec.state === 'moving') {
      this.rec.queued = p;
      return { focuser: { ...this.rec }, requested: p, sent: null, clamped, queued: true };
    }
    this.#moveTo(p);
    return { focuser: { ...this.rec }, requested: p, sent: p, clamped, queued: false };
  }

  async move(position: number): Promise<FocuserCommandResult> {
    await wait(80);
    this.#refuseManual();
    if (position < 0 || position > this.maxStep) {
      throw new Error(`Position ${position} is outside 0–${this.maxStep} (the focuser's MaxStep).`);
    }
    if (this.rec.state === 'moving') {
      this.rec.queued = position;
      return { focuser: { ...this.rec }, requested: position, sent: null, clamped: false, queued: true };
    }
    this.#moveTo(position);
    return { focuser: { ...this.rec }, requested: position, sent: position, clamped: false, queued: false };
  }

  async halt(): Promise<void> {
    await wait(60);
    if (this.#timer) clearInterval(this.#timer);
    this.#timer = null;
    this.rec.position = Math.round(this.#true);
    this.rec.target = this.rec.position;
    this.rec.queued = null;
    this.rec.state = 'idle';
    if (this.#afRunning) this.#cancel = 'halt';
  }

  async #moveAndWait(p: number): Promise<void> {
    this.#moveTo(p);
    while (this.rec.state === 'moving') await wait(100);
  }

  async startAutofocus(): Promise<void> {
    await wait(120);
    if (this.#afRunning) throw new Error('Autofocus is already running.');
    this.#afRunning = true;
    this.#cancel = null;
    const start = this.rec.position ?? 0;
    const best = 12_380;
    const samples: AutofocusSample[] = [];
    const total = 14;
    this.af = {
      state: 'running',
      stage: 'coarse',
      step: 0,
      total,
      params: { exposure_s: 2, gain: 80, half_range: 2000, num_steps: 9 },
      start_position: start,
      samples,
      best: null,
      run: (this.af.run ?? 0) + 1,
      started_utc: iso(),
    };
    this.rec.locked_by = 'autofocus';
    const hfd = (p: number) => Math.round((2.1 + Math.abs(p - best) / 520 + (Math.random() - 0.5) * 0.12) * 100) / 100;
    const plan: { p: number; stage: 'coarse' | 'fine' | 'verify' }[] = [];
    for (let i = 0; i < 9; i++) plan.push({ p: start - 2000 + i * 500, stage: 'coarse' });
    for (const d of [-375, -125, 125, 375]) plan.push({ p: best + d, stage: 'fine' });
    plan.push({ p: best, stage: 'verify' });
    for (const s of plan) {
      if (this.#cancel) break;
      await this.#moveAndWait(s.p);
      if (this.#cancel) break;
      await wait(500);
      samples.push({ position: s.p, hfd_px: hfd(s.p), stage: s.stage, t: iso() });
      this.af = { ...this.af, stage: s.stage, step: samples.length, samples: [...samples] };
    }
    const cancel = this.#cancel;
    if (cancel === 'stop') {
      this.af = { ...this.af, state: 'stopping', stage: 'returning' };
      await this.#moveAndWait(start);
      this.af = { ...this.af, state: 'cancelled', stage: null, position: start, message: `Returned to ${start}.`, ended_utc: iso() };
    } else if (cancel === 'halt') {
      const at = this.rec.position;
      this.af = { ...this.af, state: 'cancelled', stage: null, position: at, message: `Halted at ${at}: focus left there.`, ended_utc: iso() };
    } else {
      const last = samples[samples.length - 1];
      this.af = {
        ...this.af,
        state: 'done',
        stage: null,
        position: best,
        best: { position: best, hfd_px: last?.hfd_px ?? null, fitted_hfd_px: 2.08, method: 'parabola' },
        ended_utc: iso(),
      };
    }
    this.rec.locked_by = null;
    this.#afRunning = false;
    this.#cancel = null;
  }

  async stopAutofocus(): Promise<void> {
    await wait(80);
    if (!this.#afRunning) return;
    this.#cancel = 'stop';
    if (this.#timer) clearInterval(this.#timer);
    this.#timer = null;
    this.rec.state = 'idle';
    this.af = { ...this.af, state: 'stopping', stage: 'returning' };
  }

  dispose(): void {
    if (this.#timer) clearInterval(this.#timer);
    this.#cancel = 'halt';
  }
}

export class FakeWheel {
  rec: FilterWheelView = $state({
    state: 'idle',
    name: 'Seestar filter wheel (gallery)',
    slots: ['Dark', 'IR', 'LP'],
    dark_slot: true,
    position: 1,
    slot: 'IR',
    target: null,
    message: null,
  });

  async select(name: string): Promise<FilterWheelView> {
    await wait(80);
    const i = this.rec.slots.findIndex((s) => s.toLowerCase() === name.toLowerCase());
    if (i < 0) throw new Error(`No wheel slot named '${name}' (slots: ${this.rec.slots.join(', ')})`);
    if (this.rec.state === 'moving') throw new Error('The wheel is already moving.');
    const from = this.rec.slot;
    this.rec = { ...this.rec, state: 'moving', position: null, slot: null, target: this.rec.slots[i], message: null };
    setTimeout(() => {
      if (name.toUpperCase() === 'LP') {
        // H9: a refused move reads the wheel back and reports where it is.
        const back = this.rec.slots.indexOf(from ?? 'IR');
        this.rec = { ...this.rec, state: 'idle', position: back, slot: from, target: null, message: 'Move to LP refused by the driver.' };
        return;
      }
      this.rec = { ...this.rec, state: 'idle', position: i, slot: this.rec.slots[i], target: null, settled_utc: iso() };
    }, 1400);
    return this.rec;
  }
}

export class FakeMount {
  jog: MountJogView = $state({ primary: 0, secondary: 0, stop_pending: [], max_rate_deg_s: 5, deadman_s: 1, last_stop: null });
  pointing = $state({ alt_deg: 41.27 as number | null, az_deg: 182.3 as number | null });
  /** false: renewals are lost (a simulated outage); the dead-man then acts. */
  linkUp = $state(true);
  #alt = 41.27;
  #az = 182.3;
  #renewed: Record<JogAxis, number> = { primary: 0, secondary: 0 };
  #lastSeq = 0;
  #tick: ReturnType<typeof setInterval> | null = null;
  #lastPoll = 0;

  readonly transport: JogTransport = {
    start: async (axis, rate, seq) => {
      await wait(30);
      if (!this.linkUp) throw new Error('No answer from the ARGOS server');
      if (seq < this.#lastSeq) return this.jog; // an older command is ignored
      this.#lastSeq = seq;
      this.jog = { ...this.jog, [axis]: rate };
      this.#renewed[axis] = performance.now();
      this.#run();
      return this.jog;
    },
    stop: async (axis, seq) => {
      await wait(30);
      if (!this.linkUp) throw new Error('No answer from the ARGOS server');
      if (seq < this.#lastSeq) return this.jog;
      this.#lastSeq = seq;
      if (axis === null) this.jog = { ...this.jog, primary: 0, secondary: 0, last_stop: { axis: 'both', reason: 'client stop', t: iso() } };
      else this.jog = { ...this.jog, [axis]: 0, last_stop: { axis, reason: 'client stop', t: iso() } };
      return this.jog;
    },
    socketStop: () => {
      this.jog = { ...this.jog, primary: 0, secondary: 0, last_stop: { axis: 'both', reason: 'jog_stop message', t: iso() } };
    },
  };

  #run(): void {
    if (this.#tick) return;
    let last = performance.now();
    this.#tick = setInterval(() => {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      for (const a of ['primary', 'secondary'] as JogAxis[]) {
        if (this.jog[a] !== 0 && now - this.#renewed[a] > 1000) {
          this.jog = { ...this.jog, [a]: 0, last_stop: { axis: a, reason: 'no renewal for 1.0 s', t: iso() } };
        }
      }
      this.#az = (this.#az + this.jog.primary * dt + 360) % 360;
      this.#alt = Math.max(-5, Math.min(90, this.#alt + this.jog.secondary * dt));
      if (now - this.#lastPoll >= 200) {
        this.#lastPoll = now;
        this.pointing = { alt_deg: Math.round(this.#alt * 1000) / 1000, az_deg: Math.round(this.#az * 1000) / 1000 };
      }
      if (this.jog.primary === 0 && this.jog.secondary === 0 && this.#tick) {
        clearInterval(this.#tick);
        this.#tick = null;
      }
    }, 50);
  }

  dispose(): void {
    if (this.#tick) clearInterval(this.#tick);
  }
}
