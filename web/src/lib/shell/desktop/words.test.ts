import { describe, expect, it } from 'vitest';
import type { BusyItem } from '../../api/desktop';
import { busyIcon, busySentence, elapsedText, localBusy, quitConsequence, stageLabel } from './words';

const item = (kind: string, label: string | null = null): BusyItem => ({ kind, label, detail: null });

describe('what runs', () => {
  it('lists what the UI sees, once each', () => {
    expect(localBusy({})).toEqual([]);
    expect(
      localBusy({
        sequence: { state: 'running', object: 'SS Cyg', done: 34, total: 120 },
        camera: 'exposing',
        autofocus: true,
        slewing: true,
        solving: true,
        jobs: [{ kind: 'rerun' }, { kind: 'field_solve' }, { kind: 'sessions_scan' }, { kind: 'export' }],
      }).map((i) => i.kind),
    ).toEqual(['sequence', 'exposure', 'autofocus', 'slew', 'solve', 'rerun', 'export']);
    expect(localBusy({ camera: 'live' }).map((i) => i.kind)).toEqual(['live']);
    expect(localBusy({ camera: 'idle' })).toEqual([]);
  });

  it('words the sequence with its object and frames (01 2.3.7)', () => {
    const a = { sequence: { state: 'running', object: 'SS Cyg', done: 34, total: 120 } };
    expect(busySentence(item('sequence'), a)).toBe('A sequence is running: SS Cyg, 34 of 120 frames.');
    expect(busySentence(item('sequence'), { sequence: { state: 'paused', object: null, done: 1, total: 1 } })).toBe('A sequence is paused: 1 of 1 frame.');
    expect(busySentence(item('sequence'), { sequence: { state: 'scheduled', object: 'RR Lyr', done: 0, total: 0 } })).toBe('A sequence waits for its start time: RR Lyr.');
    expect(busySentence(item('sequence'))).toBe('A sequence is running.');
  });

  it("uses the server's words, then the exposure length, then the table", () => {
    const run = { sequence: { state: 'running', object: 'X', done: 1, total: 2 } };
    expect(busySentence(item('sequence', 'A sequence is running: SS Cyg, 34 of 120 frames.'), run)).toBe('A sequence is running: SS Cyg, 34 of 120 frames.');
    expect(busySentence(item('exposure'), { exposureS: 10 })).toBe('An exposure of 10.0 s is in progress.');
    expect(busySentence(item('rerun', 'Re-run of SS Cyg (120 frames)'))).toBe('Re-run of SS Cyg (120 frames).');
    expect(busySentence(item('live'))).toBe('Live view is running.');
    expect(busySentence(item('mystery_task'))).toBe('A mystery task is running.');
  });

  it('says what quitting stops', () => {
    expect(quitConsequence([item('sequence'), item('exposure')])).toBe(
      'Quitting stops the sequence and the camera, closes the equipment connections and shuts down the ARGOS server.',
    );
    expect(quitConsequence([item('live'), item('exposure'), item('slew'), item('rerun')])).toBe(
      "Quitting stops the camera, the mount's motion and the running tasks, closes the equipment connections and shuts down the ARGOS server.",
    );
    // A FITS being written is finished, never cut: it adds nothing to stop.
    expect(quitConsequence([item('write')])).toBe('Quitting closes the equipment connections and shuts down the ARGOS server.');
    expect(quitConsequence([])).toBe('Quitting closes the equipment connections and shuts down the ARGOS server.');
  });

  it('has an icon for each kind, the attention mark otherwise', () => {
    expect(busyIcon('sequence')).toBe('nav-sequencer');
    expect(busyIcon('unknown')).toBe('attention');
  });
});

describe('stages', () => {
  it("keeps the server's words, else the table, else the id made readable", () => {
    expect(stageLabel('devices', 'Disconnecting the mount…')).toBe('Disconnecting the mount');
    expect(stageLabel('stopping_sequence')).toBe('Stopping the sequence');
    expect(stageLabel('devices')).toBe('Closing the equipment connections');
    expect(['services', 'files', 'exit'].map((s) => stageLabel(s))).toEqual(['Stopping background tasks', 'Finishing file writes', 'Stopping the ARGOS server']);
    expect(stageLabel('flush_queue')).toBe('Flush queue');
    expect(stageLabel('')).toBe('Shutting down');
  });

  it('counts up: tenths under 10 s, then whole seconds', () => {
    expect(elapsedText(0)).toBe('< 0.1 s');
    expect(elapsedText(99)).toBe('< 0.1 s');
    expect(elapsedText(100)).toBe('0.1 s');
    expect(elapsedText(340)).toBe('0.3 s');
    expect(elapsedText(2_999)).toBe('2.9 s');
    expect(elapsedText(9_999)).toBe('9.9 s');
    expect(elapsedText(10_000)).toBe('10 s');
    expect(elapsedText(12_999)).toBe('12 s');
    expect(elapsedText(65_000)).toBe('1 min 05 s');
    expect(elapsedText(-5)).toBe('< 0.1 s');
  });
});
