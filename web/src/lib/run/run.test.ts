import { describe, expect, it } from 'vitest';
import { checkSequence, type PreflightItem, type SequenceResult, type SequenceState } from '../api/sequence';
import { endAt, folderName, nextAutofocus, nextAutofocusParts, outcomeOf, outcomeText, parseStartAt, readiness, startBlock, stateChip, stepText, stopDialog, stripLine } from './run';

const T = Date.UTC(2026, 10, 1, 21, 45, 0) / 1000;

const STEP = { enabled: true, frame_type: 'Light', filter_name: 'LP', exposure_s: 30, gain: 80, count: 10, interval_s: 0, cadence_s: null, dither_every: 0 };
const PLAN = { object_name: 'T CrB', repeat: 1, autofocus_every_n: 20, autofocus_on_filter_change: false, on_complete: 'Park mount', base_dir: null, metadata: {}, start_at_utc: null, steps: [STEP, STEP, STEP] };

/** A wire SequenceState (protocol.md), checked as the store checks it. */
function seq(over: Record<string, unknown> = {}): SequenceState {
  const auto = 'autofocus_every_n' in over ? { ...PLAN, autofocus_every_n: over.autofocus_every_n } : PLAN;
  return checkSequence({
    state: 'running',
    object_name: 'T CrB',
    run_id: '20261101T204502Z',
    run_root: '/data/sessions/20261101T204502Z_T_CrB/',
    plan: auto,
    step_index: 1,
    step: STEP,
    pass_index: 1,
    repeat: 1,
    frames_done: 37,
    frames_total: 50,
    eta_s: 390,
    started_utc: '2026-11-01T20:45:02Z',
    current: { exposure_s: 30, started_utc: '2026-11-01T21:44:40Z' },
    last_frame_utc: '2026-11-01T21:44:38Z',
    next_autofocus: { reason: 'every_n', in_frames: 3 },
    end_action: 'Park mount',
    last_result: null,
    ...over,
  }) as SequenceState;
}

const result = (r: Partial<SequenceResult>): SequenceResult => ({
  completed: false,
  reason: null,
  message: null,
  frames_saved: 37,
  frames_total: 50,
  started_t: null,
  ended_utc: '2026-11-01T21:52:00Z',
  ended_t: Date.UTC(2026, 10, 1, 21, 52) / 1000,
  run_root: null,
  on_complete: null,
  ...r,
});

describe('outcome (spec 2.4 Finished, P14)', () => {
  it('tells completed, stopped by the observer and stopped by an error apart', () => {
    expect(outcomeOf(result({ completed: true }))).toBe('completed');
    expect(outcomeOf(result({ reason: 'stopped' }))).toBe('stopped');
    expect(outcomeOf(result({ reason: 'cancelled' }))).toBe('stopped');
    expect(outcomeOf(result({ reason: 'camera_error', message: 'Exposure timeout after 45s' }))).toBe('failed');
    expect(outcomeOf(result({ reason: 'autofocus_timeout' }))).toBe('failed');
    expect(outcomeOf(result({}))).toBe('stopped');
  });

  it('says it in words, with the server sentence verbatim', () => {
    expect(outcomeText(result({ completed: true, frames_saved: 50, on_complete: 'Park mount' }))).toBe('Sequence complete · 50 frames · 21:52 UTC · end of run: park');
    expect(outcomeText(result({ completed: true, frames_saved: 1, on_complete: 'Nothing' }))).toBe('Sequence complete · 1 frame · 21:52 UTC');
    expect(outcomeText(result({ reason: 'stopped' }))).toBe('Stopped by the observer after 37 frames · 21:52 UTC');
    expect(outcomeText(result({ reason: 'error', message: 'Exposure timeout after 45s', frames_saved: 12 }))).toBe('Stopped: Exposure timeout after 45s · 12 frames saved · 21:52 UTC');
  });
});

