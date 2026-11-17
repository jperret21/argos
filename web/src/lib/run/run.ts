/**
 * The run in words (wave 6a; spec 06 sections 2.3.2, 2.3.5, 2.3.6, 2.4; PROPOSAL 3.1 Run
 * card): state chip, run strip line, outcome, readiness, the Stop confirmation, the
 * scheduled start (Q-P2), the next autofocus and the end time. Pure functions of the
 * server's records (api/sequence.ts), shared by the run strip, the transport, the Run card
 * and, in 6b, Watch and the status bar.
 *
 * Rules: every state carries a word (never colour alone); the server's sentences are
 * shown verbatim; a time is UTC and named; nothing is clamped or guessed: a value the
 * server did not send is a dash, an out-of-range input is refused in words.
 */

import type { PreflightItem, PreflightLevel, SequenceResult, SequenceState, SequenceStep } from '../api/sequence';
import type { Tone } from '../app/status';
import { DASH, fixed, seconds } from '../format/number';
import { clockUtc, duration, utcDate } from '../format/time';

/** A run owns the camera (Pause / Stop apply; Start and plan edits are refused). */
export const ACTIVE: ReadonlySet<string> = new Set(['running', 'pausing', 'paused', 'autofocus', 'stopping']);

export const isActive = (s: SequenceState | null): boolean => !!s && ACTIVE.has(s.state);
/** Active, or waiting for its scheduled start. */
export const isEngaged = (s: SequenceState | null): boolean => !!s && (ACTIVE.has(s.state) || s.state === 'waiting');

export type Outcome = 'completed' | 'stopped' | 'failed';

/** Ended by the observer: Stop during the run, or a scheduled start cancelled. */
const BY_OBSERVER: ReadonlySet<string> = new Set(['stopped', 'cancelled']);

/**
 * How a run ended: completed; stopped by the observer (Stop, or a scheduled start
 * cancelled); or ended by the system (camera_error, device_lost, wheel_error, save_error,
 * autofocus_timeout, refused, shutdown…: the server's sentence says why).
 */
export function outcomeOf(r: SequenceResult): Outcome {
  if (r.completed) return 'completed';
  if (r.reason && BY_OBSERVER.has(r.reason)) return 'stopped';
  return r.reason || r.message ? 'failed' : 'stopped';
}

const frames = (n: number) => `${n} frame${n === 1 ? '' : 's'}`;

/** On-complete action in words ("Park mount" -> "park"); null for "Nothing". */
export function endAction(onComplete: string | null): string | null {
  if (!onComplete || onComplete === 'Nothing') return null;
  return onComplete.replace(/ mount$/i, '').toLowerCase();
}

/** The outcome line (spec 2.4 Finished): it stays until dismissed. */
export function outcomeText(r: SequenceResult): string {
  const at = r.ended_t !== null ? ` · ${clockUtc(r.ended_t, false)} UTC` : '';
  const why = r.message ?? (r.reason ? r.reason.replace(/_/g, ' ') : 'the server gave no reason');
  switch (outcomeOf(r)) {
    case 'completed': {
      const act = endAction(r.on_complete);
      return `Sequence complete · ${frames(r.frames_saved)}${at}${act ? ` · end of run: ${act}` : ''}`;
    }
    case 'stopped':
      return r.reason === 'cancelled' ? `Scheduled start cancelled${at}` : `Stopped by the observer after ${frames(r.frames_saved)}${at}`;
    case 'failed':
      return r.reason === 'refused' ? `Not started: ${why}${at}` : `Stopped: ${why} · ${frames(r.frames_saved)} saved${at}`;
  }
}

export interface Chip {
  tone: Tone;
  label: string;
}

/** The state chip (Plan toolbar, Run card header, the status bar in 6b): a word always. */
export function stateChip(s: SequenceState | null): Chip {
  if (!s) return { tone: 'idle', label: 'No link' };
  switch (s.state) {
    case 'waiting':
    case 'scheduled':
      // The time is the strip's and the card's line ("Starts at 17:34 UTC, in 2m 55s"): the chip
      // says the state only (design review W6a: the scheduled strip repeated itself).
      return { tone: 'busy', label: 'Scheduled' };
    case 'running':
      return { tone: 'busy', label: 'Running' };
    case 'pausing':
      return { tone: 'busy', label: 'Pausing after this frame…' };
    case 'paused':
      return { tone: 'idle', label: 'Paused' };
    case 'autofocus':
      return { tone: 'busy', label: 'Autofocus' };
    case 'stopping':
      return { tone: 'busy', label: 'Stopping…' };
    case 'idle': {
      if (!s.last_result) return { tone: 'idle', label: 'No run' };
      const o = outcomeOf(s.last_result);
      if (o === 'completed') return { tone: 'ok', label: 'Complete' };
      if (o === 'stopped') return { tone: 'idle', label: s.last_result.reason === 'cancelled' ? 'Cancelled' : 'Stopped' };
      return { tone: 'error', label: s.last_result.reason === 'refused' ? 'Not started' : 'Failed' };
    }
  }
}

