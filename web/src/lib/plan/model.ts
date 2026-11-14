/**
 * Plan screen logic (06 §2.2-2.4), pure and tested without a browser: step editing, the
 * issue map, the run lock, progress per row, the keyboard map of the Steps table, times.
 *
 * - Editing never fixes a value: an operation moves, copies or removes steps as they are;
 *   the server answers with the issues (A59), which this module only indexes.
 * - Selection is explicit: no selection means no row action (06 P19), never "the last row".
 */

import { DARK_SLOT, FRAME_TYPES, type PlanDoc, type PlanIssue, type PlanStep, type SequencePlan } from '../api/plan';
import type { SequenceState } from '../api/sequence';

// -- Steps ---------------------------------------------------------------------------------------

/** The light-passing slots of a wheel (the opaque slot never becomes a Light default, S7). */
export function lightSlots(names: readonly string[]): string[] {
  return names.filter((n) => n.toLowerCase() !== DARK_SLOT.toLowerCase());
}

/**
 * A new step: the selected step's settings when there is one (the observer's own values),
 * else a Light step on the wheel's first light slot. Count and type come from the source;
 * nothing is invented beyond Qt's model defaults (sequencer.py:47-57).
 */
export function newStep(from: PlanStep | null, wheel: readonly string[]): PlanStep {
  if (from) return { ...from, enabled: true };
  return {
    enabled: true,
    frame_type: 'Light',
    filter_name: lightSlots(wheel)[0] ?? '',
    exposure_s: 10,
    gain: 80,
    count: 10,
    interval_s: 0,
    cadence_s: null,
    dither_every: 0,
  };
}

export interface StepEdit {
  steps: PlanStep[];
  /** Index of the row selected after the edit, or null. */
  selected: number | null;
}

/** Insert after the selection, else at the end (06 2.2 1.4 #11). */
export function addStep(steps: readonly PlanStep[], selected: number | null, wheel: readonly string[]): StepEdit {
  const at = selected !== null && selected >= 0 && selected < steps.length ? selected + 1 : steps.length;
  const from = selected !== null ? (steps[selected] ?? null) : null;
  const next = [...steps];
  next.splice(at, 0, newStep(from, wheel));
  return { steps: next, selected: at };
}

/** A copy right after its source; nothing selected = nothing done. */
export function duplicateStep(steps: readonly PlanStep[], i: number | null): StepEdit | null {
  if (i === null || !steps[i]) return null;
  const next = [...steps];
  next.splice(i + 1, 0, { ...steps[i] });
  return { steps: next, selected: i + 1 };
}

/** Remove one step (the last one too: an empty plan is a state, 06 2.2 1.4 #13). */
export function removeStep(steps: readonly PlanStep[], i: number | null): (StepEdit & { removed: PlanStep; at: number }) | null {
  if (i === null || !steps[i]) return null;
  const next = [...steps];
  const [removed] = next.splice(i, 1);
  const selected = next.length ? Math.min(i, next.length - 1) : null;
  return { steps: next, selected, removed, at: i };
}

/** Move a step from `from` to `to` (drag, Alt+↑↓); out-of-range moves do nothing. */
export function moveStep(steps: readonly PlanStep[], from: number | null, to: number): StepEdit | null {
  if (from === null || !steps[from] || to < 0 || to >= steps.length || to === from) return null;
  const next = [...steps];
  const [s] = next.splice(from, 1);
  next.splice(to, 0, s);
  return { steps: next, selected: to };
}

export function patchStep(steps: readonly PlanStep[], i: number, patch: Partial<PlanStep>): PlanStep[] {
  return steps.map((s, k) => (k === i ? { ...s, ...patch } : s));
}

/** Dark and Bias go to the opaque slot: their filter is not the observer's (sequencer.py:114-123). */
export function usesFilter(frameType: string): boolean {
  return frameType !== 'Dark' && frameType !== 'Bias';
}

export function isKnownType(t: string): boolean {
  return (FRAME_TYPES as readonly string[]).includes(t);
}

/** Options of a token menu: the known values, plus the step's own value when it is not one of
 * them (flagged, never replaced by the first entry, 06 P11). */
export function optionsWith(known: readonly string[], current: string, unknownDetail: string): { value: string; label: string; detail?: string }[] {
  const opts: { value: string; label: string; detail?: string }[] = known.map((v) => ({ value: v, label: v }));
  if (current && !known.includes(current)) opts.push({ value: current, label: current, detail: unknownDetail });
  return opts;
}

// -- Issues --------------------------------------------------------------------------------------