describe('state chip', () => {
  it('has a word for every state', () => {
    const labels = ['running', 'pausing', 'paused', 'autofocus', 'stopping'].map((s) => stateChip(seq({ state: s })).label);
    expect(labels).toEqual(['Running', 'Pausing after this frame…', 'Paused', 'Autofocus', 'Stopping…']);
    expect(stateChip(seq({ state: 'waiting', start_at_utc: '2026-11-02T00:12:00Z' }))).toEqual({ tone: 'busy', label: 'Scheduled' });
    expect(stateChip(seq({ state: 'idle' }))).toEqual({ tone: 'idle', label: 'No run' });
    expect(stateChip(seq({ state: 'idle', last_result: { completed: true, frames_saved: 50 } }))).toEqual({ tone: 'ok', label: 'Complete' });
    expect(stateChip(seq({ state: 'idle', last_result: { completed: false, reason: 'error', message: 'x', frames_saved: 3 } })).tone).toBe('error');
    expect(stateChip(null).label).toBe('No link');
  });
});

describe('run strip line (spec 2.3.2)', () => {
  it('reads step, frames, ETA and the end time from the newest frame', () => {
    const s = seq();
    expect(endAt(s, T)).toBe(Date.UTC(2026, 10, 1, 21, 44, 38) / 1000 + 390);
    expect(stripLine(s, T)).toBe('Step 2/3 · 10 × 30.0 s LP · frame 37/50 · ETA 6m 08s · ends ≈ 21:51 UTC');
  });

  it('leads with the state when it matters, and names a broken cadence', () => {
    expect(stripLine(seq({ state: 'paused' }), T)).toMatch(/^Paused after frame 37 · Step 2\/3/);
    expect(stripLine(seq({ state: 'paused', paused_by: 'motion', step: { ...STEP, cadence_s: 13 } }), T)).toMatch(/^Paused after frame 37 for a mount motion · 13\.0 s cadence broken · Step 2\/3 · 10 × 30\.0 s LP/);
    expect(stripLine(seq({ state: 'pausing' }), T)).toMatch(/^Step 2\/3 · /); // the chip says "Pausing after this frame…"
    expect(stripLine(seq({ state: 'autofocus' }), T, { done: 4, total: 9 })).toMatch(/^Autofocus pass \(step 4\/9\) · /);
    expect(stripLine(seq({ state: 'autofocus' }), T)).toMatch(/^Autofocus pass · /);
    expect(stripLine(seq({ state: 'stopping' }), T)).toBe('Stopping: the frame being exposed is discarded · Step 2/3 · 10 × 30.0 s LP · frame 37/50');
    expect(stripLine(seq({ repeat: 3, pass_index: 2 }), T)).toContain('pass 2/3'); // 1-based on the wire
    expect(stripLine(seq({ eta_s: null }), T)).toBe('Step 2/3 · 10 × 30.0 s LP · frame 37/50');
  });

  it('says when a scheduled run starts', () => {
    const s = seq({ state: 'waiting', start_at_utc: '2026-11-02T00:12:00Z', frames_done: 0 });
    expect(stripLine(s, T)).toBe('Starts at 00:12 UTC, in 2h 27m · 50 frames planned');
  });

  it('writes Dark and Bias steps by their type', () => {
    expect(stepText({ enabled: true, frame_type: 'Dark', filter_name: 'Dark', exposure_s: 10, gain: 80, count: 20, interval_s: 0, cadence_s: null, dither_every: 0 })).toBe('20 × 10.0 s Dark');
    expect(stepText({ enabled: true, frame_type: 'Flat', filter_name: 'IR', exposure_s: 0.5, gain: 80, count: 20, interval_s: 0, cadence_s: null, dither_every: 0 })).toBe('20 × 0.500 s Flat IR');
  });
});