/** "10 × 30.00 s LP" (Dark and Bias: the type, the wheel's opaque slot is implied). */
export function stepText(st: SequenceStep): string {
  const what = st.frame_type === 'Light' || st.frame_type === 'Flat' ? `${st.frame_type === 'Flat' ? 'Flat ' : ''}${st.filter_name || DASH}` : st.frame_type;
  return `${st.count} × ${seconds(st.exposure_s)} ${what}`; // Observe's exposure format (BRAND 5)
}

/** When the run should end: the server's end time, else its time left from the newest frame (an anchor that does not drift between frames). */
export function endAt(s: SequenceState, now: number): number | null {
  if (s.end_t !== null) return s.end_t;
  if (s.eta_s === null) return null;
  // Paused: nothing progresses, so the end moves with the clock ("if resumed now"), never a
  // frozen time counting down (design review W6a).
  if (s.state === 'paused') return now + s.eta_s;
  return (s.last_frame_t ?? s.started_t ?? now) + s.eta_s;
}

/**
 * The end from the cadence when the server's has passed while frames remain (null otherwise).
 * The server's estimate (elapsed ÷ frames × frames left, from the newest save) lags the first
 * frames of a run with an interval: at 1 / 4 it read "in 0 s" with 3 frames to go (wave 6b
 * design review). The frames left × the cadence, from the newest frame's start; never before now.
 */
export function cadenceEnd(s: SequenceState, now: number, cadence: number | null, lastAt: number | null): number | null {
  if (s.state === 'paused' || cadence === null || !(cadence > 0)) return null;
  const end = endAt(s, now);
  const remaining = Math.max(0, s.frames_total - s.frames_done);
  if (end === null || end > now || remaining === 0) return null;
  return Math.max(now, (lastAt ?? now) + remaining * cadence);
}

/** Time left until the end, from now (never negative: a late run says "overdue" elsewhere). */
export function timeLeft(s: SequenceState, now: number): number | null {
  const e = endAt(s, now);
  return e === null ? null : Math.max(0, e - now);
}

/**
 * The run strip's first line (spec 2.3.2): "Step 2/3 · 10 × 30.00 s LP · pass 1/2 ·
 * frame 37/50 · ETA 6m 30s · ends ≈ 21:52 UTC"; the state's own words lead when they add
 * to the chip (paused: after which frame, why, the cadence; autofocus; stopping; scheduled). A pause on a cadence step
 * says the cadence is broken (06 P16). `afStep`: the autofocus sweep's progress (A36).
 */
export function stripLine(s: SequenceState, now: number, afStep: { done: number; total: number } | null = null): string {
  const bits: string[] = [];
  if (s.state === 'waiting') {
    const at = s.start_at_t;
    bits.push(at !== null ? `Starts at ${clockUtc(at, false)} UTC${at - now > 0 ? `, in ${duration(at - now)}` : ''}` : 'Waiting for the scheduled start');
    bits.push(`${frames(s.frames_total)} planned`);
    return bits.join(' · ');
  }
  const cadence = s.step?.cadence_s ?? null;
  if (s.state === 'paused') bits.push(`Paused after frame ${s.frames_done}${s.paused_by === 'motion' ? ' for a mount motion' : ''}${cadence !== null ? ` · ${fixed(cadence, 1)} s cadence broken` : ''}`);
  if (s.state === 'autofocus') bits.push(afStep ? `Autofocus pass (step ${afStep.done}/${afStep.total})` : 'Autofocus pass');
  if (s.state === 'stopping') bits.push('Stopping: the frame being exposed is discarded');
  if (s.step_index !== null) bits.push(`Step ${s.step_index + 1}${s.steps_total ? `/${s.steps_total}` : ''}`);
  if (s.step) bits.push(stepText(s.step));
  if (s.pass_index !== null && s.repeat !== null && s.repeat > 1) bits.push(`pass ${s.pass_index}/${s.repeat}`);
  bits.push(`frame ${s.frames_done}/${s.frames_total}`);
  const left = timeLeft(s, now);
  const end = endAt(s, now);
  if (left !== null && end !== null && s.state !== 'stopping') bits.push(`ETA ${duration(left)} · ends ≈ ${clockUtc(end, false)} UTC`);
  return bits.join(' · ');
}

