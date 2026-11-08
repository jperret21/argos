import { describe, expect, it } from 'vitest';
import {
  canOpenConfirm,
  canStartHold,
  holdCaption,
  holdFraction,
  holdHint,
  HOLD_MS,
  releaseOutcome,
  slidOff,
  TAP_FRACTION,
} from './hold';
import { canChoose, choosesOnMove, DEFAULT_BUSY_REASON, segmentKey, segmentReason, tabStop } from './segmented';
import { splitMainName } from './split';
import { estimateWidth, fitToolbar, overflowItems, rovingTarget, rowWidth, widthKey, type FitItem, type ToolDef } from './toolbar';

describe('Segmented (manual activation for hardware)', () => {
  it('arrows move the focus, wrapping; Home / End jump; Space and Enter choose', () => {
    expect(segmentKey('ArrowRight', 0, 3)).toEqual({ move: 1 });
    expect(segmentKey('ArrowDown', 2, 3)).toEqual({ move: 0 });
    expect(segmentKey('ArrowLeft', 0, 3)).toEqual({ move: 2 });
    expect(segmentKey('ArrowUp', 1, 3)).toEqual({ move: 0 });
    expect(segmentKey('Home', 2, 3)).toEqual({ move: 0 });
    expect(segmentKey('End', 0, 3)).toEqual({ move: 2 });
    expect(segmentKey(' ', 1, 3)).toEqual({ choose: true });
    expect(segmentKey('Enter', 1, 3)).toEqual({ choose: true });
    expect(segmentKey('a', 1, 3)).toBeNull();
    expect(segmentKey('ArrowRight', 0, 0)).toBeNull();
  });

  it('only display choices follow the focus: walking the wheel never moves it', () => {
    expect(choosesOnMove('auto')).toBe(true);
    expect(choosesOnMove('manual')).toBe(false);
  });

  it('while the wheel turns, the other slots wait with a reason; the control reason wins', () => {
    const ir = { value: 'IR', label: 'IR' };
    const lp = { value: 'LP', label: 'LP', disabledReason: 'Not in this profile' };
    expect(segmentReason(ir, {})).toBeNull();
    expect(segmentReason(lp, {})).toBe('Not in this profile');
    expect(segmentReason(ir, { busyValue: 'Dark' })).toBe(DEFAULT_BUSY_REASON);
    expect(segmentReason(ir, { busyValue: 'Dark', busyReason: 'The wheel is turning to Dark' })).toBe('The wheel is turning to Dark');
    expect(segmentReason({ value: 'Dark', label: 'Dark' }, { busyValue: 'Dark' })).toBeNull();
    expect(segmentReason(ir, { disabledReason: 'Autofocus owns the camera', busyValue: 'Dark' })).toBe('Autofocus owns the camera');
  });

  it('choosing the value in effect, the one being applied, or an unavailable one does nothing', () => {
    const ir = { value: 'IR', label: 'IR' };
    const dark = { value: 'Dark', label: 'Dark' };
    expect(canChoose(ir, 'IR', {})).toBe(false);
    expect(canChoose(dark, 'IR', {})).toBe(true);
    expect(canChoose(dark, 'IR', { busyValue: 'Dark' })).toBe(false);
    expect(canChoose(dark, 'IR', { disabledReason: 'Connect the wheel first' })).toBe(false);
  });

  it('keeps one tab stop: the focused segment, else the selected one, else the first', () => {
    expect(tabStop(2, 0, 4)).toBe(2);
    expect(tabStop(-1, 1, 4)).toBe(1);
    expect(tabStop(-1, -1, 4)).toBe(0);
    expect(tabStop(-1, 0, 0)).toBe(-1);
  });
});

describe('SplitButton', () => {
  it('names the main part as it reads: the action with its options in use', () => {
    expect(splitMainName('Capture', undefined, '2.0 s')).toBe('Capture · 2.0 s');
    expect(splitMainName('Autofocus', 'Autofocus', '2.0 s · 80')).toBe('Autofocus · 2.0 s · 80');
    expect(splitMainName('Export', 'CSV')).toBe('Export: CSV');
    expect(splitMainName('Capture')).toBe('Capture');
  });
});