describe('next autofocus', () => {
  it('in frames, with the time at the observed cadence', () => {
    expect(nextAutofocus(seq(), 32)).toBe('in 3 frames (≈ 1m 36s)');
    expect(nextAutofocus(seq(), null)).toBe('in 3 frames');
    expect(nextAutofocus(seq({ autofocus_every_n: 0, next_autofocus: null }), 32)).toBe('off');
    expect(nextAutofocus(seq({ next_autofocus: null }), 32)).toBe('—');
    expect(nextAutofocus(seq({ next_autofocus: { reason: 'every_n', in_frames: 0 } }), 32)).toBe('before the next frame');
    expect(nextAutofocusParts(seq(), 32)).toEqual({ v: '3', unit: 'frames', note: '≈ 1m 36s' });
    expect(nextAutofocusParts(seq({ next_autofocus: { reason: 'every_n', in_frames: 1 } }), null)).toEqual({ v: '1', unit: 'frame', note: undefined });
  });
});

describe('Stop confirmation (spec 2.3.6, Q-P7)', () => {
  it('says what is discarded, saved and where, and the end action not applied', () => {
    expect(stopDialog(seq())).toEqual({
      title: 'Stop the sequence?',
      message: 'The current 30.0 s exposure is discarded. 37 of 50 frames are saved in 20261101T204502Z_T_CrB. The end-of-run action (park) is not applied.',
      confirm: 'Stop',
      cancel: 'Keep running',
    });
    expect(stopDialog(seq({ state: 'paused', end_action: 'Nothing', frames_done: 1 })).message).toBe('1 of 50 frames is saved in 20261101T204502Z_T_CrB.');
  });

  it('cancels a scheduled start with its own words', () => {
    const d = stopDialog(seq({ state: 'waiting', start_at_utc: '2026-11-02T00:12:00Z' }));
    expect(d.title).toBe('Cancel the scheduled start?');
    expect(d.message).toBe('The sequence will not start at 00:12 UTC. The plan stays as it is.');
  });

  it('names the run folder from any path form', () => {
    expect(folderName('/a/b/20261101T204502Z_T_CrB/')).toBe('20261101T204502Z_T_CrB');
    expect(folderName('C:\\x\\run_1')).toBe('run_1');
    expect(folderName(null)).toBeNull();
  });
});

describe('readiness (spec 2.3.5) and Start', () => {
  const items: PreflightItem[] = [
    { id: 'camera', level: 'ok', label: null, message: 'connected' },
    { id: 'focuser', level: 'note', label: null, message: 'not connected · AF options off' },
    { id: 'altitude', level: 'note', label: null, message: 'ends at 24° (below 30°)' },
  ];

  it('Ready, Ready with notes, Blocked by the first block', () => {
    expect(readiness(items.slice(0, 1))).toEqual({ level: 'ok', label: 'Ready' });
    expect(readiness(items)).toEqual({ level: 'note', label: 'Ready · 2 notes' });
    expect(readiness([...items, { id: 'camera', level: 'block', label: null, message: 'not connected' }, { id: 'site', level: 'block', label: null, message: 'none' }])).toEqual({ level: 'block', label: 'Blocked · camera and 1 more' });
    expect(readiness(null)).toEqual({ level: 'unknown', label: 'Not checked' });
  });

  it('during a run, speaks of the run and never reports the run itself as a block', () => {
    const run: PreflightItem = { id: 'run', level: 'block', label: null, message: 'A sequence is running (RR Lyr).' };
    expect(readiness([run, items[0]], true)).toEqual({ level: 'ok', label: 'Running' });
    expect(readiness([run, ...items], 'Paused')).toEqual({ level: 'note', label: 'Paused · 2 notes' });
    expect(readiness([run, { id: 'camera', level: 'block', label: null, message: 'lost' }], 'Running')).toEqual({ level: 'block', label: 'Running · camera' });
    // Unique ids (plan issues `plan:<code>:<step>`) keep their base's name.
    expect(readiness([{ id: 'plan:interval_ignored:1', level: 'note', label: null, message: 'x' }], 'Starts 17:34 UTC')).toEqual({ level: 'note', label: 'Starts 17:34 UTC · 1 note' });
    expect(readiness([run, items[0]])).toEqual({ level: 'block', label: 'Blocked · run' });
  });

  it('Start is refused only where the server would refuse: a block, an invalid step, an active run', () => {
    expect(startBlock(null, items)).toBeNull();
    expect(startBlock(null, [{ id: 'camera', level: 'block', label: null, message: 'Connect the camera first' }])).toBe('Camera: Connect the camera first');
    const issues = [
      { step: 0, level: 'warning', message: 'Light step on the Dark slot' },
      { step: 1, level: 'error', message: 'cadence shorter than exposure' },
    ];
    expect(startBlock(null, items, issues)).toBe('Fix step 2: cadence shorter than exposure');
    expect(startBlock(null, items, issues.slice(0, 1))).toBeNull();
    expect(startBlock(seq(), items)).toBe('A sequence is running');
    expect(startBlock(seq({ state: 'waiting' }), items)).toBe('A start is already scheduled');
    expect(startBlock(seq({ state: 'idle' }), items)).toBeNull();
  });
});

