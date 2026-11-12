/**
 * Deterministic fixtures for the wave 6a run-controls gallery (development only): sequence
 * records in every state (wire-shaped, checked by checkSequence as the store does), the run's
 * subs, preflight answers and an A65-shaped night.
 *
 * The night is computed here with Qt's fast altitude formula (sky_geometry.altitude_at) and
 * the Astronomical Almanac low-precision Sun, at a public city site (Paris), for XX Cyg and
 * HD 189733 on 2026-11-01. It stands in for the server's answer in the gallery only; the
 * server computes A65 itself, and the transit times below are illustrative, not predicted.
 */

import { checkPreflight, checkSequence, isoOf, type Preflight, type SequenceState, type TransitSpans, type Visibility } from '../../api/sequence';
import { aboveSpans, crossings } from '../../charts/visibility';

export const NOW = Date.UTC(2026, 10, 1, 21, 45, 0) / 1000;
const iso = isoOf;
const at = (h: number, m: number, s = 0) => Date.UTC(2026, 10, 1, h, m, s) / 1000;

// -- The night (A65 stand-in) ----------------------------------------------------------------------

const SITE = { lat: 48.8566, lon: 2.3522 };
const jd = (t: number) => t / 86400 + 2440587.5;

/** sky_geometry.altitude_at: GMST linear term, no nutation or refraction (≈ 0.1°). */
function altitudeAt(t: number, raHours: number, decDeg: number): number {
  const j = jd(t);
  const gmst = (((18.697374558 + 24.06570982441908 * (j - 2451545.0)) % 24) + 24) % 24;
  const lst = (((gmst + SITE.lon / 15) % 24) + 24) % 24;
  const ha = ((lst - raHours) * 15 * Math.PI) / 180;
  const lat = (SITE.lat * Math.PI) / 180;
  const dec = (decDeg * Math.PI) / 180;
  const s = Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(ha);
  return (Math.asin(Math.max(-1, Math.min(1, s))) * 180) / Math.PI;
}

/** Low-precision Sun (Astronomical Almanac, ≈ 0.01°): RA hours, Dec degrees. */
function sun(t: number): { ra: number; dec: number } {
  const n = jd(t) - 2451545.0;
  const r = Math.PI / 180;
  const L = 280.46 + 0.9856474 * n;
  const g = (357.528 + 0.9856003 * n) * r;
  const lam = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * r;
  const eps = (23.439 - 0.0000004 * n) * r;
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam)) / r / 15;
  return { ra: (ra + 24) % 24, dec: Math.asin(Math.sin(eps) * Math.sin(lam)) / r };
}

function night(raHours: number, decDeg: number, minAlt = 30): Visibility {
  const t0 = at(15, 0);
  const t1 = Date.UTC(2026, 10, 2, 7, 0) / 1000;
  const n = Math.round((t1 - t0) / 600) + 1;
  const t = new Float64Array(n);
  const alt = new Float64Array(n);
  const sa = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    t[i] = t0 + i * 600;
    alt[i] = Math.round(altitudeAt(t[i], raHours, decDeg) * 100) / 100;
    const s = sun(t[i]);
    sa[i] = altitudeAt(t[i], s.ra, s.dec);
  }
  const c = crossings(t, sa, -18);
  const dark = { start: c.find((x) => !x.rising)!.t, end: c.find((x) => x.rising)!.t };
  let pk = 0;
  for (let i = 0; i < n; i++) if (t[i] >= dark.start && t[i] <= dark.end && alt[i] > alt[pk]) pk = i;
  const windows = aboveSpans(t, alt, minAlt, dark);
  return { siteName: 'Paris', night: '2026-11-01', t, alt, sun: sa, peak: { t: t[pk], alt: alt[pk] }, window: windows[0] ?? null, windows, minAlt, dark, notes: [] };
}

/** XX Cyg (RRab), the variable-star run. */
export const VIS_VAR = night(20 + 3 / 60 + 15.6 / 3600, 32 + 52 / 60 + 1.8 / 3600);
/** HD 189733 (host of HD 189733 b), the transit plan. */
export const VIS_TRANSIT = night(20 + 0 / 60 + 43.7 / 3600, 22 + 42 / 60 + 39 / 3600);
/** The same night without the Sun samples: one wash outside the astronomical night. */
export const VIS_NO_SUN: Visibility = { ...VIS_VAR, sun: null };

