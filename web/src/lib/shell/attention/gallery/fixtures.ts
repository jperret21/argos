/**
 * Deterministic fixtures for the wave 6b gallery (Watch, attention, wrap-up). SYNTHETIC:
 * the numbers echo the shape of the 2026-09-25 run described in functional-spaces §4.7 and
 * §4.10 (195 frames at a 51.5 s cadence, HFD baseline 8.65 px, the focus loss near frame
 * 150) to make the states readable; they are not measurements and nothing here is the
 * owner's data. The clock is the light-curve fixture's (makeRun), so Watch's curve and its
 * tiles agree. Nothing talks to a server.
 */

import { checkAttentionItem, type AttentionItem } from '../../../api/attention';
import type { SequenceResult } from '../../../api/sequence';
import { checkWrapUp } from '../../../run/wrapup/wrapup';
import { RUN_JD0, unixOfJd } from '../../../charts/lightcurve/gallery/fixtures';
import type { WatchData } from '../../watch';

/** The first sub: the light-curve fixture's (makeRun), so Watch's curve and its tiles share one clock. */
export const RUN_START = Math.round(unixOfJd(RUN_JD0));
export const CADENCE = 51.5;
/** Frame 150 (1-based) started: when the HFD rule fires in the illustration (as the replay of §4.10). */
export const T_HFD = RUN_START + 149 * CADENCE;
/** The gallery's clock: frame 160 was 12 s ago. */
export const NOW = RUN_START + 159 * CADENCE + 12;

const iso = (t: number) => new Date(Math.round(t) * 1000).toISOString().replace('.000Z', 'Z');
const hms = (t: number) => new Date(Math.floor(t) * 1000).toISOString().slice(11, 19);
/** Frame 160 started (the newest sub). */
const F160 = RUN_START + 159 * CADENCE;
/** The run's end (195 subs). */
export const RUN_END = RUN_START + 194 * CADENCE + 10;
const RUN = 'r20260925T200453Z';

/** One item as the server sends it (protocol.md AttentionItem), through the client's check. */
const wire = (v: Record<string, unknown>): AttentionItem =>
  checkAttentionItem({ run_id: RUN, kind: 'condition', active: true, acked: false, occurrences: 1, sound: true, repeat_s: null, cleared_utc: null, cleared_reason: null, ...v })!;

// Texts in the server's words (argos/server/attention.py), numbers from the series below.
export const ITEMS = {
  silence: wire({
    id: `no_frame-${RUN}-7`,
    rule: 'no_frame',
    cause: 'no_frame',
    name: 'No new frame',
    level: 'critical',
    title: `No new frame since ${hms(F160)} UTC (limit 112 s)`,
    short: `No frame since ${hms(F160).slice(0, 5)} UTC`,
    detail: `Last frame #160 started at ${hms(F160)} UTC; limit 112 s = max(2 × cadence 51.5 s, cadence + 60 s).`,
    since: iso(F160),
    frame: 160,
    action: { to: 'watch', label: 'Watch' },
    repeat_s: 30,
  }),
  hfd: wire({
    id: `hfd_rise-${RUN}-3`,
    rule: 'hfd_rise',
    cause: 'hfd_rise:TG',
    name: 'HFD rise',
    level: 'attention',
    title: 'HFD 18.8 px = 2.2× the first 20 frames',
    short: 'HFD 18.8 px · 2.2× baseline',
    detail: 'Rule: HFD above 1.5 × 8.63 px for 3 frames in a row (18.3, 18.6, 18.8 px, frames 158 … 160).',
    values: { hfd_px: 18.77, baseline_px: 8.63, factor: 1.5 },
    since: iso(T_HFD),
    frame: 150,
    action: { to: 'focus', label: 'Focus mode' },
  }),
  comps: wire({
    id: `comps_low-${RUN}-4`,
    rule: 'comps_low',
    cause: 'comps_low',
    name: 'Comparisons used',
    level: 'attention',
    title: '2 comparisons used for 3 frames',
    short: '2 comparisons used',
    detail: 'Rule: fewer than 3 comparisons kept after clipping, 3 frames in a row.',
    since: iso(RUN_START + 120 * CADENCE),
    frame: 121,
    action: { to: 'field', label: 'Field mode' },
    active: false,
    cleared_utc: iso(RUN_START + 126 * CADENCE),
    cleared_reason: 'resolved',
  }),
  starsAcked: wire({
    id: `star_drop-${RUN}-2`,
    rule: 'star_drop',
    cause: 'star_drop:TG',
    name: 'Star count drop',
    level: 'attention',
    title: '2\u202f010 stars = 0.68× the first 20 frames',
    short: '2\u202f010 stars · 0.68× baseline',
    detail: 'Rule: fewer than 0.7 × 2\u202f948 stars for 3 frames in a row.',
    since: iso(RUN_START + 89 * CADENCE),
    frame: 90,
    acked: true,
    acked_utc: iso(RUN_START + 92 * CADENCE),
    acked_by: 'observer',
    active: false,
    cleared_utc: iso(RUN_START + 95 * CADENCE),
    cleared_reason: 'resolved',
  }),
  started: wire({
    id: `run_started-${RUN}-1`,
    rule: 'run_started',
    cause: 'run_started',
    name: 'Run started',
    level: 'info',
    kind: 'event',
    title: `Run started · RR Lyr · 195 frames · ends about ${hms(RUN_END).slice(0, 5)} UTC`,
    short: 'Run started',
    detail: `Started at ${hms(RUN_START)} UTC.`,
    since: iso(RUN_START),
    frame: null,
    sound: false,
  }),
  tracker: wire({
    id: `tracker_lost-${RUN}-5`,
    rule: 'tracker_lost',
    cause: 'tracker_lost',
    name: 'Tracker lost',
    level: 'attention',
    title: 'No point on 3 frames in a row: the stars are not where the solution puts them',
    short: 'Tracker lost · 3 frames',
    detail: 'Rule: 3 Light frames in a row without a point: lock lost (S48). The field moved since the solve, or clouds; a new solution is due.',
    since: iso(RUN_START + 60 * CADENCE),
    frame: 61,
    action: { to: 'field', label: 'Field mode' },
  }),
  deviceLost: wire({
    id: `device_lost-${RUN}-6`,
    rule: 'device_lost',
    cause: 'device_lost:mount',
    name: 'Device lost',
    level: 'critical',
    title: 'Mount lost during the run',
    short: 'Mount lost',
    detail: 'Mount: not connected. The run goes on: frames keep coming, but nothing can follow the target.',
    since: iso(RUN_START + 140 * CADENCE),
    frame: 141,
    action: { to: 'devices', label: 'Devices' },
    repeat_s: 30,
  }),
};