/** The next periodic autofocus in words ("in 7 frames (≈ 3m 44s)", "off", "—"). */
export function nextAutofocus(s: SequenceState, cadence: number | null): string {
  const r = nextAutofocusParts(s, cadence);
  return r.unit ? `in ${r.v} ${r.unit}${r.note ? ` (${r.note})` : ''}` : (r.note ?? r.v);
}

/** The same as a readout: value, unit and note ("7" frames, "≈ 3m 44s"). */
export function nextAutofocusParts(s: SequenceState, cadence: number | null): { v: string; unit?: string; note?: string } {
  if (s.autofocus_every_n === 0) return { v: 'off' };
  if (s.next_autofocus_in === null) return { v: DASH };
  if (s.next_autofocus_in <= 0) return { v: 'next', note: 'before the next frame' };
  const n = s.next_autofocus_in;
  return { v: String(n), unit: n === 1 ? 'frame' : 'frames', note: cadence ? `≈ ${duration(n * cadence)}` : undefined };
}

/**
 * How long a `pause_run` mount motion may wait for its answer. The server holds the request
 * until the run pauses (sequence.py `_pause_bound`: the sub in progress + 60 s, or 360 s in a
 * mid-run autofocus), then moves: giving up at the client's default 15 s reported a failure
 * the mount then belied by slewing (technical review W6a), and a second click sent a second
 * motion.
 */
export function pauseRunTimeoutMs(s: SequenceState | null): number {
  if (s?.state === 'autofocus') return 400_000;
  const exposure = s?.current?.exposure_s ?? s?.step?.exposure_s ?? 0;
  return Math.max(15_000, Math.ceil((exposure + 75) * 1000));
}

/** The folder name of a run root ("…/20261101T204502Z_T_CrB" -> "20261101T204502Z_T_CrB"). */
export const folderName = (p: string | null): string | null => (p ? (p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p) : null);

/** The Stop confirmation (spec 2.3.6): what is discarded, what is kept, where. */
export function stopDialog(s: SequenceState): { title: string; message: string; confirm: string; cancel: string } {
  if (s.state === 'waiting') {
    return {
      title: 'Cancel the scheduled start?',
      message: `The sequence will not start${s.start_at_t !== null ? ` at ${clockUtc(s.start_at_t, false)} UTC` : ''}. The plan stays as it is.`,
      confirm: 'Cancel the start',
      cancel: 'Keep it scheduled',
    };
  }
  const parts: string[] = [];
  if (s.current && s.state !== 'paused') parts.push(`The current ${seconds(s.current.exposure_s)} exposure is discarded.`);
  const where = folderName(s.run_root);
  if (s.frames_done === 0) parts.push(`No frame is saved yet${where ? `; the run folder ${where} stays` : ''}.`);
  else parts.push(`${s.frames_done} of ${frames(s.frames_total)} ${s.frames_done === 1 ? 'is' : 'are'} saved${where ? ` in ${where}` : ''}.`);
  const act = endAction(s.on_complete);
  if (act) parts.push(`The end-of-run action (${act}) is not applied.`);
  return { title: 'Stop the sequence?', message: parts.join(' '), confirm: 'Stop', cancel: 'Keep running' };
}

// -- Preflight (A64) and readiness ----------------------------------------------------------------

const CHECK_NAMES: Record<string, string> = {
  camera: 'Camera',
  object: 'Object name',
  mount: 'Mount',
  site: 'Observing site',
  wheel: 'Filter wheel',
  filterwheel: 'Filter wheel',
  focuser: 'Focuser',
  altitude: 'Altitude',
  output: 'Output folder',
  disk: 'Disk space',
  calibration: 'Calibration',
  // The server's `lid` check is the telescope's: darks through the wheel's Dark slot, or the
  // tube covered (design review W6a); the computer's lid is `sleep`.
  lid: 'Dark frames',
  sleep: 'Computer sleep',
  plan: 'Plan',
  run: 'Run',
  start_at: 'Start time',
  keep_awake: 'Keep awake',
};