export const TRANSIT: TransitSpans = { coverageStart: at(18, 40), ingress: at(19, 40), mid: at(20, 35), egress: at(21, 30), coverageEnd: at(22, 30) };
export const TRANSIT_RUN = { start: at(18, 40), end: at(22, 30) };

// -- The run's subs --------------------------------------------------------------------------------

/** DATE-OBS of the subs: 32 s cadence from 18:30:40, an autofocus at 20:00 (3 min), a pause 20:40-20:52. */
export function subTimes(until = NOW): number[] {
  const out: number[] = [];
  let t = at(18, 30, 40);
  while (t < until - 40) {
    out.push(t);
    t += 32;
    if (t > at(20, 0) && t < at(20, 3)) t = at(20, 3, 10);
    if (t > at(20, 40) && t < at(20, 52)) t = at(20, 52, 5);
  }
  return out;
}
export const FRAMES = subTimes();
export const AF_MARKS = [at(20, 0)];

// -- Sequence records ------------------------------------------------------------------------------

const STEP = { enabled: true, frame_type: 'Light', filter_name: 'LP', exposure_s: 30, gain: 80, count: 400, interval_s: 0, cadence_s: null, dither_every: 0 };
const PLAN = {
  schema: 2,
  object_name: 'XX Cyg',
  repeat: 1,
  autofocus_every_n: 200,
  autofocus_on_filter_change: false,
  on_complete: 'Park mount',
  base_dir: null,
  metadata: {},
  start_at_utc: null,
  steps: [{ ...STEP, filter_name: 'IR', count: 20 }, STEP, { ...STEP, frame_type: 'Dark', filter_name: 'Dark', count: 20, enabled: false }],
};
const ROOT = '/sessions/20261101T183040Z_XX_Cyg';
const last = FRAMES[FRAMES.length - 1];
/** The planned run on the timeline: its start and the server's end time. */
export const RUN_SPAN = { start: at(18, 30, 40), end: last + (420 - FRAMES.length) * 32 };

const base = {
  type: 'sequence',
  state: 'running',
  active: true,
  run_id: '20261101T183040Z',
  run_root: ROOT,
  object_name: 'XX Cyg',
  plan: PLAN,
  start_at_utc: null,
  started_utc: iso(at(18, 30, 40)),
  step_index: 1,
  step: STEP,
  pass_index: 1,
  repeat: 1,
  frames_done: FRAMES.length,
  frames_total: 420,
  eta_s: (420 - FRAMES.length) * 32,
  end_utc: iso(last + (420 - FRAMES.length) * 32),
  current: { frame_type: 'Light', image_type: 'Light Frame', filter: 'LP', exposure_s: 30, gain: 80, index: FRAMES.length - 19, step_index: 1, started_utc: iso(NOW - 8) },
  last_frame_utc: iso(last),
  last_saved_utc: iso(last + 31),
  last_frame_name: `XX_Cyg_LP_Light_e30000ms_g80_${String(FRAMES.length - 20).padStart(5, '0')}.fit`,
  cadence_s: 33,
  observed_cadence_s: 32,
  next_autofocus: { reason: 'every_n', in_frames: 200 - (FRAMES.length % 200) },
  autofocus_runs: 1,
  paused_by: null,
  end_action: 'Park mount',
  last_result: null,
  revision: 400,
};

const mk = (over: Record<string, unknown> = {}): SequenceState => checkSequence({ ...base, ...over }) as SequenceState;
const result = (r: Record<string, unknown>) => ({ frames_total: 420, run_root: ROOT, started_utc: base.started_utc, ended_utc: iso(at(21, 52)), ...r });