describe('HoldButton (owner D4)', () => {
  it('fills linearly over 700 ms, clamped', () => {
    expect(HOLD_MS).toBe(700);
    expect(holdFraction(0)).toBe(0);
    expect(holdFraction(350)).toBeCloseTo(0.5);
    expect(holdFraction(900)).toBe(1);
    expect(holdFraction(-5)).toBe(0);
    expect(holdFraction(10, 0)).toBe(1);
  });

  it('an early release sends nothing: a quick tap teaches the gesture, a longer one says released', () => {
    expect(releaseOutcome(0.05)).toBe('tapped');
    expect(releaseOutcome(TAP_FRACTION)).toBe('released');
    expect(releaseOutcome(0.9)).toBe('released');
  });

  it('sliding off the button (beyond the slop) cancels the hold', () => {
    const r = { left: 0, right: 100, top: 0, bottom: 40 };
    expect(slidOff(r, 50, 20)).toBe(false);
    expect(slidOff(r, 105, 20)).toBe(false);
    expect(slidOff(r, 110, 20)).toBe(true);
    expect(slidOff(r, 50, -9)).toBe(true);
  });

  it('never starts a hold or a confirmation while the action runs; Enter reopens after a failure', () => {
    expect(canStartHold('rest', false)).toBe(true);
    expect(canStartHold('rest', true)).toBe(false);
    expect(canStartHold('busy', false)).toBe(false);
    expect(canStartHold('confirm', false)).toBe(false);
    expect(canOpenConfirm('failed', false)).toBe(true);
    expect(canOpenConfirm('busy', false)).toBe(false);
    expect(canOpenConfirm('rest', true)).toBe(false);
  });

  it('the caption changes, the label never does; a reason wins', () => {
    const c = { verb: 'park', label: 'Park' };
    expect(holdHint('park')).toBe('Hold 0.7 s to park · Enter to confirm');
    expect(holdCaption('rest', c)).toEqual({ text: 'Hold 0.7 s to park · Enter to confirm', tone: 'muted' });
    expect(holdCaption('holding', { ...c, remainingS: 0.34 })).toEqual({ text: 'Keep holding', tone: 'plain', count: '0.3 s' });
    expect(holdCaption('released', c).text).toBe('Released · nothing sent');
    expect(holdCaption('tapped', c).text).toBe('Hold to park, or press Enter');
    expect(holdCaption('busy', { ...c, busyLabel: 'Parking…' }).text).toBe('Parking…');
    expect(holdCaption('failed', { ...c, failure: 'Mount did not answer' })).toEqual({ text: 'Mount did not answer', tone: 'failed' });
    expect(holdCaption('holding', { ...c, disabledReason: 'Connect the mount first' })).toEqual({
      text: 'Connect the mount first',
      tone: 'reason',
    });
  });
});