/** The check's name: the server's label, else the known id's, else the id itself. Ids are unique
 *  per answer: a plan issue is `plan:<code>:<step>`, a repeated id `<id>:<n>`; the name is the base's. */
export const checkName = (it: PreflightItem): string => {
  const base = it.id.split(':')[0];
  return it.label ?? CHECK_NAMES[base] ?? base.replace(/_/g, ' ');
};

/** A long absolute path in a check's words, elided in the middle ("…/w6a/integ/sessions"). */
export function checkMessage(it: PreflightItem): string {
  return it.message.replace(/(\/[^\s/]+){4,}\/?/g, (path) => {
    if (path.length <= 32) return path;
    const parts = path.replace(/\/$/, '').split('/');
    return `…/${parts.slice(-2).join('/')}`;
  });
}

export const LEVEL_WORD: Record<PreflightLevel, string> = { ok: 'OK', note: 'Note', block: 'Blocks' };

/** Blocks first, then notes, then the rest, each in the server's order. */
export function sortPreflight(items: readonly PreflightItem[]): PreflightItem[] {
  const rank = { block: 0, note: 1, ok: 2 } as const;
  return items.map((it, i) => ({ it, i })).sort((a, b) => rank[a.it.level] - rank[b.it.level] || a.i - b.i).map((x) => x.it);
}

export interface Readiness {
  level: PreflightLevel | 'unknown';
  label: string;
}

/** The checks shown: during a run, the run's own "a sequence is running" is not a blocker to report. */
export function runChecks(items: readonly PreflightItem[] | null, running = false): readonly PreflightItem[] | null {
  return items && running ? items.filter((i) => i.id !== 'run') : items;
}

/**
 * The readiness chip (spec 2.3.5): "Ready" | "Ready · 1 note" | "Blocked · camera" |
 * "Blocked · camera and 1 more". During a run (the server then checks the running plan) it says
 * the run's state (spec 2.3.2: `running` is stateChip's word, "Running", "Paused", "Starts 17:34
 * UTC"; `true` reads "Running"), never "Blocked · run": "Running" | "Paused · 1 note" |
 * "Running · camera".
 */
export function readiness(items: readonly PreflightItem[] | null, running: boolean | string = false, draftStart: { t: number; now: number } | null = null): Readiness {
  const engaged = running !== false && running !== '';
  const word = typeof running === 'string' ? running : 'Running';
  const list = runChecks(items, engaged);
  if (!list) return { level: 'unknown', label: 'Not checked' };
  const blocks = list.filter((i) => i.level === 'block');
  // A deliberate start more than 24 h ahead is a schedule, not a fault (wave 6b design
  // review): a note, with when Start opens. Any other block still says "Blocked".
  if (!engaged && draftStart && draftStart.t - draftStart.now > START_AHEAD_MAX_S && blocks.length && blocks.every((i) => i.id === 'start_at')) {
    const open = draftStart.t - START_AHEAD_MAX_S;
    return { level: 'note', label: `Scheduled · opens ${dayTime(open)} UTC` };
  }
  const more = blocks.length > 1 ? ` and ${blocks.length - 1} more` : '';
  if (blocks.length) return { level: 'block', label: `${engaged ? word : 'Blocked'} · ${checkName(blocks[0]).toLowerCase()}${more}` };
  const notes = list.filter((i) => i.level === 'note').length;
  const n = notes ? ` · ${notes} note${notes > 1 ? 's' : ''}` : '';
  if (engaged) return { level: notes ? 'note' : 'ok', label: `${word}${n}` };
  return notes ? { level: 'note', label: `Ready${n}` } : { level: 'ok', label: 'Ready' };
}

/**
 * Why Start cannot run, in the server's words (null: it can). The engine stays the
 * authority: this only mirrors what the server would refuse (a preflight block, a plan
 * error, a run already engaged), so Start is never disabled for a note or a warning.
 */
export function startBlock(
  s: SequenceState | null,
  items: readonly PreflightItem[] | null,
  issues: readonly { step: number | null; message: string; level?: string }[] = [],
): string | null {
  if (s && isEngaged(s)) return s.state === 'waiting' ? 'A start is already scheduled' : 'A sequence is running';
  const block = items?.find((i) => i.level === 'block');
  if (block) return `${checkName(block)}: ${block.message}`;
  const issue = issues.find((i) => i.level !== 'warning');
  if (issue) return issue.step !== null ? `Fix step ${issue.step + 1}: ${issue.message}` : issue.message;
  return null;
}

