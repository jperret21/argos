/**
 * The prototype's instrument: a simulated clock, run, live view, autofocus
 * and field state, driven by the synthetic night (night.ts). It stands in
 * for the server's status record and events, so the workspace components
 * read the same kind of state they would read in the app.
 *
 * Truthfulness rules kept by the simulation:
 * - a value changes only when a frame (or a step) arrives, instantly;
 * - the last-frame age is a clock and ticks once a second;
 * - the run clock may be compressed (speed x20 by default, shown in the lab
 *   panel), but every time on screen is the SIMULATED UTC time, so ages,
 *   cadences and end times stay consistent with each other.
 *
 * Big series stay out of the deep proxy (stack-capabilities T1): the night
 * is a plain array, `delivered` is the reactive counter, `records` a raw
 * derived slice.
 */

import type { DecodedFrame } from '../../../lib/api/frames';
import { NAMED_STARS, TARGET_ID } from './field';
import { FrameSynth, serverFrames } from './frames';
import { buildAutofocus, buildNight, expectedEnd, medianCadence, RUN, type FrameRecord } from './night';
import { evaluate, type AttentionItem } from './rules';
import { alertTone, armAudio } from './sound';

export type Scene = 'framing' | 'focus' | 'field' | 'run' | 'run-healthy' | 'run-complete';
export type RunState = 'idle' | 'running' | 'pausing' | 'paused' | 'complete' | 'stopped';

export interface Measured {
  /** Peak ADU per measured star id, on the frame on screen. */
  peaks: Record<number, number>;
  clipped: number;
  sky: number;
  max: number;
  /** Worker time for the last synthetic frame (ms). */
  synthMs: number;
}

export interface LogLine {
  t: number;
  level: 'CMD' | 'INFO' | 'OK' | 'WARN' | 'ERROR';
  source: string;
  text: string;
}

const MEASURE = NAMED_STARS.map((s) => s.id);
const LIVE_EXPOSURE = 2;
const LIVE_INTERVAL_MS = 2600;
const AF_STEP_MS = 2200;

export class Sim {
  readonly night: FrameRecord[] = buildNight();
  readonly af = buildAutofocus();

  scene: Scene = $state('run');
  /** Simulated UTC, unix seconds. */
  now = $state(RUN.start);
  /** Simulated seconds per real second while a run is shown (0 freezes the clock). */
  speed = $state(20);
  delivered = $state(0);
  runState: RunState = $state('idle');
  live = $state(false);
  liveSeq = $state(1);
  afStep = $state(0);
  afRunning = $state(false);
  solved = $state(false);
  tracking = $state(true);
  parked = $state(false);
  frame: DecodedFrame | null = $state.raw(null);
  measured: Measured = $state.raw({ peaks: {}, clipped: 0, sky: 0, max: 0, synthMs: 0 });
  acked: ReadonlySet<string> = $state.raw(new Set());
  sound: 'off' | 'soft' | 'normal' = $state('normal');
  /** Web Audio needs a user gesture first (WebKit and Chromium policy). */
  soundArmed = $state(false);
  log: LogLine[] = $state.raw([]);
  source: 'synthetic' | 'server' = $state('synthetic');
  serverState = $state('');

  records: FrameRecord[] = $derived(this.night.slice(0, this.delivered));
  latest: FrameRecord | null = $derived(this.records.length ? this.records[this.records.length - 1] : null);
  running = $derived(this.runState === 'running' || this.runState === 'pausing');
  inRun = $derived(this.scene.startsWith('run'));
  cadence = $derived(medianCadence(this.records));
  endsAt = $derived(expectedEnd(this.records, RUN.frames));
  /** Seconds since the last frame (whole seconds: it is a clock). */
  lastAge = $derived(this.latest ? Math.max(0, Math.floor(this.now - this.latest.t)) : NaN);
  attention: AttentionItem[] = $derived(
    this.inRun ? evaluate(this.records, { now: this.now, running: this.running }) : [],
  );
  unacked = $derived(this.attention.filter((a) => a.level !== 'info' && !this.acked.has(a.id)));

  private synth: FrameSynth | null = null;
  private stopServer: (() => void) | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastTick = 0;
  private liveDue = 0;
  private afDue = 0;
  private renderingSeq = -1;
  private sounded = new Set<string>();

  start(scene: Scene, opts: { frame?: number; speed?: number; source?: 'synthetic' | 'server' } = {}): void {
    this.source = opts.source ?? 'synthetic';
    if (this.source === 'server') {
      this.stopServer = serverFrames(
        (f) => {
          this.frame = f;
          // Only what the frame header carries; star peaks are not measured here.
          this.measured = { peaks: {}, clipped: NaN, sky: f.header.stats.median, max: f.header.stats.max, synthMs: 0 };
        },
        (s) => (this.serverState = s),
      );
    } else {
      this.synth = new FrameSynth();
    }
    if (opts.speed !== undefined) this.speed = opts.speed;
    this.setScene(scene, opts.frame);
    this.lastTick = performance.now();
    this.timer = setInterval(() => this.tick(), 250);
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.synth?.dispose();
    this.stopServer?.();
  }