export const LIST_ALL: AttentionItem[] = [ITEMS.silence, ITEMS.hfd, ITEMS.comps, ITEMS.starsAcked, ITEMS.started];

/** Smooth deterministic noise (no Math.random: stable captures). */
const wobble = (i: number, k: number) => Math.sin(i * 1.7 + k) * 0.5 + Math.sin(i * 0.37 + 2 * k) * 0.5;

/** HFD per sub: about 8.6 px, then the focus loss from frame 145 (frames 148-150 past 1.5 × the baseline: the rule fires at 150). */
export const HFD = Array.from({ length: 160 }, (_, i) => (i < 144 ? 8.6 + 0.35 * wobble(i, 1) : 8.6 + Math.min(10, (i - 143) * 1.4) + 0.4 * wobble(i, 2)));
export const STARS = Array.from({ length: 160 }, (_, i) => Math.round(2950 + 90 * wobble(i, 3) - (i > 148 ? 260 : 0)));
/** The same run without the focus loss (Watch with nothing open). */
const HFD_OK = Array.from({ length: 160 }, (_, i) => 8.6 + 0.35 * wobble(i, 1));
const STARS_OK = Array.from({ length: 160 }, (_, i) => Math.round(2950 + 90 * wobble(i, 3)));

const LINKS: WatchData['links'] = [
  { label: 'Seestar', tone: 'ok', word: 'connected' },
  { label: 'Server', tone: 'ok', word: 'linked' },
];

export const WATCH: WatchData = {
  state: 'running',
  object: 'RR Lyr',
  stepLine: 'step 1 of 1 · TG · 10.0 s',
  framesDone: 160,
  framesTotal: 195,
  lastFrameAt: NOW - 12,
  cadence: CADENCE,
  expecting: true,
  // The curve fixture's newest point and check σ (makeRun seed 3): Watch and its curve agree.
  target: { name: 'RR Lyr', mag: 11.832, err: 0.009, band: 'TG' },
  check: { name: '000-BCD-117', sigma: 0.01, n: 15 },
  comps: { used: 5, total: 6, verdict: 'consistent' },
  end: RUN_END,
  stars: STARS_OK,
  hfd: HFD_OK,
  hfdRef: 1.5 * 8.63,
  hfdFlag: false,
  alt: 52,
  altLimit: 30,
  altUntil: RUN_START + 5 * 3600,
  links: LINKS,
  computer: { state: 'held', method: 'caffeinate', message: null },
};

export const WATCH_HFD: WatchData = { ...WATCH, stars: STARS, hfd: HFD, hfdFlag: true };
export const WATCH_SILENT: WatchData = WATCH_HFD;
/** Watch's clock for the silence: frame 160 started 140 s ago (limit 112 s). */
export const NOW_SILENT = NOW + 128;
export const WATCH_PAUSED: WatchData = { ...WATCH, state: 'paused', expecting: false, target: { name: 'RR Lyr', mag: 11.853, err: 0.009, band: 'TG' }, check: null, lastFrameAt: NOW - 300 };
export const WATCH_IDLE: WatchData = {
  state: null,
  object: null,
  framesDone: null,
  framesTotal: null,
  lastFrameAt: null,
  cadence: null,
  expecting: false,
  target: null,
  check: null,
  comps: null,
  end: null,
  stars: [],
  hfd: [],
  alt: null,
  altLimit: 30,
  links: [
    { label: 'Seestar', tone: 'idle', word: 'not connected' },
    { label: 'Server', tone: 'ok', word: 'linked' },
  ],
};

