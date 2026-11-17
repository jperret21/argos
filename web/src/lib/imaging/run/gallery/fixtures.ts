/**
 * Synthetic run for the Run mode gallery (development only; wave 6b). The light curve comes
 * from the light-curve gallery's generator (an RRab-like target through the live path, the
 * store's real rules); the conditions follow the shape of the owner's RR Lyr 2026-09-25 run
 * as the science review's replay describes it (functional-spaces 4.10: HFD steady, then a
 * rise near frame 150 that fires the HFD rule three frames later). Invented numbers, never
 * presented as measurements; real-data checks use copies of real sessions.
 */

import { checkSequence, isoOf, type SequenceState } from '../../../api/sequence';
import { ConditionsStore } from '../../../charts/conditions.svelte';
import { makeRun, type Run } from '../../../charts/lightcurve/gallery/fixtures';
import type { RunAttention } from '../runband';

export const CADENCE = 52;
export const TOTAL = 300;

function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface RunFixture {
  run: Run;
  conditions: ConditionsStore;
  frameTimes: number[];
  /** Autofocus passes (unix s). */
  marks: number[];
  seq: SequenceState;
  items: RunAttention[];
  thresholds: Record<string, unknown>;
  /** "Now" for a live picture: a few seconds after the newest frame. */
  now: number;
}

/** A run of `n` frames; with `rise`, the HFD climbs from frame 150 and the rule holds from 152. */
export function makeRunFixture(opts: { n: number; seed?: number; rise?: boolean; state?: string; nowAfter?: number; cadence?: number } = { n: 180 }): RunFixture {
  const cadence = opts.cadence ?? CADENCE;
  const run = makeRun({ n: opts.n, seed: opts.seed ?? 21, cadence, flags: true, phase0: 0.35, pauseAt: 80, pauseS: 240 });
  const tgt = run.store.primary('target')!;
  const c = tgt.cols;
  const frameTimes = Array.from(c.t.subarray(0, c.n));
  const r = rng(opts.seed ?? 21);
  const conditions = new ConditionsStore(null);
  for (let i = 0; i < frameTimes.length; i++) {
    const rise = opts.rise && i >= 150 ? Math.min(1, (i - 150) / 12) : 0;
    const hfd = 2.08 + (r() - 0.5) * 0.18 + rise * 1.6;
    const stars = Math.round(3420 - Math.min(i, 300) * 0.9 + (r() - 0.5) * 60 - rise * 900);
    const sky = Math.round(812 + i * 0.35 + (r() - 0.5) * 6);
    conditions.ingest({ seq: i + 1, frame_seq: i + 1, t: new Date(frameTimes[i] * 1000).toISOString(), origin: 'sequence', exposure_s: 45, frame_type: 'light', filter: 'IR', hfd_px: hfd, fwhm_px: hfd * 1.18, star_count: stars, sky_adu: sky });
  }
  const first = frameTimes[0];
  const last = frameTimes[frameTimes.length - 1];
  const now = last + (opts.nowAfter ?? 9);
  const marks = frameTimes.length > 81 ? [first - 120, frameTimes[80] + 30] : [first - 120];
  const state = opts.state ?? 'running';
  const total = Math.max(TOTAL, frameTimes.length + 100);
  const seq = checkSequence({
    type: 'sequence',
    state,
    active: true,
    run_id: 'sim-run-1',
    run_root: null,
    object_name: 'RR Lyr (simulated)',
    plan: null,
    start_at_utc: null,
    started_utc: isoOf(first - 180),
    step_index: 0,
    step: null,
    pass_index: 1,
    repeat: 1,
    frames_done: frameTimes.length,
    frames_total: total,
    eta_s: Math.max(0, total - frameTimes.length) * cadence,
    end_utc: isoOf(last + Math.max(0, total - frameTimes.length) * cadence),
    current: { frame_type: 'Light', image_type: 'Light Frame', filter: 'IR', exposure_s: 45, gain: 80, index: frameTimes.length, step_index: 0, started_utc: isoOf(now - 5) },
    last_frame_utc: isoOf(last),
    last_saved_utc: isoOf(last + 48),
    last_frame_name: null,
    cadence_s: cadence,
    observed_cadence_s: cadence,
    next_autofocus: { reason: 'every_n', in_frames: 200 - frameTimes.length },
    autofocus_runs: 1,
    paused_by: null,
    end_action: 'Park mount',
    last_result: null,
    revision: 1,
  }) as SequenceState;
  const items: RunAttention[] = opts.rise && frameTimes.length > 152
    ? [{ id: 'hfd_rise-sim-1', rule: 'hfd_rise', ruleLabel: 'HFD rise', level: 'attention', since: frameTimes[152], cleared: null, active: true, runId: 'sim-run-1', values: null }]
    : [];
  return { run, conditions, frameTimes, marks, seq, items, thresholds: { hfd_factor: 1.5, star_factor: 0.7, baseline_frames: 20 }, now };
}