  setScene(scene: Scene, frame?: number): void {
    this.scene = scene;
    this.acked = new Set();
    this.sounded = new Set();
    const at = (h: number, m: number, s: number) => Date.UTC(2026, 8, 25, h, m, s) / 1000;
    this.log = seedLog(this.night);
    if (scene === 'framing') {
      this.runState = 'idle';
      this.delivered = 0;
      this.live = true;
      this.afRunning = false;
      this.solved = false;
      this.liveSeq = 128;
      this.now = at(19, 52, 10);
    } else if (scene === 'focus') {
      this.runState = 'idle';
      this.delivered = 0;
      this.live = true;
      this.afRunning = true;
      this.afStep = 7;
      this.solved = false;
      this.liveSeq = 212;
      this.now = at(19, 44, 31);
    } else if (scene === 'field') {
      this.runState = 'idle';
      this.delivered = 0;
      this.live = false;
      this.afRunning = false;
      this.solved = true;
      this.liveSeq = 236;
      this.now = at(19, 58, 47);
    } else {
      const n = scene === 'run-complete' ? RUN.frames : (frame ?? (scene === 'run-healthy' ? 120 : 160));
      this.delivered = Math.max(1, Math.min(RUN.frames, n));
      this.runState = this.delivered >= RUN.frames ? 'complete' : 'running';
      this.live = false;
      this.afRunning = false;
      this.solved = true;
      this.now = this.night[this.delivered - 1].t + 12;
      if (this.runState === 'complete') this.now += 140;
      // Rules that fired before the scene start are not "new": no sound.
      const fired = evaluate(this.records, { now: this.now, running: this.running });
      for (const a of fired) this.sounded.add(a.id);
      // The log as the server would have written it up to now.
      const lines: LogLine[] = [];
      for (const r of this.records.slice(-40)) {
        lines.push({ t: r.t + 6, level: 'OK', source: 'sequence', text: `Frame #${r.n} saved · HFD ${r.hfd.toFixed(2)} px · ${r.stars} stars` });
      }
      for (const a of fired) {
        if (a.level === 'info') continue;
        lines.push({ t: a.since + 7, level: a.level === 'critical' ? 'ERROR' : 'WARN', source: 'attention', text: `${a.rule}: ${a.title}` });
      }
      if (this.runState === 'complete') lines.push({ t: this.night[RUN.frames - 1].t + 9, level: 'OK', source: 'sequence', text: 'Run complete · 195 frames' });
      this.log = [...this.log, ...lines].sort((p, q) => p.t - q.t);
    }
    this.renderCurrent();
  }

  // -- Actions (what the server would do) --------------------------------------------

  ack(id: string): void {
    const next = new Set(this.acked);
    next.add(id);
    this.acked = next;
    const item = this.attention.find((a) => a.id === id);
    if (item) this.addLog('INFO', 'attention', `Acknowledged: ${item.rule} (${item.title})`);
  }

  ackAll(): void {
    const next = new Set(this.acked);
    for (const a of this.attention) next.add(a.id);
    this.acked = next;
  }

  pause(): void {
    if (this.runState !== 'running') return;
    this.runState = 'pausing';
    this.addLog('CMD', 'sequence', 'Pause requested: holding at the end of the current frame');
  }

  resume(): void {
    if (this.runState !== 'paused' && this.runState !== 'pausing') return;
    this.runState = 'running';
    this.addLog('CMD', 'sequence', 'Run resumed');
  }

  stop(): void {
    if (!this.running && this.runState !== 'paused') return;
    this.runState = 'stopped';
    this.addLog('WARN', 'sequence', `Run stopped by the observer at frame ${this.delivered} of ${RUN.frames}`);
  }

  setLive(on: boolean): void {
    this.live = on;
    this.addLog('CMD', 'camera', on ? 'Live view started (2.0 s, gain 80)' : 'Live view stopped');
  }

  park(): void {
    this.parked = true;
    this.tracking = false;
    this.addLog('CMD', 'mount', 'Park: the Seestar arm closes, tracking off');
  }

  unpark(): void {
    this.parked = false;
    this.addLog('CMD', 'mount', 'Unpark');
  }

  /** Call from a click: creates the audio context (autoplay policy). */
  armSound(): void {
    this.soundArmed = armAudio();
  }

  testSound(): void {
    this.armSound();
    if (this.soundArmed) alertTone('attention', this.sound === 'off' ? 'soft' : this.sound);
  }

  addLog(level: LogLine['level'], source: string, text: string): void {
    this.log = [...this.log, { t: this.now, level, source, text }].slice(-500);
  }