// -- Wrap-up (protocol.md WrapUp, through the client's check) ---------------------------------

const ROOT = '/sessions/20260925T200453Z_RR_Lyr';
/** The wrap-up's own run (its card shows no curve): started 20:04:53 UTC. */
const WRAP_START = Date.UTC(2026, 8, 25, 20, 4, 53) / 1000;
const ENDED = '2026-09-25T22:54:20Z';

const wrapWire = (over: Record<string, unknown> = {}) => ({
  run_id: 'r1',
  object_name: 'RR Lyr',
  started_utc: '2026-09-25T20:04:53Z',
  ended_utc: ENDED,
  frames: { saved: 195, total: 195, by_type: { Light: 195 } },
  points: { target: 193, all: 1158, flagged: 3, frames_measured: 193, frames_skipped: { field_lost: 0, lock_lost: 2, other: 0 } },
  attention: { critical: 0, attention: 1, info: 2, items: [] },
  run_root: ROOT,
  run_folder: '20260925T200453Z_RR_Lyr',
  run_bytes: 3.04e9,
  mount: { connected: true, state: 'tracking', tracking: true, end_action: 'Nothing' },
  calibration: {
    darks: [{ exposure_s: 10, gain: 80, count: 20, existing: 0, estimate_s: 20 * 21.4 }],
    biases: [{ exposure_s: 0.01, gain: 80, count: 30, existing: 0, estimate_s: 30 * 11.41 }],
    overhead_s: 11.4,
    cadence_s: 51.5,
    dark_slot: true,
    note: null,
  },
  ...over,
});

export const WRAP = {
  completed: checkWrapUp(wrapWire())!,
  failed: checkWrapUp(
    wrapWire({
      ended_utc: '2026-09-25T22:43:32Z',
      frames: { saved: 160, total: 195 },
      points: { target: 158, all: 948, flagged: 0, frames_measured: 158, frames_skipped: { field_lost: 0, lock_lost: 2, other: 0 } },
      attention: { critical: 2, attention: 1, info: 1, items: [] },
      calibration: {
        darks: [
          { exposure_s: 10, gain: 80, count: 20, existing: 0, estimate_s: 20 * 21.4 },
          { exposure_s: 20, gain: 80, count: 20, existing: 0, estimate_s: 20 * 31.4 },
        ],
        biases: [{ exposure_s: 0.01, gain: 80, count: 30, existing: 0, estimate_s: 30 * 11.41 }],
        overhead_s: 11.4,
        cadence_s: 51.5,
        dark_slot: true,
        note: null,
      },
    }),
  )!,
  stopped: checkWrapUp(
    wrapWire({
      ended_utc: '2026-09-25T21:47:40Z',
      frames: { saved: 120, total: 195 },
      points: null,
      attention: { critical: 0, attention: 0, info: 2, items: [] },
      run_bytes: 1.87e9,
      mount: { connected: true, state: 'parked', tracking: false, end_action: 'Park mount' },
      // The server's note when the wheel has no Dark slot (argos/server/wrapup.py).
      calibration: {
        darks: [{ exposure_s: 10, gain: 80, count: 20, existing: 20, estimate_s: 20 * 21.4 }],
        biases: [{ exposure_s: 0.01, gain: 80, count: 30, existing: 0, estimate_s: 30 * 11.41 }],
        overhead_s: 11.4,
        cadence_s: 51.5,
        dark_slot: false,
        note: 'No Dark slot on a filter wheel: put the lid on the telescope before the darks and biases.',
      },
    }),
  )!,
};

export const RESULT = {
  completed: {
    completed: true,
    reason: null,
    message: null,
    frames_saved: 195,
    frames_total: 195,
    run_root: ROOT,
    started_t: WRAP_START,
    ended_utc: ENDED,
    ended_t: Date.UTC(2026, 8, 25, 22, 54, 20) / 1000,
    on_complete: 'Nothing',
  },
  failed: {
    completed: false,
    reason: 'camera_error',
    message: 'The camera did not return frame 161 within 140 s',
    frames_saved: 160,
    frames_total: 195,
    run_root: ROOT,
    started_t: WRAP_START,
    ended_utc: '2026-09-25T22:43:32Z',
    ended_t: Date.UTC(2026, 8, 25, 22, 43, 32) / 1000,
    on_complete: 'Nothing',
  },
  stopped: {
    completed: false,
    reason: 'stopped',
    message: null,
    frames_saved: 120,
    frames_total: 195,
    run_root: ROOT,
    started_t: WRAP_START,
    ended_utc: '2026-09-25T21:47:40Z',
    ended_t: Date.UTC(2026, 8, 25, 21, 47, 40) / 1000,
    on_complete: 'Park mount',
  },
} satisfies Record<string, SequenceResult>;