/** Names of the fields, in the observer's words (issue list, screen readers). */
export const FIELD_LABELS: Record<string, string> = {
  enabled: 'On',
  frame_type: 'Type',
  filter_name: 'Filter',
  exposure_s: 'Exposure',
  gain: 'Gain',
  count: 'Count',
  interval_s: 'Interval',
  cadence_s: 'Cadence',
  dither_every: 'Dither',
  object_name: 'Object',
  repeat: 'Repeat',
  autofocus_every_n: 'Autofocus every',
  autofocus_on_filter_change: 'Autofocus on filter change',
  on_complete: 'End of run',
  steps: 'Steps',
  metadata: 'Transit ephemeris',
  start_at_utc: 'Start (UTC)',
};

export interface IssueIndex {
  /** Issues of one step field ("2:exposure_s"). */
  field(step: number, field: string): PlanIssue[];
  /** Every issue of a step (its fields and the step itself). */
  step(step: number): PlanIssue[];
  /** Issues of a plan-level field ("repeat"), or of the plan itself with `null`. */
  plan(field: string | null): PlanIssue[];
  /** Errors block Start; warnings are said. */
  errors: PlanIssue[];
  warnings: PlanIssue[];
  all: PlanIssue[];
}

export function indexIssues(issues: readonly PlanIssue[]): IssueIndex {
  const byField = new Map<string, PlanIssue[]>();
  const byStep = new Map<number, PlanIssue[]>();
  const byPlan = new Map<string, PlanIssue[]>();
  const push = <K>(m: Map<K, PlanIssue[]>, k: K, i: PlanIssue) => {
    const l = m.get(k);
    if (l) l.push(i);
    else m.set(k, [i]);
  };
  for (const i of issues) {
    if (i.step !== null) {
      push(byStep, i.step, i);
      if (i.field) push(byField, `${i.step}:${i.field}`, i);
    } else {
      push(byPlan, i.field ?? '', i);
    }
  }
  return {
    field: (s, f) => byField.get(`${s}:${f}`) ?? [],
    step: (s) => byStep.get(s) ?? [],
    plan: (f) => byPlan.get(f ?? '') ?? [],
    errors: issues.filter((i) => i.level === 'error'),
    warnings: issues.filter((i) => i.level === 'warning'),
    all: [...issues],
  };
}

/**
 * The server's sentence without the place the screen already shows: "Step 2: cadence 20 s is
 * shorter…" under step 2's row reads "Cadence 20 s is shorter…" (the words are otherwise kept).
 */
export function issueText(i: PlanIssue): string {
  if (i.step === null) return i.message;
  const m = new RegExp(`^Step ${i.step + 1}\\s*[:·,-]\\s*`, 'i').exec(i.message);
  if (!m) return i.message;
  const rest = i.message.slice(m[0].length);
  return rest ? rest[0].toUpperCase() + rest.slice(1) : i.message;
}

/** "Step 2 · Cadence: …" / "Repeat: …" / the message alone. */
export function issueTitle(i: PlanIssue): string {
  const field = i.field ? (FIELD_LABELS[i.field] ?? i.field) : null;
  if (i.step !== null) return `Step ${i.step + 1}${field ? ` · ${field}` : ''}`;
  return field ?? 'Plan';
}

/**
 * Why Start cannot run now, in the server's terms (spec 2.4 "Invalid cell"): no enabled step,
 * then the first error. Null = the plan itself does not stop it (the preflight may).
 */
export function planBlock(doc: PlanDoc | null): string | null {
  if (!doc) return 'the plan is not loaded yet';
  const enabled = doc.plan.steps.some((s) => s.enabled && s.count > 0);
  if (!doc.plan.steps.length) return 'add a step or open a preset';
  if (!enabled) return 'enable at least one step';
  const first = doc.issues.find((i) => i.level === 'error' && i.code !== 'no_enabled_step');
  if (!first) return null;
  return first.step !== null ? `fix step ${first.step + 1}: ${lowerFirst(issueText(first))}` : `fix the plan: ${lowerFirst(first.message)}`;
}

function lowerFirst(s: string): string {
  // Keep acronyms and names ("BJD_TDB", "IR") as written.
  return /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s;
}

// -- Run -----------------------------------------------------------------------------------------

/** Run states in which the plan is locked (Q-P9): every state but idle, a scheduled start too. */
export function runActive(s: { state: string } | null | undefined): boolean {
  return !!s && s.state !== 'idle';
}

export const LOCKED_REASON = 'Locked while a run is scheduled or running';

export type RowRun = { kind: 'done' | 'active' | 'waiting' | 'skipped'; done: number; total: number };

/**
 * Progress of each row in the current pass, from the run's frame count (the server's
 * authority): steps before the active one are done, disabled ones skipped (06 2.3.2).
 */