describe('Start at hh:mm (Q-P2)', () => {
  it('takes today when still ahead, else the next UTC date, written out', () => {
    const r = parseStartAt('23:30', T);
    expect(r).toEqual({ ok: true, t: Date.UTC(2026, 10, 1, 23, 30) / 1000, tomorrow: false, text: '23:30 UTC, in 1h 45m' });
    const n = parseStartAt('0:12', T);
    expect(n).toEqual({ ok: true, t: Date.UTC(2026, 10, 2, 0, 12) / 1000, tomorrow: true, text: '2026-11-02 00:12 UTC, in 2h 27m' });
    expect(parseStartAt('2130', T).ok).toBe(true);
  });

  it('refuses what is not a 24-hour time, in words (never clamped)', () => {
    expect(parseStartAt('24:10', T)).toEqual({ ok: false, error: '24:10 is not a time: hours 00 to 23, minutes 00 to 59.' });
    expect(parseStartAt('12:75', T).ok).toBe(false);
    expect(parseStartAt('soon', T)).toEqual({ ok: false, error: 'Type a UTC time as hh:mm, 00:00 to 23:59.' });
  });
});

describe('fixer W6a: pause_run wait, preflight words, paused end', () => {
  it('waits as long as the server may hold a pause_run motion', async () => {
    const { pauseRunTimeoutMs } = await import('./run');
    expect(pauseRunTimeoutMs(null)).toBe(75_000);
    expect(pauseRunTimeoutMs({ state: 'running', current: { exposure_s: 300 }, step: null } as never)).toBe(375_000);
    expect(pauseRunTimeoutMs({ state: 'autofocus', current: null, step: null } as never)).toBe(400_000);
  });

  it('names checks by their base id and elides long paths', async () => {
    const { checkMessage, checkName } = await import('./run');
    expect(checkName({ id: 'lid', level: 'ok', label: null, message: '' })).toBe('Dark frames');
    expect(checkName({ id: 'plan:interval_ignored:2', level: 'note', label: null, message: '' })).toBe('Plan');
    expect(checkName({ id: 'sleep', level: 'ok', label: null, message: '' })).toBe('Computer sleep');
    const long = { id: 'output', level: 'ok' as const, label: null, message: 'Runs are written in /private/tmp/claude/scratchpad/w6a/integ/sessions.' };
    expect(checkMessage(long)).toBe('Runs are written in …/integ/sessions.');
    expect(checkMessage({ ...long, message: 'Runs are written in /data/runs.' })).toBe('Runs are written in /data/runs.');
  });

  it('moves the end with the clock while paused, never a frozen countdown', () => {
    const paused = seq({ state: 'paused', end_t: null, eta_s: 600 });
    expect(endAt(paused, T)).toBe(T + 600);
    expect(endAt(paused, T + 60)).toBe(T + 660);
  });

  it('says nothing is saved yet when Stop comes before the first frame', () => {
    const d = stopDialog(seq({ frames_done: 0, current: null }));
    expect(d.message).toMatch(/^No frame is saved yet; the run folder 20261101T204502Z_T_CrB stays\./);
  });
});
