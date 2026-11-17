import { describe, expect, it } from 'vitest';
import type { SequenceResult } from '../../api/sequence';
import { aboutText, attentionLine, checkWrapUp, entryLine, entryTitle, mountLine, pointsLine, runLine, sizeText, totalEstimate, wrapupApi } from './wrapup';
import { WrapUpStore } from './store.svelte';

const result = (over: Partial<SequenceResult> = {}): SequenceResult => ({
  completed: true,
  reason: null,
  message: null,
  frames_saved: 195,
  frames_total: 195,
  run_root: '/data/sessions/20260925T200453Z_RR_Lyr',
  started_t: Date.UTC(2026, 8, 25, 20, 4) / 1000,
  ended_utc: '2026-09-25T22:54:00Z',
  ended_t: Date.UTC(2026, 8, 25, 22, 54) / 1000,
  on_complete: 'Nothing',
  ...over,
});

// protocol.md "Night (wave 6b)", WrapUp: the 2026-09-25 shape (10 s subs, 51.5 s cadence).
const WIRE = {
  run_id: 'r1',
  object_name: 'RR Lyr',
  outcome: { completed: true },
  started_utc: '2026-09-25T20:04:53Z',
  ended_utc: '2026-09-25T22:54:20Z',
  frames: { saved: 195, total: 195, by_type: { Light: 195 } },
  points: { target: 193, all: 1158, flagged: 3, frames_measured: 193, frames_skipped: { field_lost: 0, lock_lost: 2, other: 0 } },
  attention: { critical: 0, attention: 1, info: 2, items: [] },
  run_root: '/data/sessions/20260925T200453Z_RR_Lyr',
  run_folder: '20260925T200453Z_RR_Lyr',
  run_bytes: 3.04e9,
  mount: { connected: true, state: 'tracking', tracking: true, end_action: 'Nothing' },
  calibration: {
    darks: [{ exposure_s: 10, gain: 80, count: 20, existing: 0, estimate_s: 1030 }],
    biases: [{ exposure_s: 0.001, gain: 80, count: 30, existing: 4, estimate_s: 1245.03 }],
    overhead_s: 41.5,
    cadence_s: 51.5,
    dark_slot: true,
    note: null,
  },
};

describe('wrap-up record', () => {
  it("reads the server's record, alone or inside a sequence record", () => {
    const w = checkWrapUp(WIRE)!;
    expect(w.frames).toEqual({ saved: 195, total: 195, lights: 195 });
    expect(w.points?.skipped.lock_lost).toBe(2);
    expect(w.mount).toEqual({ connected: true, state: 'tracking', tracking: true, endAction: 'Nothing' });
    expect(w.calibration?.entries.map((e) => `${e.kind} ${e.exposure_s} ${e.count} ${e.existing}`)).toEqual(['dark 10 20 0', 'bias 0.001 30 4']);
    expect(w.calibration).toMatchObject({ overhead: 41.5, cadence: 51.5, darkSlot: true });
    expect(checkWrapUp({ sequence: { state: 'idle', wrapup: WIRE } })?.runFolder).toBe('20260925T200453Z_RR_Lyr');
    expect(checkWrapUp({ wrapup: WIRE })?.runBytes).toBe(3.04e9);
  });

  it('refuses a record without frames or an end (never guessed); null while measuring', () => {
    expect(checkWrapUp(null)).toBeNull();
    expect(checkWrapUp({ ...WIRE, frames: undefined })).toBeNull();
    expect(checkWrapUp({ ...WIRE, ended_utc: null })).toBeNull();
    expect(checkWrapUp({ ...WIRE, calibration: { darks: [{ exposure_s: 10 }], biases: 'x' } })?.calibration?.entries).toEqual([]);
  });

  it('follows the sequence record and prepares the calibration plan', async () => {
    const handlers = new Map<string, (m: Record<string, unknown>) => void>();
    const calls: [string, string, unknown][] = [];
    const client = {
      request: async <T,>(method: string, path: string, body?: unknown): Promise<T> => {
        calls.push([method, path, body]);
        return (method === 'GET' ? WIRE : { plan: {}, replaced: { object_name: 'RR Lyr', steps: [] } }) as T;
      },
    };
    const store = new WrapUpStore();
    store.attach({ on: (t: string, fn: (m: Record<string, unknown>) => void) => (handlers.set(t, fn), () => handlers.delete(t)) }, client);
    handlers.get('sequence')!({ type: 'sequence', sequence: { state: 'idle', wrapup: null } });
    expect(store.view).toBeNull();
    handlers.get('sequence')!({ type: 'sequence', sequence: { state: 'idle', wrapup: WIRE } });
    expect(store.view?.frames.saved).toBe(195);
    handlers.get('sequence')!({ type: 'sequence', sequence: { state: 'running' } });
    expect(store.view?.frames.saved).toBe(195);
    await store.refresh();
    const r = await store.prepare({ darks: 15 });
    expect(r.replaced?.object_name).toBe('RR Lyr');
    expect(calls).toEqual([
      ['GET', '/api/sequence/wrapup', undefined],
      ['POST', '/api/sequence/calibration-plan', { darks: 15 }],
    ]);
    await expect(wrapupApi.get({ request: () => Promise.reject(new Error('No run has ended yet.')) })).rejects.toThrow('No run has ended yet.');
  });
});