export function rowProgress(plan: SequencePlan, seq: Pick<SequenceState, 'state' | 'step_index' | 'pass_index' | 'frames_done'> | null): RowRun[] | null {
  // A scheduled start (protocol "waiting"; "scheduled" in lib/run) has no row progress yet.
  const st: string | undefined = seq?.state;
  if (!seq || !runActive(seq) || st === 'waiting' || st === 'scheduled') return null;
  const counts = plan.steps.map((s) => (s.enabled && s.count > 0 ? s.count : 0));
  const perPass = counts.reduce((a, b) => a + b, 0);
  if (perPass <= 0) return null;
  // `pass_index` is 1-based on the wire (protocol "SequenceState").
  const pass = seq.pass_index !== null && seq.pass_index >= 1 ? seq.pass_index - 1 : Math.floor(Math.max(0, seq.frames_done - 1) / perPass);
  let left = Math.max(0, seq.frames_done - pass * perPass);
  return plan.steps.map((s, i) => {
    const total = counts[i];
    if (!total) return { kind: 'skipped', done: 0, total: s.count };
    const done = Math.min(total, left);
    left -= done;
    const kind = i === seq.step_index ? 'active' : done >= total ? 'done' : 'waiting';
    return { kind, done, total };
  });
}

// -- Keyboard (06 2.4) ---------------------------------------------------------------------------

export type StepCommand = 'add' | 'duplicate' | 'remove' | 'up' | 'down' | 'toggle' | 'prev' | 'next' | 'first' | 'last';

/** The Steps table's keys on a focused row (never inside an editor): Insert, Mod+D, Delete /
 * Backspace, Alt+↑↓, Space, ↑↓ Home End. */
export function stepKeyCommand(e: Pick<KeyboardEvent, 'key' | 'altKey' | 'metaKey' | 'ctrlKey' | 'shiftKey'>, mac: boolean): StepCommand | null {
  const mod = mac ? e.metaKey : e.ctrlKey;
  if (mod && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'd') return 'duplicate';
  if (mod || e.shiftKey) return null;
  if (e.altKey) return e.key === 'ArrowUp' ? 'up' : e.key === 'ArrowDown' ? 'down' : null;
  switch (e.key) {
    case 'Insert':
      return 'add';
    case 'Delete':
    case 'Backspace':
      return 'remove';
    case ' ':
      return 'toggle';
    case 'ArrowUp':
      return 'prev';
    case 'ArrowDown':
      return 'next';
    case 'Home':
      return 'first';
    case 'End':
      return 'last';
    default:
      return null;
  }
}

// -- Times ---------------------------------------------------------------------------------------

const pad2 = (n: number) => String(n).padStart(2, '0');

/** "21:52" in the browser's local time (the observer's), or "—". `offsetMin` for tests. */
export function localHm(iso: string | null | undefined, offsetMin?: number): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const off = offsetMin ?? -d.getTimezoneOffset();
  const l = new Date(d.getTime() + off * 60_000);
  return `${pad2(l.getUTCHours())}:${pad2(l.getUTCMinutes())}`;
}

/** "20:52" UTC, or "—". */
export function utcHm(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(11, 16);
}

/** The local hh:mm written in an ISO string with an offset ("2026-11-12T01:12:00+01:00"). */
export function wallHm(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : '—';
}

/** "21:52 local · 20:52 UTC · 2026-11-12": the tooltip of a local time (06 2.4 Formats). */
export function timeTitle(iso: string | null | undefined, offsetMin?: number): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${localHm(iso, offsetMin)} local · ${utcHm(iso)} UTC · ${d.toISOString().slice(0, 10)}`;
}

/**
 * The night to show (local date of its evening, Q-P6): before local noon it is still last
 * night (fixes 06 P3, the next evening drawn between 00:00 and 06:00).
 */
export function nightOf(now: Date, offsetMin?: number): string {
  const off = offsetMin ?? -now.getTimezoneOffset();
  const l = new Date(now.getTime() + off * 60_000);
  if (l.getUTCHours() < 12) l.setUTCDate(l.getUTCDate() - 1);
  return l.toISOString().slice(0, 10);
}

/** "≈ 21m 30s" style totals line parts, from the server's derived values. */
export function frameWord(n: number): string {
  return n === 1 ? 'frame' : 'frames';
}

/** True when two plans are the same for the observer (unsaved-changes check). */
export function samePlan(a: SequencePlan | null, b: SequencePlan | null): boolean {
  if (!a || !b) return a === b;
  const norm = (p: SequencePlan) =>
    JSON.stringify({
      o: p.object_name,
      r: p.repeat,
      af: p.autofocus_every_n,
      afc: p.autofocus_on_filter_change,
      oc: p.on_complete,
      s: p.steps,
      m: p.metadata,
    });
  return norm(a) === norm(b);
}
