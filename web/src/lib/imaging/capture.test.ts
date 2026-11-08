import { describe, expect, it } from 'vitest';
import { afFrames, autofocusWheelGuard, darkGuard, frameNote, needsDark, ownerReason } from './capture';

const wheel = (over: Partial<{ state: 'idle' | 'moving' | 'disconnected' | 'error'; slot: string | null; target: string | null; dark_slot: boolean }> = {}) => ({
  state: 'idle' as const,
  slot: 'IR',
  target: null,
  dark_slot: true,
  ...over,
});

describe('Take shot rules (S1)', () => {
  it('needs the Dark slot only for Dark and Bias', () => {
    expect(needsDark('dark')).toBe(true);
    expect(needsDark('bias')).toBe(true);
    expect(needsDark('light')).toBe(false);
    expect(needsDark('flat')).toBe(false);
  });

  it('refuses a Dark while the wheel turns to another slot, as the server does', () => {
    expect(darkGuard('dark', wheel({ state: 'moving', slot: null, target: 'LP' }))).toMatch(/turning to LP: a Dark frame needs it settled on Dark/);
    expect(darkGuard('bias', wheel({ state: 'moving', slot: null, target: 'IR' }))).toMatch(/a Bias frame/);
  });

  it('lets the server turn a settled wheel, or one already turning to Dark', () => {
    expect(darkGuard('dark', wheel())).toBeNull();
    expect(darkGuard('dark', wheel({ state: 'moving', target: 'Dark' }))).toBeNull();
    expect(darkGuard('light', wheel({ state: 'moving', target: 'LP' }))).toBeNull();
  });

  it('refuses a Light or Flat shot through the Dark slot (409 dark_slot)', () => {
    expect(darkGuard('light', wheel({ slot: 'Dark' }))).toMatch(/on Dark, which blocks the light: choose a filter for the Light frame/);
    expect(darkGuard('flat', wheel({ state: 'moving', slot: null, target: 'Dark' }))).toMatch(/turning to Dark, which blocks the light/);
    expect(darkGuard('light', wheel({ slot: 'IR' }))).toBeNull();
    expect(frameNote('light', wheel({ slot: 'Dark' }), false)?.tone).toBe('warn');
  });

  it('refuses autofocus behind the Dark slot or while the wheel turns', () => {
    expect(autofocusWheelGuard(wheel({ slot: 'Dark' }))).toMatch(/on Dark, which blocks the light/);
    expect(autofocusWheelGuard(wheel({ state: 'moving', slot: null, target: 'LP' }))).toMatch(/turning to LP/);
    expect(autofocusWheelGuard(wheel())).toBeNull();
    expect(autofocusWheelGuard(null)).toBeNull();
  });

  it('has nothing to guard without a wheel or without a Dark slot', () => {
    expect(darkGuard('dark', null)).toBeNull();
    expect(darkGuard('dark', wheel({ state: 'disconnected' }))).toBeNull();
    expect(darkGuard('dark', wheel({ dark_slot: false, state: 'moving', target: 'LP' }))).toBeNull();
  });

  it('says what a Dark shot will do, before the shot', () => {
    expect(frameNote('light', wheel(), false)).toBeNull();
    expect(frameNote('dark', wheel(), false)?.text).toMatch(/turns the wheel to Dark first \(now IR\)/);
    expect(frameNote('dark', wheel({ slot: 'Dark' }), false)?.text).toMatch(/light is blocked/);
    expect(frameNote('dark', null, false)).toEqual({ text: expect.stringMatching(/cover the telescope/), tone: 'warn' });
    expect(frameNote('dark', wheel({ state: 'moving', target: 'LP', slot: null }), false)?.tone).toBe('warn');
    expect(frameNote('light', wheel(), true)?.text).toMatch(/Turning the wheel to Dark/);
  });
});

describe('camera owner and autofocus frames', () => {
  it('names the owner that blocks the settings', () => {
    expect(ownerReason('autofocus')).toMatch(/autofocus/);
    expect(ownerReason('sequence')).toMatch(/sequence/);
    expect(ownerReason('live')).toBeNull();
    expect(ownerReason('idle')).toBeNull();
  });

  it('shows the AF exposure capped at 10 s with the capture gain (S22), or the run in progress', () => {
    expect(afFrames(null, { exposure_s: 30, gain: 120 })).toEqual({ exposure_s: 10, gain: 120 });
    expect(afFrames({ state: 'done', params: { exposure_s: 2, gain: 80 } }, { exposure_s: 1, gain: 50 })).toEqual({ exposure_s: 1, gain: 50 });
    expect(afFrames({ state: 'running', params: { exposure_s: 2, gain: 80 } }, { exposure_s: 1, gain: 50 })).toEqual({ exposure_s: 2, gain: 80 });
    expect(afFrames(null, null)).toBeNull();
  });
});