describe('Toolbar priority overflow', () => {
  const items: FitItem[] = [
    { id: 'capture', group: 'acq', width: 60, priority: Infinity },
    { id: 'live', group: 'acq', width: 34, priority: Infinity },
    { id: 'stop', group: 'acq', width: 34, priority: Infinity },
    { id: 'zoom-in', group: 'view', width: 34, priority: 3 },
    { id: 'zoom-out', group: 'view', width: 34, priority: 3 },
    { id: 'fit', group: 'view', width: 34, priority: 4 },
    { id: 'stretch', group: 'disp', width: 34, priority: 1 },
    { id: 'reset', group: 'disp', width: 34, priority: 1 },
  ];
  const opts = { gap: 2, separator: 13, overflow: 48 };

  it('measures a row: tools, gaps inside groups, separators between them', () => {
    const all = new Set(items.map((i) => i.id));
    expect(rowWidth(items, all, { ...opts, available: 0 }, false)).toBe(60 + 34 + 34 + 4 + 34 * 3 + 4 + 34 * 2 + 2 + 2 * 13);
    expect(rowWidth(items, all, { ...opts, available: 0 }, true)).toBe(rowWidth(items, all, { ...opts, available: 0 }, false) + 48);
  });

  it('keeps everything when it fits', () => {
    const r = fitToolbar(items, { ...opts, available: 2000 });
    expect(r.hidden).toEqual([]);
    expect(r.visible.size).toBe(items.length);
  });

  it('hides the lowest priority first, rightmost first, drops an emptied group and reserves the trigger', () => {
    const full = rowWidth(items, new Set(items.map((i) => i.id)), { ...opts, available: 0 }, false);
    const r = fitToolbar(items, { ...opts, available: full - 10 });
    // The overflow trigger costs 48: the whole 'disp' group (and its separator) has to go.
    expect(r.hidden).toEqual(['stretch', 'reset']);
    expect(r.width).toBeLessThanOrEqual(full - 10);
    // Then the equal priorities 3 of 'view', its rightmost tool first; 'fit' (4) stays.
    const r2 = fitToolbar(items, { ...opts, available: 250 });
    expect(r2.hidden).toEqual(['zoom-in', 'zoom-out', 'stretch', 'reset']);
    expect(r2.width).toBe(132 + 34 + 13 + 48);
  });

  it('backfills: a small tool comes back into the room a wide one left', () => {
    const its: FitItem[] = [
      { id: 'a', group: 'g1', width: 100, priority: Infinity },
      { id: 'big', group: 'g2', width: 150, priority: 2 },
      { id: 'small', group: 'g3', width: 30, priority: 1 },
    ];
    const r = fitToolbar(its, { ...opts, available: 250 });
    expect(r.hidden).toEqual(['big']);
    expect(r.width).toBe(100 + 13 + 30 + 48);
  });

  it('never hides run-critical tools, even when nothing else fits', () => {
    const r = fitToolbar(items, { ...opts, available: 50 });
    expect(r.visible.has('capture')).toBe(true);
    expect(r.visible.has('live')).toBe(true);
    expect(r.visible.has('stop')).toBe(true);
    expect(r.hidden).toEqual(['zoom-in', 'zoom-out', 'fit', 'stretch', 'reset']);
  });

  it('the overflow menu keeps order, groups, toggle state, shortcuts and reasons', () => {
    const tools: ToolDef[] = [
      { id: 'zoom-in', group: 'view', kind: 'button', icon: 'zoom-in', label: 'Zoom in', shortcut: '+', priority: 3 },
      { id: 'cross', group: 'view', kind: 'toggle', icon: 'crosshair', label: 'Crosshair', pressed: true, priority: 3 },
      { id: 'scale', group: 'disp', kind: 'readout', icon: 'zoom-fit', label: 'Zoom', text: '62 %', priority: 1 },
      { id: 'cap', group: 'disp', kind: 'split', icon: 'capture', label: 'Capture', text: '2.0 s', priority: 1, disabledReason: 'Connect the camera first' },
    ];
    const menu = overflowItems(tools);
    expect(menu.map((m) => ('kind' in m && m.kind === 'separator' ? '|' : m.id))).toEqual(['zoom-in', 'cross', '|', 'scale', 'cap']);
    expect(menu[1]).toMatchObject({ kind: 'checkbox', checked: true });
    expect(menu[0]).toMatchObject({ shortcut: '+' });
    expect(menu[3]).toMatchObject({ label: 'Zoom: 62 %' });
    expect(menu[4]).toMatchObject({ label: 'Capture · 2.0 s', disabledReason: 'Connect the camera first' });
  });

  it('remeasures a tool only when what it shows changes; estimates before the first measure', () => {
    const icon: ToolDef = { id: 'z', group: 'g', kind: 'button', icon: 'zoom-in', label: 'Zoom in', priority: 1 };
    expect(widthKey(icon)).toBe(widthKey({ ...icon, label: 'Other' }));
    const ro: ToolDef = { id: 'r', group: 'g', kind: 'readout', icon: 'x', label: 'Zoom', text: '62 %', priority: 1 };
    expect(widthKey(ro)).not.toBe(widthKey({ ...ro, text: '100 %' }));
    expect(estimateWidth(icon, 34)).toBe(34);
    expect(estimateWidth({ ...icon, width: 50 }, 34)).toBe(50);
    expect(estimateWidth({ ...icon, kind: 'split', text: '2.0 s' }, 34)).toBe(34 + 19 + 8 + 5 * 7);
  });

  it('roving focus: arrows wrap, Home / End jump, Up / Down are left to the part', () => {
    expect(rovingTarget('ArrowRight', 2, 3)).toBe(0);
    expect(rovingTarget('ArrowLeft', 0, 3)).toBe(2);
    expect(rovingTarget('Home', 2, 3)).toBe(0);
    expect(rovingTarget('End', 0, 3)).toBe(2);
    expect(rovingTarget('ArrowDown', 1, 3)).toBeNull();
    expect(rovingTarget('ArrowRight', 0, 0)).toBeNull();
  });
});