  // -- Clock -------------------------------------------------------------------------

  private tick(): void {
    const t = performance.now();
    const dt = (t - this.lastTick) / 1000;
    this.lastTick = t;
    if (this.speed <= 0) return;
    if (this.inRun) {
      this.now += dt * this.speed;
      if (this.runState === 'running' || this.runState === 'pausing') {
        let next = this.delivered;
        while (next < RUN.frames && this.night[next].t <= this.now) next++;
        if (next !== this.delivered) {
          this.delivered = next;
          const r = this.night[next - 1];
          this.addLog('OK', 'sequence', `Frame #${r.n} saved · HFD ${r.hfd.toFixed(2)} px · ${r.stars} stars`);
          if (this.runState === 'pausing') {
            this.runState = 'paused';
            this.addLog('INFO', 'sequence', `Paused after frame #${r.n}`);
          }
          if (next >= RUN.frames) {
            this.runState = 'complete';
            this.addLog('OK', 'sequence', 'Run complete');
          }
          this.renderCurrent();
        }
      }
      this.soundNew();
    } else {
      this.now += dt;
      if (this.live && t >= this.liveDue) {
        this.liveDue = t + LIVE_INTERVAL_MS;
        this.liveSeq++;
        this.renderCurrent();
      }
      if (this.afRunning && t >= this.afDue) {
        this.afDue = t + AF_STEP_MS;
        if (this.afStep < this.af.steps.length) this.afStep++;
        else {
          this.afRunning = false;
          this.addLog('OK', 'focuser', `Autofocus done · best ${this.af.best} steps · HFD ${this.af.bestHfd.toFixed(2)} px`);
        }
      }
    }
  }

  private soundNew(): void {
    for (const a of this.unacked) {
      if (this.sounded.has(a.id)) continue;
      this.sounded.add(a.id);
      this.addLog(a.level === 'critical' ? 'ERROR' : 'WARN', 'attention', `${a.rule}: ${a.title}`);
      if (this.soundArmed && this.sound !== 'off') alertTone(a.level, this.sound);
    }
  }

  /** HFD of what the camera sees now, by scene. */
  private currentHfd(): number {
    if (this.inRun) return this.latest?.hfd ?? 6.25;
    if (this.scene === 'focus') {
      const s = this.af.steps[Math.max(0, Math.min(this.af.steps.length - 1, this.afStep - 1))];
      return s.hfd;
    }
    return 6.3;
  }

  private renderCurrent(): void {
    if (!this.synth) return;
    const r = this.inRun ? this.latest : null;
    const seq = r ? r.n : this.liveSeq;
    if (seq === this.renderingSeq) return;
    this.renderingSeq = seq;
    const t = r ? r.t : this.now;
    void this.synth
      .render({
        seq,
        hfd: this.currentHfd(),
        sky: r ? r.sky : 1176,
        mags: { [TARGET_ID]: r ? r.target : 7.41 },
        exposure: r ? RUN.exposure : LIVE_EXPOSURE,
        t,
        measure: MEASURE,
      })
      .then((s) => {
        if (s.frame.header.seq !== this.renderingSeq) return; // superseded
        this.frame = s.frame;
        this.measured = {
          peaks: s.peaks,
          clipped: s.clipped,
          sky: s.frame.header.stats.median,
          max: s.frame.header.stats.max,
          synthMs: s.ms,
        };
      });
  }
}

function seedLog(night: FrameRecord[]): LogLine[] {
  const t0 = night[0].t - 1300;
  const L = (dt: number, level: LogLine['level'], source: string, text: string): LogLine => ({ t: t0 + dt, level, source, text });
  return [
    L(0, 'CMD', 'connection', 'Connect all · Seestar 192.168.1.42:32323'),
    L(3, 'OK', 'connection', 'Mount, camera, filter wheel, focuser ready'),
    L(4, 'INFO', 'mount', 'Mount clock 0.4 s from this computer'),
    L(120, 'CMD', 'mount', 'GoTo RR Lyr · 19h 25m 27.9s +42° 47′ 04″'),
    L(171, 'OK', 'mount', 'Slew complete · 0.08° from target'),
    L(290, 'CMD', 'focuser', 'Autofocus started · 14 steps of 50'),
    L(331, 'OK', 'focuser', 'Autofocus done · best 1305 steps · HFD 5.80 px'),
    L(600, 'CMD', 'field', 'Identify field (ASTAP)'),
    L(608, 'OK', 'field', 'Field identified · 2.39″/px · rotation 91.2° · target 1.5′ from centre'),
    L(780, 'INFO', 'photometry', 'Recommend comparisons: 6 of 11 candidates, B−V within 0.3 mag'),
    L(1290, 'CMD', 'sequence', 'Start · RR Lyr · 195 x 10 s · gain 80 · IR'),
  ];
}