// -- Scheduled start (Q-P2) -----------------------------------------------------------------------

export type StartAt = { ok: true; t: number; tomorrow: boolean; text: string } | { ok: false; error: string };

/**
 * "hh:mm" (UTC) to the next such instant after `now`. A time already past on today's UTC
 * date is the next date, and the answer then writes that date (never a silent shift),
 * with how long from now; anything that is not a 24-hour time is refused in words.
 */
export function parseStartAt(text: string, now: number): StartAt {
  const m = /^\s*(\d{1,2})[:h.]?(\d{2})\s*$/.exec(text);
  if (!m) return { ok: false, error: 'Type a UTC time as hh:mm, 00:00 to 23:59.' };
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return { ok: false, error: `${m[1]}:${m[2]} is not a time: hours 00 to 23, minutes 00 to 59.` };
  const day = Math.floor(now / 86400) * 86400;
  let t = day + h * 3600 + mi * 60;
  const tomorrow = t <= now;
  if (tomorrow) t += 86400;
  return { ok: true, t, tomorrow, text: `${tomorrow ? `${utcDate(t)} ` : ''}${clockUtc(t, false)} UTC, in ${duration(t - now)}` };
}

/** The server refuses a start more than this far ahead (sequence.py START_AHEAD_MAX_S). */
export const START_AHEAD_MAX_S = 86400;

export type DraftStart = { ok: true; t: number | null; text: string } | { ok: false; error: string };

/**
 * The plan draft's own start time (W6b; 6a gap "a transit prepared for a night more than
 * 24 h ahead"): "YYYY-MM-DD hh:mm" (UTC) for any day, "hh:mm" for the next such time, empty
 * for none (Start then runs at once). A time already passed is refused in words; one more
 * than 24 h ahead is kept in the draft and Start opens 24 h before (said under the field).
 */
export function parseDraftStart(text: string, now: number): DraftStart {
  const s = text.trim();
  if (!s) return { ok: true, t: null, text: 'No start time: Start runs at once' };
  const d = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2})[:h.]?(\d{2})(?::00)?Z?$/i.exec(s);
  let t: number;
  if (d) {
    const [y, mo, da, h, mi] = d.slice(1).map(Number);
    if (h > 23 || mi > 59) return { ok: false, error: `${d[4]}:${d[5]} is not a time: hours 00 to 23, minutes 00 to 59.` };
    t = Date.UTC(y, mo - 1, da, h, mi) / 1000;
    if (!Number.isFinite(t) || new Date(t * 1000).getUTCDate() !== da || new Date(t * 1000).getUTCMonth() !== mo - 1) {
      return { ok: false, error: `${d[1]}-${d[2]}-${d[3]} is not a date.` };
    }
    if (t <= now) return { ok: false, error: `${utcDate(t)} ${clockUtc(t, false)} UTC has passed: type a later time, or clear the field to start at once.` };
  } else {
    const r = parseStartAt(s, now);
    if (!r.ok) return { ok: false, error: 'Type a UTC start as YYYY-MM-DD hh:mm (or hh:mm for the next one); empty starts at once.' };
    t = r.t;
  }
  const ahead = t - now;
  const days = Math.floor(Math.round(ahead) / 86400);
  const span = days >= 2 ? `${days}d ${Math.floor((Math.round(ahead) % 86400) / 3600)}h` : duration(ahead);
  // The field shows the date and time: the line under it says how far, and when Start opens.
  const open = t - START_AHEAD_MAX_S;
  return { ok: true, t, text: ahead > START_AHEAD_MAX_S ? `in ${span} · Start opens ${dayTime(open)} UTC` : `in ${span}` };
}

/** "21:30" today (UTC), "16 Nov 21:30" another day: a time is never read as tonight's. */
export function dayTime(t: number, now: number | null = null): string {
  const d = new Date(Math.round(t) * 1000);
  const today = now !== null && Math.floor(t / 86400) === Math.floor(now / 86400);
  return today ? clockUtc(t, false) : `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${clockUtc(t, false)}`;
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** The draft's start for its field: "YYYY-MM-DD hh:mm" (UTC), '' for none. */
export const draftStartText = (t: number | null): string => (t === null ? '' : `${utcDate(t)} ${clockUtc(t, false)}`);

/** "hh:mm" of unix seconds, for prefilling the field (a transit's coverage start). */
export const hhmm = (t: number): string => clockUtc(t, false);