export const SEQ = {
  running: mk(),
  pausing: mk({ state: 'pausing' }),
  paused: mk({ state: 'paused', current: null, paused_by: 'observer' }),
  pausedMotion: mk({ state: 'paused', current: null, paused_by: 'motion', step: { ...STEP, cadence_s: 13, exposure_s: 10 } }),
  autofocus: mk({ state: 'autofocus', current: null }),
  stopping: mk({ state: 'stopping' }),
  late: mk({ last_frame_utc: iso(NOW - 150) }),
  scheduled: mk({
    state: 'waiting',
    run_id: null,
    run_root: null,
    started_utc: null,
    start_at_utc: iso(Date.UTC(2026, 10, 2, 0, 12) / 1000),
    step_index: null,
    step: null,
    pass_index: null,
    frames_done: 0,
    eta_s: null,
    current: null,
    last_frame_utc: null,
    last_saved_utc: null,
    last_frame_name: null,
    observed_cadence_s: null,
    end_utc: iso(Date.UTC(2026, 10, 2, 3, 2) / 1000),
  }),
  completed: mk({ state: 'idle', active: false, current: null, last_result: result({ completed: true, reason: 'completed', message: 'Sequence complete.', frames_saved: 420 }) }),
  stopped: mk({ state: 'idle', active: false, current: null, last_result: result({ completed: false, reason: 'stopped', message: 'Stopped by the observer.', frames_saved: FRAMES.length }) }),
  failed: mk({ state: 'idle', active: false, current: null, last_result: result({ completed: false, reason: 'camera_error', message: 'Exposure timeout after 45s', frames_saved: 212 }) }),
  cancelled: mk({ state: 'idle', active: false, run_root: null, current: null, last_result: result({ completed: false, reason: 'cancelled', message: 'The scheduled start was cancelled.', frames_saved: 0, run_root: null }) }),
  idle: mk({ state: 'idle', active: false, run_id: null, run_root: null, current: null, frames_done: 0, frames_total: 0 }),
};

export const LAST_SAVED = { seq: 412, t: last, name: base.last_frame_name as string, hfd: 2.14, fwhm: 2.61, stars: 143 };

// -- Preflight (A64) -------------------------------------------------------------------------------

const checks = (over: Record<string, { level: string; message: string }> = {}) =>
  [
    { id: 'run', level: 'ok', message: 'No run active.' },
    { id: 'camera', level: 'ok', message: 'Connected: Seestar S50 (IMX462, 1920 × 1080).' },
    { id: 'plan', level: 'ok', message: '420 frames, about 3h 51m.' },
    { id: 'start_at', level: 'ok', message: 'Starts now.' },
    { id: 'object', level: 'ok', message: 'XX Cyg.' },
    { id: 'mount', level: 'ok', message: 'Connected, tracking.' },
    { id: 'site', level: 'ok', message: 'Paris.' },
    { id: 'wheel', level: 'ok', message: 'IR, LP: every step’s slot exists.' },
    { id: 'focuser', level: 'ok', message: 'Autofocus every 200 frames with the focuser.' },
    { id: 'altitude', level: 'ok', message: 'XX Cyg stays above 30° until the planned end.' },
    { id: 'output', level: 'ok', message: 'The sessions folder is writable.' },
    { id: 'disk', level: 'ok', message: '1.7 GB needed, 212.4 GB free.' },
    { id: 'calibration', level: 'ok', message: 'Darks 20, biases 30 match the Light steps tonight.' },
    { id: 'lid', level: 'ok', message: 'Dark steps go through the wheel’s Dark slot.' },
  ].map((c) => ({ ...c, ...(over[c.id] ?? {}) }));

const pre = (over: Record<string, { level: string; message: string }> = {}, extra: Record<string, unknown> = {}): Preflight =>
  checkPreflight({ checks: checks(over), frames_total: 420, estimate_s: 13_860, start_utc: iso(NOW), end_utc: iso(NOW + 13_860), bytes_needed: 1.72e9, bytes_free: 212.4e9, ...extra }) as Preflight;

export const PRE = {
  ready: pre(),
  notes: pre({
    focuser: { level: 'note', message: 'Autofocus every 200 frames is planned and no focuser is connected: the passes are skipped.' },
    altitude: { level: 'note', message: 'XX Cyg dips below 30° from 22:41 UTC (planned end 23:00).' },
    calibration: { level: 'note', message: 'No darks for 30.00 s at gain 80 tonight; no flats for LP.' },
  }),
  blocked: pre(
    {
      camera: { level: 'block', message: 'Not connected. Connect the camera before running a sequence.' },
      disk: { level: 'block', message: '1.7 GB needed, 0.9 GB free on the sessions disk.' },
      mount: { level: 'note', message: 'Parked: Light frames would be taken with the arm closed.' },
    },
    { bytes_free: 0.9e9 },
  ),
};