describe('wrap-up words', () => {
  const w = checkWrapUp(WIRE)!;
  const [dark, bias] = w.calibration!.entries;

  it("writes the calibration lines; tonight's 51.5 s cadence makes 20 darks about 17 min (finding 1)", () => {
    expect(entryTitle(dark)).toBe('20 darks');
    expect(entryTitle(bias)).toBe('30 biases');
    expect(entryLine(dark, true)).toBe('10.0 s · gain 80 · Dark slot');
    expect(entryLine(bias, false)).toBe('shortest exposure 0.001 s · gain 80 · lid on · 4 taken tonight');
    expect(aboutText(dark.estimate_s)).toBe('≈ 17m 10s'); // the Plan's Duration column
    expect(totalEstimate([dark, bias])).toBeCloseTo(2275.03);
    expect(totalEstimate([{ ...dark, estimate_s: null }])).toBeNull();
    expect(aboutText(null)).toBe('time unknown');
    expect(aboutText(3900)).toBe('≈ 1h 05m');
    expect(aboutText(20)).toBe('≈ 20 s');
    expect(aboutText(80)).toBe('≈ 1m 20s');
  });

  it('says what the mount does now', () => {
    expect(mountLine({ state: 'tracking', tracking: true }, 'Nothing')).toEqual({ text: 'Tracking is still on.', tracking: true });
    expect(mountLine({ state: 'tracking', tracking: true }, 'Stop tracking').text).toBe('Tracking is still on (the end action did not stop it).');
    expect(mountLine({ state: 'parked', tracking: false }, 'Park mount')).toEqual({ text: 'The mount is parked.', tracking: false });
    expect(mountLine({ state: 'idle', tracking: false }, null).text).toBe('Tracking is off.');
    expect(mountLine({ state: 'idle', tracking: null, connected: true }, null).text).toBe('The mount state is not known.');
    expect(mountLine({ state: null, tracking: null, connected: false }, null).text).toBe('The mount is not connected.');
    expect(mountLine(null, null).text).toBe('The mount is not connected.');
  });

  it('summarises the run, its points, its items and its size', () => {
    expect(runLine('RR Lyr', result())).toBe('RR Lyr · 195 frames of 195 · 20:04–22:54 UTC');
    expect(runLine(null, result({ frames_saved: 1, frames_total: null, started_t: null }))).toBe('1 frame');
    expect(pointsLine(w.points)).toBe('193 target points · 3 flagged · frames without a point: 2 lock lost');
    expect(pointsLine(w.points, w.frames.lights)).toBe('193 target points · 3 flagged · frames without a point: 2 lock lost'); // 195 = 193 + 2
    // 40 frames: 37 measured, 2 lock lost, 1 not measured (the design review's count).
    const p40 = { ...w.points!, target: 37, flagged: 0, measured: 37, skipped: { field_lost: 0, lock_lost: 2, other: 0 } };
    expect(pointsLine(p40, 40)).toBe('37 target points · frames without a point: 2 lock lost, 1 not measured');
    expect(pointsLine(null)).toBeNull();
    expect(attentionLine(w.attention)).toBe('1 attention during the run');
    expect(attentionLine({ critical: 0, attention: 0, info: 3 })).toBeNull();
    expect(sizeText(3.04e9)).toBe('3.0 GB');
    expect(sizeText(4.12e8)).toBe('412 MB');
    expect(sizeText(null)).toBeNull();
  });
});
